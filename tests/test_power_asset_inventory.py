"""Prevent carrier storage and unknown electric MW from corrupting GENCO budgets."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd

from power_asset_inventory import partition_generator_assets,write_asset_inventory
from power_input_links import link_tables
from native_input_checks import generator_checks


class PowerAssetInventoryTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame(dict(unit_name=['IT_ITC4D_Hydrogen_Storage_NAN_NONCHP_AGG','IT_H2','IT_Gas','IT_PHS','IT_unknown'],
            System='IT',Zone='ITC4D',fuel_type=['Hydrogen Storage','Hydrogen Storage','Gas','Hydro','Gas'],
            technology=['NAN','NAN','COMC','HPHS','COMC'],CHPType='N',
            cap_mw=[np.nan,.01,10.,20.,np.nan],STOCapacity=[.07,.14,0.,100.,0.]))

    def test_reported_italy_storage_is_separate_from_electric_generators(self):
        original=self.fixture();before=original.copy(deep=True)
        retained,excluded=partition_generator_assets(original)
        self.assertEqual(retained.unit_name.tolist(),['IT_Gas','IT_PHS'])
        self.assertEqual(len(excluded),3)
        self.assertEqual(excluded.iloc[0].exclusion_reason,'storage_inventory_not_an_electric_generator')
        self.assertEqual(excluded.iloc[0].STOCapacity,.07)
        self.assertTrue(pd.isna(excluded.iloc[0].cap_mw))
        pd.testing.assert_frame_equal(before,original)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'inventory.csv'
            report=write_asset_inventory(excluded,path,len(retained))
            self.assertEqual(report['excluded_records'],3)
            self.assertIn('not automatically',report['interpretation'])
            pd.testing.assert_frame_equal(pd.read_csv(path),excluded.reset_index(drop=True),check_dtype=False)

    def test_raw_source_energy_is_preserved_and_hydro_storage_is_retained(self):
        raw=pd.DataFrame(dict(Name=['hydrogen','heat','battery','mechanical','hydro'],
            Fueltype=['Hydrogen Storage','Heat Storage','Battery','Mechanical Storage','Hydro'],
            Technology=['unknown']*4+['Pumped Storage'],Capacity=[np.nan,1.,2.,3.,4.],StorageCapacity_MWh=[.07,5.,6.,7.,8.]))
        retained,excluded=partition_generator_assets(raw,fuel='Fueltype',technology='Technology',capacity='Capacity')
        self.assertEqual(retained.Name.tolist(),['hydro'])
        self.assertEqual(excluded.StorageCapacity_MWh.sum(),18.07)
        self.assertEqual(len(excluded),4)

    def test_financial_allocation_rejects_unknown_mw_before_calculating_shares(self):
        plants=self.fixture()
        with self.assertRaisesRegex(ValueError,'Invalid electric generator capacity MW.*IT_ITC4D'):
            link_tables(plants,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),
                        {('IT','ITC4D')},{('IT','ITC4D'):1.})

    def test_nonfinite_and_negative_capacity_are_reported_but_zero_is_valid(self):
        plants=self.fixture().iloc[[2]*4].reset_index(drop=True)
        plants['cap_mw']=[np.inf,-1.,0.,np.nan]
        retained,excluded=partition_generator_assets(plants)
        self.assertEqual(retained.cap_mw.tolist(),[0.])
        self.assertEqual(len(excluded),3)

    def test_native_validation_rejects_storage_even_with_valid_financial_columns(self):
        plant=self.fixture().iloc[[1]].copy()
        cost=pd.DataFrame({'year':[2020],'System':['IT'],'IT_H2':[1.]})
        limits=pd.DataFrame({'year':[2020],'zone':['ITC4D'],'IT_H2':[10.]})
        errors,_=generator_checks(plant,cost,limits,[2020],{'ITC4D'})
        self.assertTrue(any('Non-generator storage' in e for e in errors))


if __name__=='__main__':unittest.main()
