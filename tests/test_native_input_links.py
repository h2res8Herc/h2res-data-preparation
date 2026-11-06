"""Conserve budgets/stocks while matching the identifiers the native model uses."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from power_input_links import link_tables
from native_input_checks import generator_checks, industry_checks
from model_input_bundle import pooled_industry
from h2res_input_schema import annual_limits


class GeneratorLinkTests(unittest.TestCase):
    def fixture(self):
        plants=pd.DataFrame(dict(unit_name=['HR_Plant_A','HR_Plant_B','HR_Plant_C'],System='HR',Zone=['a','a','b'],
                                 fuel_type='Solar',technology='PHOT',CHPType='N',cap_mw=[10.,20.,30.]))
        old=pd.DataFrame(dict(unit_name=['HR_PV','HR_PV_1'],System='HR',Zone='HR1',fuel_type='Solar',technology='PHOT',CHPType='N'))
        cost=pd.DataFrame(dict(year=[2020,2021],System='HR',HR_PV=[.6,.5],HR_PV_1=[.6,.5]))
        limits=pd.DataFrame(dict(year=[2020,2021],zone='HR1',HR_PV=[100.,200.],HR_PV_1=[200.,400.],HeatPump=[32.,64.]))
        return plants,old,cost,limits

    def test_names_calendar_home_zone_and_national_budget_are_linked(self):
        plants,old,cost,limits=self.fixture()
        before=limits.copy(deep=True)
        result,annual,notes=link_tables(plants,old,cost,limits,cost,limits,{('HR','a'),('HR','b')},{('HR','a'):.25,('HR','b'):.75})
        for name in plants.unit_name:
            self.assertEqual(result[name].tolist(),[.6,.5])
        for year,budget in [(2020,300.),(2021,600.)]:
            block=annual.loc[annual.year.eq(year)]
            self.assertAlmostEqual(block[list(plants.unit_name)].sum().sum(),budget)
        self.assertEqual(annual.loc[annual.zone.eq('b'),'HR_Plant_A'].tolist(),[0.,0.])
        self.assertEqual(annual.loc[annual.zone.eq('a'),'HR_Plant_A'].tolist(),[50.,100.])
        self.assertEqual(annual.loc[annual.zone.eq('a'),'HeatPump'].tolist(),[8.,16.])
        self.assertEqual(annual.loc[annual.zone.eq('b'),'HeatPump'].tolist(),[24.,48.])
        self.assertAlmostEqual(sum(r['investment_budget_share'] for r in notes),1.)
        errors,audit=generator_checks(plants,result,annual,[2020,2021],{'a','b'})
        self.assertEqual(errors,[])
        self.assertTrue(audit['cost_and_investment_keys_complete'])
        pd.testing.assert_frame_equal(limits,before)

    def test_reader_contract_detects_missing_plant_cost_and_investment_zone(self):
        plants,_,cost,limits=self.fixture()
        errors,_=generator_checks(plants,cost,limits,[2020,2021],{'a','b'})
        self.assertTrue(any('tech_cost_years lacks generator' in error for error in errors))
        self.assertTrue(any('cap_inv_lim lacks generator' in error for error in errors))

    def test_unknown_financial_assumption_is_not_silently_zeroed(self):
        plants,old,cost,limits=self.fixture()
        with self.assertRaisesRegex(ValueError,'No explicit reference cost'):
            link_tables(plants,old,cost[['year','System']],limits,cost,limits,{('HR','a'),('HR','b')},{('HR','a'):.5,('HR','b'):.5})

    def test_geothermal_uses_power_cost_and_explicit_existing_only_build_default(self):
        plants,old,cost,limits=self.fixture()
        plants=plants.iloc[:1].assign(fuel_type='Geothermal',technology='STUR')
        cost['Geothermal.1']=3.4
        result,annual,notes=link_tables(plants,old,cost,limits,cost,limits,{('HR','a')},{('HR','a'):1.})
        self.assertTrue(result.HR_Plant_A.eq(3.4).all())
        self.assertTrue(annual.HR_Plant_A.eq(0).all())
        self.assertEqual(notes[0]['investment_basis'],'explicit_existing_only_zero_build_default')


class IndustryAccountingTests(unittest.TestCase):
    def fixture(self):
        table=pd.DataFrame(dict(System='HR',zone='HR028',Industry=['A','A','B','B'],category='all',
            unit_name=['Gas_industry','Coal_industry']*2,fuel_type=['Gas','Coal']*2,include_in_the_model='N',
            cap_mw=[10.,20.,30.,40.],share_fuel_2020=[.9,.1,.2,.8],max_share_fuel=[.9,.7,.5,1.],
            efficiency=[.9,.8,.6,.8],CO2Intensity=[.2,.8,.4,.8],max_cap=100.,max_inv_period=10.))
        profiles=pd.DataFrame(dict(System=['HR'],zone=['HR028'],period=[1],A=[100.],B=[300.]))
        return annual_limits(table),profiles

    def test_pool_conserves_stocks_demand_weighted_mix_and_bounds(self):
        table,profiles=self.fixture()
        # Older native simple sheets omit bounds present in the source table.
        template=table.iloc[:2].drop(columns=['max_cap','max_inv_period_2030'])
        result=pooled_industry(table,profiles,template)
        gas=result.loc[result.fuel_type.eq('Gas')].iloc[0]
        self.assertAlmostEqual(gas.cap_mw,40.)
        self.assertAlmostEqual(gas.share_fuel_2020,.375)
        self.assertAlmostEqual(gas.max_share_fuel,.6)
        self.assertAlmostEqual(gas.efficiency,150./(90./.9+60./.6))
        self.assertAlmostEqual(gas.CO2Intensity,.3)
        self.assertAlmostEqual(gas.max_cap,200.)
        self.assertAlmostEqual(gas.max_inv_period_2030,20.)
        errors,audit=industry_checks(table,result,profiles,'regular')
        self.assertEqual(errors,[])
        self.assertEqual(audit['pooled_annual_service_MWh'],400.)
        self.assertAlmostEqual(result.share_fuel_2020.sum(),1.)

    def test_validator_rejects_empty_incorrect_or_double_counted_pool(self):
        table,profiles=self.fixture()
        result=pooled_industry(table,profiles,table.iloc[:2])
        for corrupted in (result.iloc[:0],result.assign(cap_mw=lambda d:d.cap_mw*2),result.assign(share_fuel_2020=.1),result.assign(max_cap=lambda d:d.max_cap*2)):
            with self.subTest(rows=len(corrupted)):
                errors,_=industry_checks(table,corrupted,profiles,'regular')
                self.assertTrue(errors)

    def test_empty_simple_sheet_is_correct_for_fully_detailed_services(self):
        table,profiles=self.fixture()
        table['include_in_the_model']='Y'
        result=pooled_industry(table,profiles,table.iloc[:2])
        self.assertTrue(result.empty)
        errors,audit=industry_checks(table,result,profiles,'regular')
        self.assertEqual(errors,[])
        self.assertTrue(audit['empty_pool_is_valid'])

    def test_enabled_heat_pump_does_not_send_the_same_service_to_remainder(self):
        table,profiles=self.fixture()
        table=pd.concat([table,table.iloc[:1].assign(unit_name='HP_industry_60',fuel_type='Electricity',
                         include_in_the_model='Y',cap_mw=0.,share_fuel_2020=0.,efficiency=3.)],ignore_index=True)
        pooled=pooled_industry(table,profiles,table.iloc[:2])
        # Only B is completely excluded. A's disabled baseline is reported by
        # the accounting validator instead of secretly pooling A a second time.
        self.assertEqual(pooled.cap_mw.sum(),70.)
        errors,_=industry_checks(table,pooled,profiles,'regular')
        self.assertTrue(any('drops fuel service' in error for error in errors))


if __name__=='__main__':
    unittest.main()
