import unittest

import numpy as np
import pandas as pd

from transport.script.activity_units import ensure_energy_column, transport_efficiencies


class TransportEfficiencyTests(unittest.TestCase):
    def test_same_zone_ice_formulas_also_repair_old_model_inputs(self):
        frame = pd.DataFrame({
            "System": ["HR"] * 6, "sector": ["freight"] * 6,
            "zone": ["a"] * 3 + ["b"] * 3,
            "unit_name": ["ICE_truck", "EV_truck", "HYBRID_truck"] * 2,
            "efficiency_primary": [2., .47, 0., 3., np.nan, np.inf],
            "number": [200, 1, 0, 80, 0, 0],
        })
        fleet = transport_efficiencies(frame)
        self.assertEqual(fleet.efficiency_primary.tolist(), [2., 6., 3., 3., 9., 4.5])
        pd.testing.assert_series_equal(frame.number, fleet.number)
        pd.testing.assert_frame_equal(transport_efficiencies(fleet), fleet)

    def test_preserve_observations_and_fill_missing_rail_coefficients(self):
        rail = pd.DataFrame({"sector": ["rail"] * 2, "unit_name": ["ICE_RAIL", "EV_RAIL"],
                             "efficiency_primary": [2., 4.]})
        self.assertEqual(transport_efficiencies(rail).efficiency_primary.tolist(), [2., 4.])
        rail["efficiency_primary"] = [0., -1.]
        np.testing.assert_allclose(transport_efficiencies(rail).efficiency_primary,
                                   [2.0778166653, 3 * 2.0778166653])

    def test_historical_energy_uses_source_efficiency_before_scenario_conversion(self):
        frame = pd.DataFrame({"sector": ["freight"] * 2, "unit_name": ["ICE_truck", "EV_truck"],
                              "total_load": [1., 1.], "efficiency_primary": [2., .5]})
        self.assertEqual(ensure_energy_column(frame, "history").energy_MWh.tolist(), [500., 2000.])
        frame.loc[1, "efficiency_primary"] = 0.
        self.assertAlmostEqual(ensure_energy_column(frame, "history").energy_MWh.iloc[1], 1000. / 6.)
