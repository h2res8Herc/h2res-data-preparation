from pathlib import Path
import tempfile
import unittest

import pandas as pd

from default_model_inputs import complete_defaults
from native_input_checks import outside_supply_checks


class OutsideSystemTests(unittest.TestCase):
    def fixture(self):
        shares=pd.DataFrame(dict(year=[2025,2050],System='OUTSIDE',outside_wind_supply_share=[.2,.4],outside_pv_supply_share=[.1,.3]))
        curves=pd.DataFrame(dict(period=range(1,8761),outside_demand_normalized=.6,outside_wind_cf=.4,outside_pv_cf=.2))
        return shares,curves

    def test_global_outside_rows_are_preserved_when_regional_defaults_expand(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            for name,table in zip(('outside_system_supply_shares.csv','outside_system_normalized_curves.csv'),self.fixture()):
                table.to_csv(data/name,index=False)
            before={p.name:p.read_bytes() for p in data.iterdir()}
            complete_defaults(data,{('HR','HR021'),('IT','IT1')},[],[],'unused.xlsx',[])
            self.assertEqual(before,{p.name:p.read_bytes() for p in data.iterdir()})
            self.assertEqual(outside_supply_checks(*self.fixture()),[])

    def test_duplicate_global_years_and_incomplete_calendar_block_publication(self):
        shares,curves=self.fixture()
        errors=outside_supply_checks(pd.concat([shares,shares.assign(System='HR')]),curves)
        self.assertTrue(any('one row per integer year' in error for error in errors))
        self.assertTrue(outside_supply_checks(shares,curves.iloc[:24]))
        self.assertTrue(outside_supply_checks(shares.assign(outside_wind_supply_share=.9),curves))


if __name__=='__main__':unittest.main()
