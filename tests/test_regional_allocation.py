"""Regional data must differ for a reason and conserve their national margins."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from industry.regional_allocation import allocate_margins, raster_totals
from default_model_inputs import allocation_weights, complete_defaults, default_rows, quantity_columns
from regional_input_quality import check_prepared_industry
from industry.regional_allocation import file_hash
from h2res_input_gui import build_command


class RegionalAllocationTests(unittest.TestCase):
    def setUp(self):
        self.national = pd.DataFrame([
            ("steel", "high", "gas", 80.), ("paper", "low", "gas", 20.),
            ("steel", "high", "coal", 30.), ("paper", "low", "coal", 10.),
            ("steel", "high", "heat", 5.), ("paper", "low", "heat", 5.),
        ], columns=["sector", "category", "fuel", "national_total_MWh"])
        self.sites = pd.DataFrame([(z, b, 1.) for z in ("a", "b") for b in ("steel", "paper")],
                                  columns=["nuts", "branch", "weight"])
        self.rasters = pd.DataFrame(dict(gas=[1., 3.], solid=[4., 1.], others=[0., 100.], heat=[0., 0.]), index=["a", "b"])

    def test_rebases_geography_to_every_national_sector_category_fuel_margin(self):
        result, notes = allocate_margins(self.national, ["a", "b"], self.sites, self.rasters)
        expected = self.national.set_index(["sector", "category", "fuel"]).national_total_MWh.sort_index()
        actual = result.rename(columns={"branch": "sector"}).groupby(["sector", "category", "fuel"]).MWh.sum().sort_index()
        np.testing.assert_allclose(actual, expected, rtol=1e-10)
        gas = result[result.fuel.eq("gas")].groupby("nuts").MWh.sum()
        np.testing.assert_allclose(gas, [25., 75.])
        coal = result[result.fuel.eq("coal")].groupby("nuts").MWh.sum()
        np.testing.assert_allclose(coal, [32., 8.])  # Solid fuels, not the "others" map.
        self.assertIn("combined industrial", next(n for n in notes if n['fuel']=='heat')['basis'])

    def test_implicit_equal_geography_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no usable EIGL"):
            allocate_margins(self.national, ["a", "b"], self.sites, pd.DataFrame())
        result, notes = allocate_margins(self.national, ["a", "b"], self.sites, pd.DataFrame(), equal=True)
        np.testing.assert_allclose(result.groupby("nuts").MWh.sum(), [75., 75.])
        self.assertTrue(all("explicit equal" in note['basis'] for note in notes))

    def test_facility_branch_prior_is_used_without_losing_a_region(self):
        sites = self.sites.copy()
        sites['weight'] = [8., 1., 1., 8.]
        result, _ = allocate_margins(self.national, ["a", "b"], sites, self.rasters)
        gas = result[result.fuel.eq("gas")].pivot(index="nuts", columns="branch", values="MWh")
        self.assertGreater(gas.at['a','steel']/gas.loc['a'].sum(), gas.at['b','steel']/gas.loc['b'].sum())
        np.testing.assert_allclose(gas.sum(axis=0).sort_index(), [20.,80.])

    def test_national_zone_does_not_require_a_regional_map(self):
        result, notes = allocate_margins(self.national, ["a"], self.sites, pd.DataFrame())
        self.assertAlmostEqual(result.MWh.sum(), 150.)
        self.assertTrue(all(n['basis']=='single national zone' for n in notes))

    def test_raster_pixels_are_not_counted_twice_at_county_boundaries(self):
        import geopandas as gpd
        import rasterio
        from rasterio.transform import from_origin
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'electricity_ind_demand_2019.tif'
            with rasterio.open(path, 'w', driver='GTiff', width=2, height=1, count=1,
                               dtype='float32', crs='EPSG:3035', transform=from_origin(0,1,1,1), nodata=-999) as f:
                f.write(np.array([[1.,3.]],dtype='float32'),1)
            nuts = gpd.GeoDataFrame(dict(NUTS_ID=['a','b']),geometry=[box(0,0,1,1),box(1,0,2,1)],crs='EPSG:3035')
            totals, sources = raster_totals(directory, nuts, '2019')
            self.assertEqual(totals.electricity.tolist(), [1.,3.])
            self.assertEqual(len(sources[0]['sha256']),64)


class RegionalDefaultTests(unittest.TestCase):
    def test_native_long_electricity_demand_supplies_country_normalized_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            pd.DataFrame(dict(period=[1,2,1,2,1],System=['HR','HR','HR','HR','IT'],
                              Zone=['HR021','HR021','HR022','HR022','IT1'],Power=[1.,1.,3.,3.,100.])).to_csv(root/'electricity_demand.csv',index=False)
            targets={('HR','HR021'),('HR','HR022')}
            weights=allocation_weights(root,targets)
            self.assertEqual(weights['electricity'],{('HR','HR021'):.25,('HR','HR022'):.75})
            pd.DataFrame(dict(period=[1,2],HR1=[0.,0.])).to_csv(root/'cooling_district.csv',index=False)
            complete_defaults(root,targets,['electricity_demand.csv'],[],'unused.xlsx',[])
            cooling=pd.read_csv(root/'cooling_district.csv')
            self.assertEqual(cooling.HR021.sum(),0.)

    def test_national_stocks_are_split_and_efficiency_is_preserved(self):
        frame = pd.DataFrame(dict(System=['HR'],zone=['HR1'],cap_mw=[500.],max_cap=[1000.],efficiency=[.9]))
        targets = {('HR','HR021'),('HR','HR022')}
        result, notes = default_rows(frame,targets,weights={('HR','HR021'):.25,('HR','HR022'):.75},
                                     quantities=quantity_columns(frame),weight_basis='prepared electricity demand')
        local = result[result.zone.ne('HR1')]
        self.assertEqual(local.cap_mw.tolist(),[125.,375.])
        self.assertEqual(local.max_cap.sum(),1000.)
        self.assertEqual(local.efficiency.tolist(),[.9,.9])
        self.assertEqual(notes[0]['allocation_weight'],.25)

    def test_annual_nh3_quantity_scales_but_prices_do_not(self):
        frame = pd.DataFrame({'System':['HR'],'zone':['HR1'],2020:[10.],2050:[20.]})
        self.assertEqual(quantity_columns(frame,'NH3_demand'),[2020,2050])
        self.assertEqual(quantity_columns(frame,'Import_Price'),[])

    def test_hourly_absolute_defaults_scale_but_normalized_shapes_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            pd.DataFrame(dict(period=[1,2],HR021=[1.,1.],HR022=[3.,3.])).to_csv(root/'electricity_demand.csv',index=False)
            for name, curve in [('heating_individual.csv',[8.,12.]),('nh3_demand.csv',[.4,.6]),('solar_thermal_availability.csv',[.2,.7])]:
                pd.DataFrame(dict(period=[1,2],HR1=curve)).to_csv(root/name,index=False)
            complete_defaults(root,{('HR','HR021'),('HR','HR022')},['electricity_demand.csv'],[],'unused.xlsx',[])
            heat=pd.read_csv(root/'heating_individual.csv')
            self.assertEqual(heat.HR021.tolist(),[2.,3.])
            self.assertEqual(heat.HR022.tolist(),[6.,9.])
            profile=pd.read_csv(root/'nh3_demand.csv')
            self.assertEqual(profile.HR021.tolist(),[.4,.6])
            self.assertEqual(pd.read_csv(root/'solar_thermal_availability.csv').HR022.tolist(),[.2,.7])


class RegionalQualityTests(unittest.TestCase):
    def test_category_mode_receives_the_selected_national_year_and_allocation_setting(self):
        command = build_command(dict(countries='HR',spatial_level='nuts3',out_root='out',data_root='cache',
                                     sector_industry=True,industry_mode='categories',industry_base_year='2021',
                                     industry_regional_allocation='equal'))
        self.assertEqual(command[command.index('--industry-base-year')+1],'2021')
        self.assertEqual(command[command.index('--industry-regional-allocation')+1],'equal')

    def fixture(self, root):
        (root/'_zone_maps').mkdir()
        pd.DataFrame(dict(country=['HR','HR'],zone=['a','b'])).to_csv(root/'_zone_maps/zone_map_common.csv',index=False)
        base=root/'industry/combined'
        base.mkdir(parents=True)
        pd.DataFrame(dict(System=['HR','HR'],zone=['a','b'],all=[1.,3.])).to_csv(base/'industry_heat.csv',index=False)
        args=SimpleNamespace(out_root=root,sectors=['industry'],industry_mode='categories',countries=['HR'],
                             industry_base_year=2020,industry_regional_allocation='require-weights')
        return args,base

    def provenance(self, base):
        report=dict(method='JRC margins and facility activity shares',method_id='paper_facility_activity_v1',national_energy_year=2020,
                    regional_totals={'a':1.,'b':3.},
                    national_sector_category_fuel_conserved=True,fuels=[dict(basis='EIGL industrial gas raster')],
                    sources=[],spatial_data_kind='modelled spatial proxy',raster_year='2019')
        metadata=dict(countries=dict(HR=report),files={'industry_heat.csv':file_hash(base/'industry_heat.csv')})
        (base/'regional_generation.json').write_text(json.dumps(metadata),encoding='utf-8')

    def test_old_regional_outputs_need_regeneration_and_changed_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args,base=self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError,'Regenerate Industry'):
                check_prepared_industry(args)
            self.provenance(base)
            self.assertTrue(check_prepared_industry(args)['industry']['HR']['national_sector_category_fuel_conserved'])
            (base/'industry_heat.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed after allocation'):
                check_prepared_industry(args)

    def test_accidental_equal_demand_is_not_approved_by_format_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            args,base=self.fixture(Path(directory))
            pd.DataFrame(dict(System=['HR','HR'],zone=['a','b'],all=[2.,2.])).to_csv(base/'industry_heat.csv',index=False)
            self.provenance(base)
            with self.assertRaisesRegex(ValueError,'disagrees with the facility allocation'):
                check_prepared_industry(args)


if __name__ == '__main__':
    unittest.main()
