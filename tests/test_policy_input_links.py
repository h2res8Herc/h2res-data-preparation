import unittest
import pandas as pd

from policy_input_links import national_table,generation_checks


class PolicyInputTests(unittest.TestCase):
    def fixture(self):
        plants=pd.DataFrame(dict(System=['HR','HR'],Zone=['a','b'],fuel_type=['Gas','Coal']))
        targets={('HR','a'),('HR','b')}
        source=pd.DataFrame(dict(System='HR',Zone='HR1',Year=2025,Fuel=['Gas','Coal','Biomass'],Target_TWh=[2.3,.6,.5]))
        return source,targets,plants

    def test_national_calibration_is_an_aggregate_not_a_demand_allocation(self):
        source,targets,plants=self.fixture()
        result,notes=national_table(source,targets,plants,'generation_targets')
        self.assertEqual(result.Zone.tolist(),['*','*'])
        self.assertEqual(result.Target_TWh.tolist(),[2.3,.6])
        self.assertEqual(generation_checks(result,plants,targets),[])
        absent=[r for r in notes if not r['applied']]
        self.assertEqual([(r['Fuel'],r['supplied_target_TWh']) for r in absent],[('Biomass',.5)])
        self.assertEqual(len(source),3)

    def test_wrong_regional_fuel_calibration_fails_before_model_build(self):
        source,targets,plants=self.fixture()
        wrong=source.iloc[:1].assign(Zone='b')
        self.assertTrue(generation_checks(wrong,plants,targets))

    def test_national_budgets_are_not_duplicated_in_each_region(self):
        _,targets,plants=self.fixture()
        for sheet in ('hydro_caps','biomass_caps'):
            source=pd.DataFrame(dict(System=['HR'],Zone=['HR1'],Year=['*'],Cap_TWh=[6.5]))
            result,_=national_table(source,targets,plants,sheet)
            self.assertEqual(result.Cap_TWh.tolist(),[6.5])
            self.assertEqual(result.Zone.tolist(),['*'])


if __name__=='__main__':unittest.main()
