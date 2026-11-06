"""Regression checks for quantities and the actual model reader interface."""
import importlib.util
import io
import re
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h2res_input_schema import annual_limits, industry_category, industry_label, model_calendar, transport_identifiers
from model_input_bundle import industry_parameters, pooled_industry, replace_sheets, selected_complex_workbook, selected_workbook, sheet_paths, transport_parameters
from h2res_input_gui import build_command


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class SchemaTests(unittest.TestCase):
    def test_leap_calendar_drops_only_february_29(self):
        timestamps = pd.date_range("2020-01-01", "2020-12-31 23:00", freq="h", tz="UTC")
        source = pd.DataFrame({"time": timestamps, "power": np.arange(8784)})
        result = model_calendar(source)
        self.assertEqual(len(result), 8760)
        self.assertEqual(result.iloc[-1].power, 8783)
        self.assertEqual(result.period.tolist(), list(range(1, 8761)))

    def test_calendar_rejects_unexplained_missing_hours(self):
        with self.assertRaises(ValueError):
            model_calendar(pd.DataFrame({"period": range(1, 8760), "x": 1}))

    def test_limits_preserve_zero_blank_and_edited_year(self):
        source = pd.DataFrame({"max_inv_period": [10., 0., np.nan], "max_inv_period_2030": [7., 0., np.nan]})
        result = annual_limits(source)
        self.assertEqual(result.max_inv_period_2026.iloc[0], 10)
        self.assertEqual(result.max_inv_period_2030.iloc[0], 7)
        self.assertEqual(result.max_inv_period_2026.iloc[1], 0)
        self.assertTrue(pd.isna(result.max_inv_period_2026.iloc[2]))
        self.assertTrue(result.CC_max_inv_period_2026.isna().all())

    def test_invalid_limits_rejected_in_years_outside_horizon(self):
        for value in (-1, np.inf, "bad"):
            with self.assertRaises(ValueError):
                annual_limits(pd.DataFrame({"max_inv_period_2070": [value]}))

    def test_current_identifiers(self):
        self.assertEqual(industry_label("Not elsewhere specified (industry) [<100C]"), "Not_elsewhere_specified_(industry)")
        self.assertEqual(industry_category("Iron and steel [100-400C]"), "100_400C")
        self.assertEqual(selected_workbook(True, "categories"), "flex_tech_efuel_categories.xlsx")
        self.assertEqual(selected_workbook(True, "categories", "technical_2050"), "variants/technical_2050/flex_tech_efuel_categories.xlsx")
        self.assertEqual(selected_workbook(False, "complex"), "flex_tech_complex_industry.xlsx")
        self.assertEqual(selected_complex_workbook(True, "technical_2050"), "industry_complex_efuel_electricity_technical_2050.xlsx")

    def test_cached_shipping_profiles_use_current_units_without_changing_values(self):
        legacy = pd.DataFrame({"period": [1, 2], "ICE_MARINE_DOM": [.4, .6], "ICE_MARINE_INT": [.7, .3]})
        current = transport_identifiers(legacy)
        self.assertEqual(current.columns.tolist(), ["period", "ICE_MARINE_SHORT", "ICE_MARINE_LONG"])
        np.testing.assert_array_equal(current.to_numpy(), legacy.to_numpy())
        with self.assertRaisesRegex(ValueError, "duplicate unit columns"):
            transport_identifiers(legacy.assign(ICE_MARINE_SHORT=.5))

    def test_sheet_patch_preserves_unrelated_xml_and_cached_formulas(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.xlsx"
            book = Workbook()
            book.active.title = "Industry_data"
            book.active.append(["old"])
            sheet = book.create_sheet("keep")
            sheet["A1"] = "=3*4"
            book.save(path)
            # Add a cached formula result, as in the real model workbooks.
            with ZipFile(path) as original:
                members = {entry.filename: original.read(entry.filename) for entry in original.infolist()}
                keep = sheet_paths(original)["keep"]
            members[keep] = re.sub(rb"<v\s*/>|<v>\s*</v>", b"<v>12</v>", members[keep])
            with ZipFile(path, "w") as archive:
                for name, value in members.items():
                    archive.writestr(name, value)
            replace_sheets(path, {"Industry_data": pd.DataFrame({"x": [1, np.nan], "active": ["Y", "N"]})})
            with ZipFile(path) as archive:
                changed = sheet_paths(archive)["Industry_data"]
                for name, original in members.items():
                    if name != changed:
                        self.assertEqual(archive.read(name), original, name)
            cached = load_workbook(path, data_only=True)
            self.assertEqual(cached["keep"]["A1"].value, 12)
            cached.close()

    def test_gui_passes_model_selection(self):
        config = {"countries": "HR", "sector_industry": True, "spatial_level": "country",
                  "out_root": "out", "data_root": "cache", "industry_mode": "complex", "efuels": True,
                  "input_action": "import model inputs", "require_model_ready": True}
        command = build_command(config)
        self.assertIn("--import-model-inputs", command)
        self.assertIn("--require-model-ready", command)
        self.assertEqual(command[command.index("--industry-mode") + 1], "complex")


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.industry = module("industry_test", "industry/generate_industry_inputs_standalone.py")
        cls.transport = module("transport_test", "transport/script/generate_transport_inputs_standalone.py")
        cls.heating = module("heating_test", "heating/generate_heating_inputs_standalone.py")

    def test_industry_regular_fuel_mapping_conserves_capacities(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            path = base / "units.csv"
            pd.DataFrame({"System": "HR", "zone": "HR1", "Industry": "Iron and steel [100-400C]",
                          "fuel_type": ["diesel", "fuel_oil", "Electricity", "non_energy_gas", "non_energy_oil"],
                          "cap_mw": [10, 20, 5, 3, 7], "share_fuel_2020": 0}).to_csv(path, index=False)
            result = self.industry.write_model_ready_industry_data(path, base, True, False, write_workbook=False)
            self.assertEqual(result.loc[result.fuel_type.eq("Oil"), "cap_mw"].item(), 30)
            self.assertEqual(result.loc[result.fuel_type.eq("non_energy"), "cap_mw"].item(), 10)
            self.assertTrue(result.category.eq("100_400C").all())
            self.assertTrue(result.Industry.eq("Iron_steel").all())
            self.assertAlmostEqual(result.share_fuel_2020.sum(), 1)
            self.assertIn("max_inv_period_2050", result)
            self.assertTrue(result.CC_active.eq("N").all())

    def test_industry_category_profiles_keep_non_heat_energy(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            units = base / self.industry.UNITS_FILE
            pd.DataFrame({"System": "HR", "zone": "HR1", "Industry": ["Iron steel [<100C]", "Iron steel [NON_HEAT]"],
                          "fuel_type": "Electricity", "cap_mw": 1, "share_fuel_2020": 1}).to_csv(units, index=False)
            self.industry.write_industry_variants(units, base, True)
            hourly = base / self.industry.DIST_FILE
            pd.DataFrame({"period": range(1, 8761), "System": "HR", "zone": "HR1",
                          "Iron steel [<100C]": 2., "Iron steel [NON_HEAT]": 3.}).to_csv(hourly, index=False)
            self.industry.write_demand_views(hourly, base)
            heat = pd.read_csv(base / "industry_heat.csv")
            process_heat = pd.read_csv(base / self.industry.HEAT_DIST_FILE)
            self.assertTrue(heat["all"].eq(5).all())
            self.assertTrue(process_heat["all"].eq(2).all())
            profiles = pd.read_csv(base / "industry_category_profiles.csv")
            self.assertIn("Iron_steel[NON_HEAT]", profiles)
            self.assertTrue(np.allclose(pd.read_csv(base / "industry_electricity.csv").HR1, 5 / .99))

    def test_transport_curves_match_model_keys_and_normalize(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for key, filename in zip(("activity", "plugin", "v2g"), self.transport.CURVE_FILES):
                (base / filename).write_bytes(self.transport.embedded_bytes(key))
            self.transport.write_distribution_curves(base, base)
            ready = pd.DataFrame({"System": ["HR", "HR"], "zone": ["HR1", "HR1"],
                                  "sector": ["Passenger_cars", "Passenger_cars"], "unit_name": ["EV_car", "ICE_car"]})
            self.transport.write_model_curves(ready, base)
            demand = pd.read_csv(base / "transport_demand.csv")
            self.assertEqual(len(demand), 8760)
            self.assertAlmostEqual(demand.Passenger_cars.sum(), 1)
            available = pd.read_csv(base / "transport_profiles.csv")
            self.assertTrue(available.EV_car.between(0, 1).all())
            self.assertEqual(available.period.tolist(), list(range(1, 8761)))

    def test_shipping_source_names_keep_loads_and_expose_model_options(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            common = {"country": "IT", "type": "ICE"}
            domestic = pd.DataFrame([
                {**common, "nuts3": nuts, "sector": "Domestic shipping", "unit_name": "ICE_MARINE_DOM",
                 "total_load": load, "number": count, "efficiency_primary": 2.}
                for nuts, load, count in (("IT001", 40., 4.), ("IT002", 60., 6.))])
            international = pd.DataFrame([
                {**common, "nuts3": nuts, "sector": "international shipping", "unit_name": "ICE_MARINE_INT",
                 "total_load": load, "number": count, "efficiency_primary": 4.}
                for nuts, load, count in (("IT001", 100., 1.), ("IT002", 200., 2.))])
            domestic.to_csv(base / "transp1_shape_passenger_NUTS3.csv", index=False)
            international.to_csv(base / "transp1_shape_freight_NUTS3.csv", index=False)
            mapping = base / "zones.csv"
            pd.DataFrame({"country": "IT", "nuts3": ["IT001", "IT002"], "zone": "IT1"}).to_csv(mapping, index=False)
            compact = self.transport.aggregate_country(base, mapping)
            ready = self.transport.model_ready(compact)
            self.assertEqual(set(ready.unit_name), {"ICE_MARINE_SHORT", "EV_MARINE_SHORT", "ICE_MARINE_LONG"})
            short = ready.loc[ready.unit_name.eq("ICE_MARINE_SHORT")].iloc[0]
            long = ready.loc[ready.unit_name.eq("ICE_MARINE_LONG")].iloc[0]
            electric = ready.loc[ready.unit_name.eq("EV_MARINE_SHORT")].iloc[0]
            self.assertEqual((short.total_load, short.number, short.efficiency_primary), (100., 10., 2.))
            self.assertEqual((long.total_load, long.number, long.efficiency_primary), (300., 3., 4.))
            self.assertEqual((electric.number, electric.total_load, electric.efficiency_primary), (0., 100., 6.))
            primary = self.transport.transport_ice_prim(ready)
            self.assertTrue({short.unit_name, long.unit_name}.issubset(set(primary.sector_prim)))
            for key, filename in zip(("activity", "plugin", "v2g"), self.transport.CURVE_FILES):
                (base / filename).write_bytes(self.transport.embedded_bytes(key))
            self.transport.write_distribution_curves(base, base)
            self.transport.write_model_curves(ready, base)
            profiles = pd.read_csv(base / "transport_profiles.csv")
            self.assertTrue(set(ready.unit_name).issubset(profiles))
            demand = pd.read_csv(base / "transport_demand.csv")
            self.assertTrue(np.allclose(demand[["Domestic_shipping", "international_shipping"]].sum(), 1.))

    def test_transport_rejects_unknown_combustion_fuel_mapping_early(self):
        frame = pd.DataFrame({"System": ["IT"], "zone": ["IT1"], "type": ["ICE"], "unit_name": ["ICE_UNKNOWN"]})
        with self.assertRaisesRegex(ValueError, "ICE_UNKNOWN"):
            self.transport.transport_ice_prim(frame)

    def test_heating_multi_country_columns_use_reader_zone_names(self):
        frame = pd.DataFrame({"period": [1], "HR::HR1": [1], "SI::SI1": [2]})
        self.assertEqual(self.heating.friendly_curve_columns(frame, 2).columns.tolist(), ["period", "HR1", "SI1"])

    def test_remainder_recomputes_excluded_demand_weighted_shares(self):
        industry = pd.DataFrame({"System": "HR", "zone": "HR1", "category": "all",
                                 "Industry": ["A", "A", "B", "B"],
                                 "unit_name": ["Gas_industry", "Coal_industry"] * 2,
                                 "fuel_type": ["Gas", "Coal"] * 2,
                                 "include_in_the_model": "N", "cap_mw": [5, 5, 5, 5],
                                 "share_fuel_2020": [.9, .1, .2, .8], "max_share_fuel": 1., "max_inv_period": 10.})
        profiles = pd.DataFrame({"System": ["HR"], "zone": ["HR1"], "A": [100.], "B": [300.]})
        template = industry.iloc[:2].drop(columns=["category", "include_in_the_model"])
        result = pooled_industry(industry, profiles, template)
        self.assertAlmostEqual(result.loc[result.fuel_type.eq("Gas"), "share_fuel_2020"].item(), .375)
        self.assertAlmostEqual(result.share_fuel_2020.sum(), 1)
        self.assertTrue(result.cap_mw.eq(10).all())
        self.assertTrue(result.Industry.eq("remainder").all())

    def test_reference_selection_and_hp_equipment_are_retained(self):
        generated = pd.DataFrame({"System": ["HR"], "zone": ["HR1"], "Industry": ["A"], "category": ["<100C"],
                                  "unit_name": ["Gas_industry"], "fuel_type": ["Gas"], "include_in_the_model": ["Y"],
                                  "cap_mw": [17.], "share_fuel_2020": [1.], "max_share_fuel": [1.], "max_inv_period": [10.]})
        reference = pd.concat([generated, generated.assign(unit_name="HP_industry_60", fuel_type="Electricity", cap_mw=0.,
                                                           share_fuel_2020=0.)], ignore_index=True)
        reference["include_in_the_model"] = "N"
        result = industry_parameters(generated, reference)
        self.assertTrue(result.include_in_the_model.eq("N").all())
        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc[result.unit_name.eq("Gas_industry"), "cap_mw"].item(), 17.)

    def test_fractional_reference_parameters_replace_integer_source_defaults_exactly(self):
        generated = pd.DataFrame({"System": ["HR", "SI"], "zone": ["HR1", "SI1"],
                                  "Industry": "A", "category": "100_400C", "unit_name": "Gas_industry",
                                  "fuel_type": "Gas", "cap_mw": [17, 21], "share_fuel_2020": [.8, .9],
                                  "max_share_fuel": [1, 1], "include_in_the_model": "Y",
                                  "max_cap": [10000, 10000], "max_inv_period": [500, 500], "max_inv_period_2030": [500, 500], "life_time": [20, 20]})
        original = generated.copy(deep=True)
        reference = generated.iloc[:1].assign(max_cap=341.663728186051, max_inv_period=155.375,
                                             max_inv_period_2030=122.125, life_time=17.5,
                                             max_share_fuel=.75, include_in_the_model="N")
        result = industry_parameters(generated, reference)
        self.assertTrue(result.max_cap.eq(341.663728186051).all())
        self.assertTrue(result.max_inv_period.eq(155.375).all())
        self.assertTrue(result.max_inv_period_2030.eq(122.125).all())
        self.assertTrue(result.life_time.eq(17.5).all())
        self.assertEqual(result.max_share_fuel.tolist(), [.8, .9])
        self.assertEqual(result.cap_mw.tolist(), [17, 21])
        self.assertTrue(result.include_in_the_model.eq("N").all())
        pd.testing.assert_frame_equal(generated, original)

    def test_paid_transport_conversions_keep_metadata_without_initial_stock(self):
        base = {"System": "HR", "zone": "HR1", "sector": "Passenger_cars", "unit_name": "ICE_car",
                "type": "ICE", "total_load": 100., "number": 20., "efficiency_primary": .5, "2025": 0.}
        generated = pd.DataFrame([base])
        parent = {**base, 2025: 0., "compat_parent": np.nan, "compat_schema": np.nan}
        parent.pop("2025")
        child = {**parent, "unit_name": "RETROFIT_METHANOL_ICE_car", "compat_parent": "ICE_car",
                 "number": 0., "compat_schema": 1., "compat_fuel": "methanol", "compat_kind": "fuel_retrofit",
                 "compat_affected_fraction": .45, "compat_cost_factor": .1}
        primary = pd.DataFrame({"sector_prim": ["ICE_car", child["unit_name"]], "fuel_prim": "petrol",
                                "share2020prim": 1., "max_share": 1., "CO2prim": .25, "fossil": "Y",
                                "zone": "HR1", "system": "HR", "use": "Y"})
        fleet, fuels = transport_parameters(generated, pd.DataFrame([parent, child]), primary)
        self.assertEqual(len(fleet), 2)
        self.assertEqual(fleet.number.sum(), 20)
        self.assertEqual(fleet.loc[fleet.compat_parent.notna(), "compat_schema"].item(), 1)
        self.assertNotIn("2025", fleet)
        self.assertIn(2025, fleet)
        self.assertEqual(len(fuels), 2)

    def test_legacy_shipping_export_keeps_both_paid_conversion_families(self):
        generated, template, primary = [], [], []
        for sector, legacy, current, fuel in (
                ("Domestic_shipping", "ICE_MARINE_DOM", "ICE_MARINE_SHORT", "diesel"),
                ("international_shipping", "ICE_MARINE_INT", "ICE_MARINE_LONG", "fuel_oil")):
            source = dict(System="IT", zone="IT1", sector=sector, unit_name=legacy,
                          type="ICE", total_load=100., number=20., efficiency_primary=4.)
            generated.append(source)
            parent = {**source, "System": "HR", "zone": "HR1", "unit_name": current,
                      "efficiency_primary": 2., "compat_parent": np.nan, "compat_schema": np.nan}
            child = {**parent, "unit_name": "RETROFIT_" + current, "compat_parent": current,
                     "compat_schema": 1., "compat_cost_factor": .15, "efficiency_primary": 1.5}
            template.extend([parent, child])
            for unit in (current, child["unit_name"]):
                primary.append(dict(sector_prim=unit, fuel_prim=fuel, zone="HR1", system="HR", use="Y"))
        fleet, fuels = transport_parameters(pd.DataFrame(generated), pd.DataFrame(template), pd.DataFrame(primary))
        self.assertEqual(len(fleet), 4)
        self.assertEqual(fleet.number.sum(), 40.)
        conversions = fleet.loc[fleet.compat_parent.notna()]
        self.assertTrue(conversions.number.eq(0).all())
        self.assertTrue(conversions.efficiency_primary.eq(3.).all())
        self.assertTrue(conversions.compat_cost_factor.eq(.15).all())
        self.assertTrue(set(conversions.compat_parent).issubset(fleet.unit_name))
        self.assertEqual(set(fuels.sector_prim), set(fleet.unit_name))
        self.assertTrue(fuels.zone.eq("IT1").all())
        self.assertTrue(fuels.system.eq("IT").all())
        with self.assertRaisesRegex(ValueError, "No current primary-fuel compatibility mapping"):
            transport_parameters(pd.DataFrame(generated), pd.DataFrame(template), pd.DataFrame(primary).iloc[:0])


if __name__ == "__main__":
    unittest.main()
