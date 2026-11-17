"""Physical quantities, explicit adaptations and atomic case publication."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from refactored_input_export import CaseExporter,carrier,hourly,residual_electricity,export_refactored_bundle,selected_export_sectors
from h2res_input_gui import build_command,DataPreparationGui

class ElectricityTests(unittest.TestCase):
    def test_only_explicit_sector_baselines_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            period=range(1,8761)
            gross=pd.DataFrame({'A':np.linspace(20.,40.,8760),'B':np.linspace(40.,10.,8760)},index=pd.Index(period,name='period'))
            native=gross.stack().rename('Power').reset_index();native.columns=['period','Zone','Power'];native['System']='HR'
            for sectors,factor,files in [({'power'},1.,[]),({'power','industry'},.8,['industry_electricity.csv']),
                                         ({'power','heating'},.9,['heating_electricity.csv']),
                                         ({'power','industry','heating'},.7,['industry_electricity.csv','heating_electricity.csv'])]:
                with self.subTest(sectors=sectors):
                    e=CaseExporter.__new__(CaseExporter);e.selected_sectors=sectors
                    e.bundle=Path(tmp);e.data=Path(tmp);e.countries={'A':'HR','B':'HR'};e.fleets=[];e.years=[2025]
                    e.audit={};e.source_files={};e.demand_multiplier=lambda *args:1.;e.bus=lambda zone,c:zone+'_'+c
                    seen=[]
                    def source(name):
                        seen.append(name)
                        if name=='electricity_demand.csv':return native
                        if name not in files:raise AssertionError('Read unselected sector: '+name)
                        return (gross*(.2 if name.startswith('industry') else .1)).reset_index()
                    e.series=source;e.build_electricity_demand()
                    np.testing.assert_allclose(e.electricity.to_numpy(),gross.to_numpy()*factor)
                    self.assertEqual(seen,['electricity_demand.csv',*files])
                    self.assertEqual(e.audit['electricity_accounting_MWh']['removed_sector_baseline_files'],files)

    def test_power_only_chp_does_not_create_an_unmodeled_heat_bus(self):
        e=CaseExporter.__new__(CaseExporter);e.selected_sectors={'power'};e.pairs={('HR','HR021')}
        e.audit={};e.plants=[];e.profile={};e.inflows={}
        source=pd.DataFrame(dict(unit_name=['CHP_A'],System='HR',Zone='HR021',technology='Gas',CHPType='Y'))
        e.series=lambda name:source if name=='generators.csv' else pd.DataFrame(dict(period=range(1,8761)))
        def bus(zone,carrier,*args,**kwargs):
            if carrier!='electricity':raise AssertionError('Unselected heating bus')
            return zone+'_electricity'
        e.bus=bus;e.unit=lambda *args,**kwargs:dict(name='CHP_A',fuel='gas')
        e.build_power()
        self.assertEqual(e.audit['chp_without_heat_sector'],['CHP_A'])
        self.assertNotIn('bus_out_2',e.plants[0])

    def test_mixed_year_deficits_conserve_energy_and_original_regional_profiles(self):
        total=pd.DataFrame({'A':[2.,6.,6.],'B':[1.,2.,2.],'C':[4.,4.,4.]})
        baseline=pd.DataFrame({'A':[4.,3.,2.],'B':[1.,1.,1.],'C':[1.,1.,1.]})
        result,changed=residual_electricity(total,baseline,{'A':'HR','B':'HR','C':'SI'})
        self.assertTrue(np.isfinite(result.to_numpy()).all())
        self.assertTrue((result.to_numpy()>=0).all())
        self.assertEqual(changed,1)
        for cols in [['A','B'],['C']]:
            self.assertAlmostEqual(result[cols].sum().sum(),(total[cols]-baseline[cols]).sum().sum())
        self.assertTrue((result.to_numpy()>0).all())
        for cols in [['A','B'],['C']]:
            factor=(total[cols].sum().sum()-baseline[cols].sum().sum())/total[cols].sum().sum()
            np.testing.assert_allclose(result[cols],total[cols]*factor)
            np.testing.assert_allclose(result[cols].div(result[cols].sum(axis=1),axis=0),total[cols].div(total[cols].sum(axis=1),axis=0))
        for zone in total:
            np.testing.assert_allclose(result[zone]/result[zone].sum(),total[zone]/total[zone].sum())

    def test_industrial_region_is_not_zeroed_by_a_different_sector_allocation(self):
        total=pd.DataFrame({'industrial':[1.,2.,3.],'residential':[5.,10.,15.]})
        baseline=pd.DataFrame({'industrial':[4.,6.,8.],'residential':[0.,0.,0.]})
        result,_=residual_electricity(total,baseline,{'industrial':'HR','residential':'HR'})
        np.testing.assert_allclose(result,total*.5)

    def test_true_source_zeros_and_independent_country_budgets_are_retained(self):
        total=pd.DataFrame({'A':[0.,10.],'B':[5.,5.],'C':[1.,3.],'empty':[0.,0.]})
        baseline=pd.DataFrame({'A':[6.,6.],'B':[0.,0.],'C':[0.,1.],'empty':[0.,0.]})
        result,_=residual_electricity(total,baseline,{'A':'HR','B':'HR','C':'SI','empty':'SI'})
        np.testing.assert_allclose(result[['A','B']],total[['A','B']]*.4)
        np.testing.assert_allclose(result[['C','empty']],total[['C','empty']]*.75)
        self.assertEqual(result.A.iloc[0],0)
        self.assertTrue(result['empty'].eq(0).all())

    def test_exhausted_country_budget_is_an_explicit_zero_residual(self):
        total=pd.DataFrame({'A':[1.,2.]})
        result,_=residual_electricity(total,total,{'A':'HR'})
        self.assertTrue(result.A.eq(0).all())

    def test_misaligned_or_negative_source_values_are_rejected(self):
        total=pd.DataFrame({'A':[1.,2.]})
        with self.assertRaisesRegex(ValueError,'same regions'):
            residual_electricity(total,total.rename(columns={'A':'B'}),{'A':'HR'})
        with self.assertRaisesRegex(ValueError,'nonnegative'):
            residual_electricity(total,-total,{'A':'HR'})

    def test_annual_sector_overconsumption_fails(self):
        with self.assertRaisesRegex(ValueError,'annual historical'):
            residual_electricity(pd.DataFrame({'A':[1.]}),pd.DataFrame({'A':[2.]}),{'A':'HR'})

    def test_calendar_rejects_duplicate_and_missing_periods(self):
        frame=pd.DataFrame({'period':range(1,8761),'load':1.})
        self.assertEqual(hourly(frame,'valid').load.sum(),8760)
        frame.loc[0,'period']=2
        with self.assertRaisesRegex(ValueError,'complete non-leap'):hourly(frame,'bad')

class TransportTests(unittest.TestCase):
    def test_absolute_activity_energy_emissions_and_stock(self):
        e=CaseExporter.__new__(CaseExporter)
        e.countries={'HR1':'HR'};e.efuels=False;e.years=[2025,2030]
        e.fleets=[];e.pathway=[];e.mobility={};e.connection={};e.audit={'assumptions':[]}
        e.book=SimpleNamespace(sheet_names=['transport_ICE_prim'])
        fleets=pd.DataFrame([dict(System='HR',zone='HR1',sector='cars',unit_name='ICE_car',type='ICE',total_load=10.,
            number=100.,efficiency_primary=2.,CO2=.25,life_time=15,include_in_the_model='Y')])
        fuels=pd.DataFrame([dict(zone='HR1',sector_prim='ICE_car',fuel_prim='diesel',share2020prim=1.,CO2prim=.25)])
        e.local=lambda x:x;e.sheet=lambda n:fleets if n=='transport_all' else fuels
        e.long_profiles=lambda n:{'HR1':pd.DataFrame({'cars':np.full(8760,1/8760)},index=range(1,8761))}
        e.price=lambda f,y:70.
        e.build_transport();f=e.fleets[0];activity=e.mobility[f['mode']].sum()
        self.assertAlmostEqual(activity,10e6)
        self.assertAlmostEqual(activity/f['efficiency'],5000.)
        self.assertAlmostEqual(activity*f['co2_per_activity'],1250.)
        self.assertEqual([r['fleet_units'] for r in e.pathway],[100.,100.])
        self.assertEqual([r['activity_share'] for r in e.pathway],[1.,1.])

class CostsAndPublicationTests(unittest.TestCase):
    def test_export_sector_scope_uses_selection_and_retains_legacy_import_behavior(self):
        self.assertEqual(selected_export_sectors({'generated_sectors':['power']}),{'power'})
        self.assertEqual(selected_export_sectors({'generated_sectors':['industry']}),{'power','industry'})
        self.assertEqual(selected_export_sectors({}),{'power','industry','heating','transport'})
        self.assertEqual(selected_export_sectors({'generated_sectors':[]}),{'power','industry','heating','transport'})
        self.assertEqual(selected_export_sectors({'generated_sectors':['power']},'all'),{'power','industry','heating','transport'})
        self.assertEqual(selected_export_sectors({},'electricity,transport'),{'power','transport'})
        for bad in ('none','power,unknown',[]):
            with self.assertRaises(ValueError):selected_export_sectors({},bad)

    def test_gui_requests_additional_export_and_keeps_native_export(self):
        config=dict(countries='HR',spatial_level='country',out_root='prepared',data_root='cache',
                    sector_industry=True,refactored_export=True)
        command=build_command(config)
        self.assertIn('--refactored-export',command);self.assertIn('--model-export',command)
        config['model_export']=False
        with self.assertRaisesRegex(ValueError,'prepared native'):build_command(config)

    def test_gui_opens_the_selected_refactored_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data_refactored').mkdir()
            gui=DataPreparationGui.__new__(DataPreparationGui)
            gui.vars={'out_root':Mock(get=Mock(return_value=tmp))}
            gui.config=Mock(return_value={'refactored_export':True})
            with patch('h2res_input_gui.os.startfile',create=True) as launch:
                gui.open_model_inputs()
            launch.assert_called_once_with(root/'data_refactored')

    def test_million_euros_converted_once_for_exact_generator(self):
        e=CaseExporter.__new__(CaseExporter)
        e.cost_table=pd.DataFrame({'year':[2025,2030],'zone':['HR1','HR1'],'Plant':[.7,.6]})
        e.cost_curves={};e.years=[2025,2030];e.costs=[]
        self.assertEqual(e.cost('Plant','Plant','HR1'),700000.)
        self.assertEqual(e.costs[1]['capital_cost'],600000.)

    def test_national_cost_sheet_selects_country_before_checking_duplicate_years(self):
        e=CaseExporter.__new__(CaseExporter)
        e.countries={'SI1':'SI','HR1':'HR'}
        e.cost_table=pd.DataFrame({'year':[2025,2030,2025,2030],
            'System':['HR','HR','SI','SI'],'SI_Sostanj':[.7,.6,1.5,1.4]})
        e.cost_curves={};e.years=[2025,2030];e.costs=[]
        self.assertEqual(e.cost('SI_Sostanj','SI_Sostanj','SI1'),1500000.)
        self.assertEqual(e.costs[1]['capital_cost'],1400000.)
        self.assertEqual(e.trajectory('SI_Sostanj','HR1'),{2025:700000.,2030:600000.})

    def test_regional_costs_require_both_matching_country_and_zone(self):
        e=CaseExporter.__new__(CaseExporter)
        e.countries={'SI1':'SI'};e.cost_curves={};e.years=[2025]
        e.cost_table=pd.DataFrame({'year':[2025,2025,2025],
            'System':['HR','SI','SI'],'zone':['SI1','SI1','SI2'],'Plant':[.2,1.5,2.]})
        self.assertEqual(e.trajectory('Plant','SI1'),{2025:1500000.})

    def test_missing_country_costs_do_not_silently_use_a_foreign_reference(self):
        e=CaseExporter.__new__(CaseExporter)
        e.countries={'SI1':'SI'};e.cost_curves={};e.years=[2025]
        e.cost_table=pd.DataFrame({'year':[2025],'System':['HR'],'Plant':[.7]})
        with self.assertRaisesRegex(ValueError,'Missing native investment cost'):
            e.trajectory('Plant','SI1')

    def test_duplicate_years_within_the_selected_country_still_fail(self):
        e=CaseExporter.__new__(CaseExporter)
        e.countries={'SI1':'SI'};e.cost_curves={};e.years=[2025]
        e.cost_table=pd.DataFrame({'year':[2025,2025],'System':['SI','SI'],'Plant':[1.,2.]})
        with self.assertRaisesRegex(ValueError,'Ambiguous cost trajectory'):
            e.trajectory('Plant','SI1')

    def test_invalid_investment_values_are_rejected_during_lookup(self):
        for value in [-1.,np.inf]:
            e=CaseExporter.__new__(CaseExporter)
            e.countries={'SI1':'SI'};e.cost_curves={};e.years=[2025]
            e.cost_table=pd.DataFrame({'year':[2025],'System':['SI'],'Plant':[value]})
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Invalid native investment cost'):
                e.trajectory('Plant','SI1')

    def test_failed_export_retains_existing_case_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=root/'data_refactored';case.mkdir();(case/'marker').write_text('old')
            archive=root/'H2RES_refactored_inputs.zip';archive.write_bytes(b'previous')
            with patch('refactored_input_export.CaseExporter',side_effect=ValueError('bad source')):
                with self.assertRaisesRegex(ValueError,'bad source'):export_refactored_bundle(root/'bundle',root)
            self.assertEqual((case/'marker').read_text(),'old');self.assertEqual(archive.read_bytes(),b'previous')
            self.assertTrue((root/'refactored_export_failure.json').is_file())

    def test_carrier_aliases_are_explicit(self):
        self.assertEqual(carrier('H2'),'hydrogen');self.assertEqual(carrier('N2'),'nitrogen')
        self.assertEqual(carrier('fuel_oil'),'oil')

if __name__=='__main__':unittest.main()
