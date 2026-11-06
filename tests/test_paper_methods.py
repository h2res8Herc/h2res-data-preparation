"""Check the spatial evidence, conservation and cache boundaries in the paper method."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, LineString, Point

from heating.method_provenance import raw_cache_matches
from heating.paper_weather import sample_region, regional_hdd
from industry.facility_sources import assign_regions, branch_weights, nace_branch, observations
from industry.regional_allocation import allocate_facility_margins
from regional_input_quality import check_prepared_methods
from sector_method_provenance import file_hash, sources
from transport.script.osm_infrastructure import measure, read_features, weights
from transport.script.activity_units import ensure_energy_column


class PaperMethodsTests(unittest.TestCase):
    def test_transport_diagnostic_energy_converts_million_activity_to_mwh(self):
        national = pd.DataFrame({'total_load':[20_000.,0.],'efficiency_primary':[2.,0.]})
        self.assertEqual(ensure_energy_column(national,'cars').energy_MWh.sum(),10_000_000.)
        explicit = national.assign(energy_MWh=[9_500_000.,0.])
        self.assertEqual(ensure_energy_column(explicit,'cars').energy_MWh.sum(),9_500_000.)
        with self.assertRaisesRegex(ValueError,'no valid primary efficiency'):
            ensure_energy_column(national.assign(efficiency_primary=0.),'cars')

    def test_industrial_classification_excludes_refineries_and_energy_transformation(self):
        expected = {'20.15':'chemicals_petrochem', '19.20':None, '22.22':'nes_industry',
                    '24.53':'non_ferrous_metals', '35.11':None, '07.10':'mining_quarrying',
                    '05.10':None, '29.10':'transport_equipment', '25.11':'machinery'}
        for code, branch in expected.items():
            with self.subTest(code=code):
                self.assertEqual(nace_branch(code), branch)

    def test_greek_registry_code_is_joined_to_gisco_el_regions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pd.DataFrame([dict(id='GR_1',name='Chemical plant',registry_id='GR',activity_name='Production of ammonia')]).to_csv(root/'installations.csv',index=False)
            pd.DataFrame([dict(installation_id='GR_1',year=2020,verified=100.)]).to_csv(root/'compliance.csv',index=False)
            pd.DataFrame([dict(installation_id='GR_1',longitude=.5,latitude=.5)]).to_csv(root/'installation_locations.csv',index=False)
            pd.DataFrame([dict(installation_id='GR_1',nace_2020=20.15,nace_2015=20.15)]).to_csv(root/'nace_mappings.csv',index=False)
            (root/'ied.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=[])))
            nuts=gpd.GeoDataFrame({'NUTS_ID':['EL111']},geometry=[box(0,0,1,1)],crs=4326)
            ets,ied,extra=observations(root,root/'ied.geojson','EL',2020,nuts)
            self.assertEqual(ets.nuts.tolist(),['EL111'])
            self.assertEqual(ets.branch.tolist(),['chemicals_petrochem'])

    def test_installation_coordinates_control_the_county_even_with_a_different_head_office(self):
        nuts = gpd.GeoDataFrame({'NUTS_ID':['plant_county','capital']},
                                geometry=[box(0,0,1,1),box(1,0,2,1)],crs=4326)
        sites = pd.DataFrame({'facility_id':['factory','boundary'], 'longitude':[.2,1.],
                              'latitude':[.2,.5], 'operator_city':['capital','capital']})
        actual = assign_regions(sites,nuts).set_index('facility_id')
        self.assertEqual(actual.loc['factory','nuts'],'plant_county')
        self.assertEqual(len(actual),2)  # No duplicated boundary installation.

    def test_sector_activity_is_not_diluted_by_a_second_inventory_or_population(self):
        ets = pd.DataFrame({'nuts':['a','b'],'branch':['chem','chem'],'metric':[9.,1.]})
        ied = pd.DataFrame({'nuts':['a','b'],'branch':['chem','chem'],'metric':[1.,9.]})
        actual, choices = branch_weights(ets,ied,['a','b'],branches=['chem','uncovered'])
        np.testing.assert_allclose(actual.loc[actual.branch.eq('chem'),'weight'],[.9,.1])
        np.testing.assert_allclose(actual.loc[actual.branch.eq('uncovered'),'weight'],[.1,.9])
        self.assertFalse(choices[0]['assumption'])
        self.assertTrue(choices[1]['assumption'])
        with self.assertRaisesRegex(ValueError,'No industrial facility evidence'):
            branch_weights(ets.iloc[:0],ied.iloc[:0],['a','b'],branches=['uncovered'])

    def test_facility_allocation_conserves_each_margin_and_keeps_real_zero_regions(self):
        national = pd.DataFrame([('chem','NON_HEAT','gas',100.),('chem','HIGH','oil',20.),
                                 ('paper','LOW','gas',30.)],
                                columns=['sector','category','fuel','national_total_MWh'])
        shares = pd.DataFrame([('a','chem',1.),('b','chem',0.),('a','paper',.2),('b','paper',.8)],
                              columns=['nuts','branch','weight'])
        actual = allocate_facility_margins(national,shares)
        np.testing.assert_allclose(actual.groupby(['branch','category','fuel']).MWh.sum().sort_index(),
                                   national.set_index(['sector','category','fuel']).national_total_MWh.sort_index())
        self.assertEqual(actual.loc[actual.nuts.eq('b') & actual.branch.eq('chem'),'MWh'].sum(),0.)
        with self.assertRaisesRegex(ValueError,'sum to one'):
            allocate_facility_margins(national,shares.assign(weight=1.))

    def population_grid(self,path):
        with rasterio.open(path,'w',driver='GTiff',width=4,height=4,count=1,dtype='float32',
                           crs='EPSG:4326',transform=from_origin(0,4,1,1),nodata=-9999) as raster:
            raster.write(np.arange(1,17,dtype='float32').reshape(4,4),1)

    def test_weather_uses_eight_reproducible_inhabited_points_with_population_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            raster = Path(folder)/'population.tif'
            self.population_grid(raster)
            first = sample_region(box(0,0,4,4),4326,raster,'zone',8,0)
            second = sample_region(box(0,0,4,4),4326,raster,'zone',8,0)
            pd.testing.assert_frame_equal(first,second)
            self.assertEqual(len(first),8)
            self.assertEqual(first[['longitude','latitude']].drop_duplicates().shape[0],8)
            np.testing.assert_allclose(first.weight,first.population/first.population.sum())
            self.assertTrue(all(box(0,0,4,4).contains(Point(r.longitude,r.latitude)) for r in first.itertuples()))
            nuts = gpd.GeoDataFrame({'NUTS_ID':['zone']},geometry=[box(0,0,4,4)],crs=4326)
            def weather(path,*,lon,lat,year,verbose=False):
                return np.full(8760,lon)
            stats, hourly = regional_hdd(pd.DataFrame({'nuts3_id':['zone'],'pop_sum':[100.]}),
                                         nuts,raster,Path(folder),2021,18.,1.,1.,weather)
            np.testing.assert_allclose(hourly['zone'],18.-np.average(first.longitude,weights=first.weight))
            self.assertAlmostEqual(stats.w_base.sum(),1.)

    def test_transport_lengths_are_clipped_and_boundary_points_count_once(self):
        nuts = gpd.GeoDataFrame({'NUTS_ID':['a','b']},geometry=[box(0,0,1000,1000),box(1000,0,2000,1000)],crs=3035)
        rail = gpd.GeoDataFrame(geometry=[LineString([(500,500),(1500,500)])],crs=3035)
        np.testing.assert_allclose(measure(rail,nuts,'length'),[.5,.5])
        stations = gpd.GeoDataFrame(geometry=[Point(1000,500)],crs=3035)
        self.assertEqual(measure(stations,nuts,'count').sum(),1.)

    def test_real_osm_parser_and_coastal_shipping_constraint(self):
        with tempfile.TemporaryDirectory() as folder:
            osm = Path(folder)/'test.osm'
            osm.write_text('''<?xml version="1.0"?><osm version="0.6">
<node id="1" lat=".2" lon=".2"><tag k="railway" v="station"/></node>
<node id="2" lat=".8" lon="1.8"/>
<node id="3" lat=".3" lon=".3"><tag k="harbour" v="yes"/></node>
<node id="4" lat=".3" lon="1.3"><tag k="harbour" v="yes"/></node>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="railway" v="rail"/><tag k="electrified" v="contact_line"/></way>
</osm>''',encoding='utf-8')
            nuts = gpd.GeoDataFrame({'NUTS_ID':['coast','inland']},
                                    geometry=[box(0,0,1,1),box(1,0,2,1)],crs=4326)
            rail, shipping, aviation, proof = weights(nuts,osm,{'coast':1,'inland':3})
            self.assertEqual(proof['feature_counts']['rail_lines'],1)
            self.assertTrue(rail.rail_main_km_el.gt(0).all())
            self.assertGreater(shipping.loc[0,'ship_passenger'],0.)
            self.assertEqual(shipping.loc[1].sum(),0.)
            read_features.cache_clear()

    def test_heating_cache_rejects_legacy_empty_or_changed_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity = {'fingerprint':'new_method'}
            self.assertFalse(raw_cache_matches(root,identity))
            target = root/'annual.csv'
            target.write_text('correct')
            manifest = root/'paper_generation.json'
            manifest.write_text(json.dumps(dict(fingerprint='new_method',complete=True,outputs={})))
            self.assertFalse(raw_cache_matches(root,identity))
            manifest.write_text(json.dumps(dict(fingerprint='new_method',complete=True,outputs={'annual.csv':file_hash(target)})))
            self.assertTrue(raw_cache_matches(root,identity))
            target.write_text('stale')
            self.assertFalse(raw_cache_matches(root,identity))

    def test_export_checks_nested_method_sources_not_just_the_final_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'_zone_maps').mkdir()
            pd.DataFrame({'country':['HR','HR'],'zone':['a','b']}).to_csv(root/'_zone_maps/zone_map_common.csv',index=False)
            (root/'transport/combined').mkdir(parents=True)
            raw = root/'registry.csv'
            raw.write_text('original')
            calculation = root/'calculation.json'
            calculation.write_text(json.dumps({'sources':sources([raw])}))
            output = root/'transport/combined/transport_all.csv'
            output.write_text('correct')
            (output.parent/'paper_generation.json').write_text(json.dumps(dict(method_id='paper_transport_v1',
                files={output.name:file_hash(output)},sources=sources([calculation]))))
            args = SimpleNamespace(out_root=root,sectors=['transport'])
            self.assertEqual(check_prepared_methods(args)['transport']['method_id'],'paper_transport_v1')
            raw.write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):
                check_prepared_methods(args)


if __name__ == '__main__':
    unittest.main()
