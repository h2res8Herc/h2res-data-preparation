"""Landlocked domestic navigation must conserve activity without becoming sea shipping."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from transport.script import generate_transport_inputs_standalone as generator
from transport.script.activity_units import ensure_energy_column
from transport.script.navigation_allocation import allocate_table, navigation_kind, METHOD


def embedded_allocator():
    module = ModuleType('navigation_allocator_test')
    exec(compile(generator.embedded_bytes('allocator'), '<bundled transport allocator>', 'exec'), module.__dict__)
    return module


class NavigationAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allocator = embedded_allocator().allocate_table_to_nuts3_complete

    def source(self, load=1998., international=0.):
        return pd.DataFrame(dict(sector=['Domestic shipping', 'international shipping'],
            unit_name=['ICE_MARINE_DOM', 'ICE_MARINE_INT'], type='ICE',
            total_load=[load, international], number=[0., 0.], energy_MWh=[load * 1000 / 20.957895, international * 1000],
            efficiency_primary=[20.957895, 1.]))

    def allocate(self, source, coast, sea, river):
        ids = ['HU001', 'HU002', 'HU003']
        shipping = pd.DataFrame(dict(ship_freight=sea, ship_passenger=sea,
                                     ship_inland_freight=river, ship_inland_passenger=river))
        notes = []
        result = allocate_table(type(self).allocator, source, ids, {}, 'freight', dict(zip(ids, coast)), shipping, notes)
        return result, notes

    def test_hungary_navigation_uses_ports_and_preserves_real_national_totals(self):
        source = self.source()
        result, notes = self.allocate(source, [3, 3, 3], [0, 0, 0], [2., 0., 1.])
        domestic = result.loc[result.sector.eq('Domestic shipping')]
        np.testing.assert_allclose(domestic.total_load, [1332., 0., 666.])
        self.assertAlmostEqual(domestic.energy_MWh.sum(), source.energy_MWh.sum())
        self.assertTrue(domestic.navigation_kind.eq('inland_navigation').all())
        self.assertTrue(result.loc[result.sector.eq('international shipping'), 'total_load'].eq(0).all())
        self.assertEqual(notes[0]['eligible_regions'], ['HU001', 'HU003'])

    def test_coastal_country_keeps_sea_shipping_out_of_inland_regions(self):
        result, _ = self.allocate(self.source(international=100.), [1, 3, 2], [2., 0., 1.], [2., 10., 1.])
        self.assertTrue(result.loc[result.nuts3.eq('HU002'), ['total_load', 'number', 'energy_MWh']].eq(0).all().all())
        self.assertAlmostEqual(result.total_load.sum(), 2098.)

    def test_missing_coastal_ports_can_only_fall_back_to_coastal_regions(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result, notes = self.allocate(self.source(), [1, 3, 2], [0., 0., 0.], [0., 0., 0.])
        np.testing.assert_allclose(result.loc[result.sector.eq('Domestic shipping'), 'total_load'], [999., 0., 999.])
        self.assertEqual(notes[0]['weights_basis'], 'assumed_equal_coastal_regions_no_OSM_port_proxy')

    def test_missing_inland_infrastructure_does_not_trigger_uniform_allocation(self):
        with self.assertRaisesRegex(ValueError, 'no OSM port/quay evidence'):
            self.allocate(self.source(), [3, 3, 3], [0., 0., 0.], [0., 0., 0.])

    def test_positive_sea_shipping_in_landlocked_country_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Sea shipping has positive activity'):
            self.allocate(self.source(international=100.), [3, 3, 3], [0., 0., 0.], [2., 0., 1.])

    def test_zero_shipping_needs_no_ports_and_keeps_complete_grid(self):
        result, _ = self.allocate(self.source(load=0.), [3, 3, 3], [0., 0., 0.], [0., 0., 0.])
        self.assertEqual(len(result), 6)
        self.assertTrue(result[['total_load', 'number', 'energy_MWh']].eq(0).all().all())

    def test_domestic_navigation_and_international_shipping_are_different_kinds(self):
        self.assertEqual(navigation_kind('Domestic shipping', 'ICE_MARINE_DOM', False), 'inland_navigation')
        self.assertEqual(navigation_kind('international shipping', 'ICE_MARINE_INT', False), 'maritime')
        self.assertEqual(navigation_kind('Passenger cars', 'ICE_car', False), None)

    def test_full_offline_transport_pipeline_with_hungary_source_snapshot(self):
        import osmium
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ids = ['HU001', 'HU002', 'HU003']
            nuts = root / 'nuts.geojson'
            gpd.GeoDataFrame(dict(NUTS_ID=ids, CNTR_CODE='HU', LEVL_CODE=3, COAST_TYPE=3),
                geometry=[box(i * .01, 0, (i + 1) * .01, .01) for i in range(3)], crs=4326).to_file(nuts, driver='GeoJSON')
            osm = root / 'osm'
            osm.mkdir()
            with osmium.SimpleWriter(str(osm / 'HU.osm.pbf')) as writer:
                for index, lon in enumerate((.002, .003, .022), 1):
                    writer.add_node(osmium.osm.mutable.Node(id=index, location=(lon, .005), tags={'industrial':'port', 'harbour':'yes'}))
            raster = root / 'road.tif'
            with rasterio.open(raster, 'w', driver='GTiff', width=3, height=1, count=1,
                dtype='float32', crs='EPSG:4326', transform=from_origin(0, .01, .01, .01)) as stream:
                stream.write(np.array([[1., 2., 3.]], dtype='float32'), 1)
            output = root / 'output'
            args = ['--countries', 'HU', '--nuts3', str(nuts), '--pbf-dir', str(osm), '--data-dir', str(root / 'cache'),
                    '--oil-raster', str(raster), '--el-raster', str(raster), '--out-root', str(output)]
            log = io.StringIO()
            with patch.object(sys, 'path', [str(generator.SCRIPT_DIR), *sys.path]), contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                result = generator.main(args)
            self.assertEqual(result, 0, log.getvalue())
            proof = json.loads((output / 'combined/paper_generation.json').read_text(encoding='utf-8'))
            self.assertEqual(proof['countries']['HU']['navigation_method'], METHOD)
            self.assertTrue(proof['countries']['HU']['inland_navigation_present'])
            self.assertTrue(proof['countries']['HU']['maritime_inland_zero'])
            self.assertTrue(proof['countries']['HU']['national_conservation']['freight']['conserved'])
            raw = pd.read_csv(output / 'HU/transp1_shape_freight_NUTS3.csv')
            domestic = raw.loc[raw.sector.eq('Domestic shipping')]
            np.testing.assert_allclose(domestic.total_load, [1332., 0., 666.])
            fleet = pd.read_csv(output / 'combined/transport_all.csv')
            self.assertIn('ICE_MARINE_SHORT', set(fleet.unit_name))
            self.assertNotIn('ICE_MARINE_DOM', set(fleet.unit_name))
            self.assertTrue((output / 'combined/transport_inputs.xlsx').is_file())
            self.assertEqual(len(pd.read_csv(output / 'combined/transport_profiles.csv')), 3 * 8760)


if __name__ == '__main__':
    unittest.main()
