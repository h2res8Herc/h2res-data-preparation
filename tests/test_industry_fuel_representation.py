"""Check native fuel compatibility while preserving regional industrial service."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from industry.fuel_representation import redistribute_service_mix, regular_complex_aggregate
from industry.generate_industry_inputs_standalone import FUEL_DEFAULTS, write_model_ready_industry_data
from model_input_bundle import industry_parameters


class IndustryFuelRepresentationTests(unittest.TestCase):
    def test_proportional_mix_never_allocates_to_feedstocks_or_unbuilt_hydrogen(self):
        source = dict(Gas=60., Electricity=20., heat=12., waste=8., non_energy=100., Hydrogen=0.)
        result, audit = redistribute_service_mix(source)
        self.assertEqual(result, dict(Gas=75., Electricity=25., non_energy=100., Hydrogen=0.))
        self.assertAlmostEqual(sum(result.values()), sum(source.values()))
        self.assertEqual(sum(row['added_service_weight'] for row in audit), 20.)
        self.assertEqual([r['recipient_fraction'] for r in audit], [.25, .75])

    def test_service_without_incumbents_uses_local_mix_then_explicit_gas_default(self):
        result, audit = redistribute_service_mix(dict(heat=20., non_energy=5.), dict(Biomass=3., Gas=1.))
        self.assertEqual(result, dict(non_energy=5., Biomass=15., Gas=5.))
        self.assertIn('other_categories', audit[0]['basis'])
        result, audit = redistribute_service_mix(dict(waste=20., non_energy_gas=5.))
        self.assertEqual(result, dict(non_energy_gas=5., Gas=20.))
        self.assertEqual(audit[0]['basis'], 'assumed_gas_no_supported_incumbent')

    def test_invalid_service_is_rejected(self):
        for value in (-1, np.inf, np.nan):
            with self.assertRaises(ValueError):
                redistribute_service_mix(dict(heat=value, Gas=10))

    def test_regular_and_category_generation_preserve_service_and_geography(self):
        rows = []
        for zone, multiplier in [('HR028', 1.), ('HR050', 2.)]:
            for category, fuels in [('100-400C', dict(Gas=60., Electricity=20., heat=12., waste=8., non_energy_gas=100.)),
                                    ('<100C', dict(heat=20.))]:
                for fuel, service in fuels.items():
                    cf = 1. if fuel in {'Electricity', 'heat'} else .85
                    rows.append(dict(System='HR', zone=zone, Industry='Chemical and petrochemical [' + category + ']',
                                     fuel_type=fuel, cap_mw=service * multiplier / cf / FUEL_DEFAULTS[fuel][2],
                                     share_fuel_2020=0.))
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / 'units.csv'
            pd.DataFrame(rows).to_csv(source, index=False)
            category = write_model_ready_industry_data(source, root, True, False, 'category.csv', False)
            ordinary = write_model_ready_industry_data(source, root, False, False, 'regular.csv', False)
            efuel = write_model_ready_industry_data(source, root, True, True, 'efuel.csv', False)
            self.assertFalse(category.fuel_type.isin(['heat', 'waste']).any())
            self.assertFalse(ordinary.fuel_type.isin(['heat', 'waste']).any())
            self.assertTrue(efuel.fuel_type.isin(['heat', 'waste']).any())
            for frame in (category, ordinary):
                cf = frame.fuel_type.map({'Electricity': 1.}).fillna(.85)
                useful = frame.cap_mw * cf * frame.efficiency
                totals = useful.groupby(frame.zone).sum()
                np.testing.assert_allclose(totals.reindex(['HR028', 'HR050']), [220., 440.])
                self.assertTrue((frame.max_share_fuel >= frame.share_fuel_2020).all())
            gas = category.loc[category.zone.eq('HR028') & category.category.eq('100_400C') & category.fuel_type.eq('Gas')].iloc[0]
            self.assertAlmostEqual(gas.cap_mw * .85 * gas.efficiency, 75.)
            feedstock = ordinary.loc[ordinary.zone.eq('HR028') & ordinary.fuel_type.eq('non_energy')].iloc[0]
            self.assertAlmostEqual(feedstock.cap_mw * .85 * feedstock.efficiency, 100.)
            keys = ['System', 'zone', 'Industry', 'fuel_type']
            np.testing.assert_allclose(category.groupby(keys).cap_mw.sum(), ordinary.set_index(keys).cap_mw.sort_index())
            audit = pd.read_csv(root / 'category_fuel_redistribution.csv')
            self.assertAlmostEqual(audit.added_service_weight.sum(), 120.)

    def test_complex_ordinary_remainder_preserves_process_data_and_service(self):
        source = pd.DataFrame(dict(System='HR', zone='HR028', Industry='Chemical', category='all',
            fuel_type=['Gas', 'Electricity', 'heat', 'non_energy_gas'],
            unit_name=['Gas_industry', 'Electricity_industry', 'heat_industry', 'non_energy_gas_industry'],
            cap_mw=[60., 20., 20., 100.], share_fuel_2020=[.3, .1, .1, .5],
            max_share_fuel=[.3, .5, .15, .5], max_cap=5000., efficiency=.9, include_in_the_model='Y'))
        before = source.copy(deep=True)
        adapted, audit = regular_complex_aggregate(source, source)
        pd.testing.assert_frame_equal(source, before)
        self.assertFalse(adapted.fuel_type.isin(['heat', 'waste']).any())
        self.assertEqual(adapted.cap_mw.sum(), 200.)
        self.assertAlmostEqual(adapted.share_fuel_2020.sum(), 1.)
        self.assertEqual(adapted.loc[adapted.fuel_type.eq('Gas'), 'cap_mw'].item(), 75.)
        self.assertEqual(adapted.loc[adapted.fuel_type.eq('non_energy_gas'), 'cap_mw'].item(), 100.)
        self.assertTrue((adapted.max_share_fuel >= adapted.share_fuel_2020).all())
        self.assertEqual(sum(r['added_service_weight'] for r in audit), 20.)
        # Native process-derived aggregate sheets omit the ordinary max_cap
        # column; adaptation must work without adding a different schema.
        minimal, _ = regular_complex_aggregate(source.drop(columns='max_cap'), source.drop(columns='max_cap'))
        self.assertNotIn('max_cap', minimal)
        self.assertEqual(minimal.cap_mw.sum(), 200.)
        only_heat = source.loc[source.fuel_type.isin(['Gas', 'heat'])].copy()
        only_heat.loc[only_heat.fuel_type.eq('Gas'), 'cap_mw'] = 0.
        fallback, notes = regular_complex_aggregate(only_heat, source)
        self.assertEqual(fallback.unit_name.tolist(), ['Gas_industry'])
        self.assertEqual(fallback.cap_mw.item(), 20.)
        self.assertEqual(fallback.share_fuel_2020.item(), 1.)
        self.assertEqual(notes[0]['basis'], 'assumed_gas_no_supported_incumbent')

    def test_export_rejects_stale_prepared_heat_waste_for_regular_reference(self):
        generated = pd.DataFrame(dict(fuel_type=['Gas', 'heat', 'waste']))
        reference = pd.DataFrame(dict(fuel_type=['Gas']))
        with self.assertRaisesRegex(ValueError, 'Regenerate Industry using cached downloads'):
            industry_parameters(generated, reference)


if __name__ == '__main__':
    unittest.main()
