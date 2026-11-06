"""Catch namespace conflicts and incomplete inputs before CSV generation."""
from pathlib import Path
import sys
import json
import tempfile
import unittest
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from refactored_input_checks import select_scope,unique_rows,common_fuel_price,year_value
from refactored_input_export import CaseExporter,export_refactored_bundle


class NamespaceChecks(unittest.TestCase):
    def test_shared_zone_names_in_foreign_reference_rows_do_not_leak(self):
        frame=pd.DataFrame(dict(System=['HR','SI','SI'],zone=['SI1','SI1','SI2'],value=[2.,3.,4.]))
        self.assertEqual(select_scope(frame,system='SI',zone='SI1').value.tolist(),[3.])

    def test_identical_profile_duplicates_can_be_coalesced(self):
        frame=pd.DataFrame(dict(period=[1,1,2],COP=[3.,3.,4.]))
        result=unique_rows(frame,['period'],'COP',values=['COP'],allow_identical=True)
        self.assertEqual(result.COP.tolist(),[3.,4.])

    def test_conflicting_profile_duplicates_are_not_silently_discarded(self):
        frame=pd.DataFrame(dict(period=[1,1],COP=[3.,4.]))
        with self.assertRaisesRegex(ValueError,'COP.*duplicate keys'):
            unique_rows(frame,['period'],'COP',values=['COP'],allow_identical=True)

    def test_country_fuel_prices_are_not_averaged(self):
        with self.assertRaisesRegex(ValueError,'cannot be averaged silently'):
            common_fuel_price(pd.Series([20.,40.]),'Gas/2025')
        self.assertEqual(common_fuel_price(pd.Series([20.,20.]),'Gas/2025'),20.)

    def test_invalid_prices_and_scaling_values_fail_early(self):
        for values in [[np.nan],[-1.],[np.inf]]:
            with self.subTest(values=values),self.assertRaises(ValueError):common_fuel_price(pd.Series(values),'Gas')
        for row in [pd.Series({2025:-1.}),pd.Series({2025:np.nan}),pd.Series({2030:1.}),pd.Series([1.,2.],index=[2025,'2025'])]:
            with self.subTest(row=str(row)),self.assertRaises(ValueError):year_value(row,2025,'dem_change/SI/SI1')

    def test_policy_scaling_uses_country_and_zone_and_allows_explicit_zero(self):
        e=CaseExporter.__new__(CaseExporter);e.countries={'SI1':'SI'}
        e.cache={'policy:dem_change':pd.DataFrame({'System':['HR','SI'],'zone':['SI1','SI1'],2025:[9.,0.]})}
        self.assertEqual(e.demand_multiplier('dem_change','SI1',2025),0.)

    def test_COP_profile_selects_country_before_collapsing_periods(self):
        e=CaseExporter.__new__(CaseExporter);e.countries={'SI1':'SI'};e.cache={}
        weather=pd.concat([pd.DataFrame(dict(System=c,zone='SI1',period=range(1,8761),HP=cop))
            for c,cop in [('HR',2.),('SI',4.)]],ignore_index=True)
        e.sheet=lambda name:weather.copy()
        self.assertTrue(e.efficiency_profile('HP','SI1').eq(4).all())


class EarlyFailureTests(unittest.TestCase):
    def test_all_reported_preflight_errors_are_saved_and_mapping_does_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=root/'data_refactored';case.mkdir();(case/'old').write_text('retained')
            e=Mock()
            result=dict(ready=False,checks=2,errors=[dict(source='tech_cost_years',error='missing 2030'),
                                                   dict(source='COP_HP',error='conflicting SI1 period 1')])
            with patch('refactored_input_export.CaseExporter',return_value=e),patch('refactored_input_export.preflight',return_value=result):
                with self.assertRaisesRegex(ValueError,'preflight failed'):
                    export_refactored_bundle(root/'bundle',root)
            e.build.assert_not_called();e.close.assert_called_once()
            self.assertEqual(json.loads((root/'refactored_preflight.json').read_text())['errors'],result['errors'])
            failure=json.loads((root/'refactored_export_failure.json').read_text())
            self.assertEqual(failure['phase'],'preflight')
            self.assertEqual((case/'old').read_text(),'retained')

    def test_check_only_does_not_generate_or_publish_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e=Mock();result=dict(ready=True,checks=12,errors=[])
            with patch('refactored_input_export.CaseExporter',return_value=e),patch('refactored_input_export.preflight',return_value=result):
                self.assertEqual(export_refactored_bundle(root/'bundle',root,preflight_only=True),result)
            e.build.assert_not_called()
            self.assertFalse((root/'data_refactored').exists())
            self.assertFalse((root/'H2RES_refactored_inputs.zip').exists())


if __name__=='__main__':unittest.main()
