"""Source and native-interface regressions for the supplied industry method."""
from pathlib import Path
import re
import sys
import tempfile
import unittest
from zipfile import ZipFile

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from industry.generate_complex_industry_inputs import allocations, equipment_frames, observations, regionalize, sync_costs
from industry.complex_sources import require_formula_caches, sector_waste_proofs
from industry.methods import jrc_source as jrc
from model_input_bundle import sheet_paths


class IndustrySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "industry/handoff/model/data/sources/JRC-IDEES-2023_Industry_HR.xlsx"
        cls.components, cls.branches, cls.evidence = jrc.extract_source(cls.source)
        cls.templates = pd.read_excel(ROOT / "model_reference/data/industry_complex_efuel.xlsx", sheet_name=None)
        cls.leaves = observations(cls.source, cls.components)
        cls.frames = equipment_frames(cls.components, cls.branches, cls.evidence, cls.leaves, cls.templates, "HR", True, "conservative")

    def test_independent_jrc_root_totals_close_energy_and_carbon(self):
        # Read the published root totals directly; do not reuse generator grouping.
        book = load_workbook(self.source, read_only=True, data_only=True)
        try:
            t = self.frames["complex_industry"]
            p = self.frames["Process_data"]
            for code, industry in jrc.SECTORS.items():
                expected = {}
                for suffix in ("_ued", "_fec", "_emi"):
                    rows = list(book[code + suffix].iter_rows())
                    column = next(i for i, c in enumerate(rows[0]) if c.value == 2020)
                    total = 0.
                    for row in rows[4:]:
                        if row[0].value is None:
                            continue
                        if row[0].alignment.indent == 0:
                            break
                        if row[0].alignment.indent == 1:
                            total += float(row[column].value or 0.)
                    expected[suffix] = total
                block = t.loc[t.Industry.eq(industry)]
                useful = block.cap_mw * 8760
                final = useful / block.efficiency.replace(0, np.nan)
                with self.subTest(industry=industry):
                    self.assertAlmostEqual(useful.sum(), expected["_ued"] * 11630, delta=1e-5)
                    self.assertAlmostEqual(final.sum(), expected["_fec"] * 11630, delta=1e-5)
                    carbon = (final * block.combustion_CO2_t_per_MWh).sum() + p.loc[p.Industry.eq(industry), "historical_process_CO2_t"].sum()
                    self.assertAlmostEqual(carbon, expected["_emi"] * 1000, delta=1e-5)
        finally:
            book.close()

    def test_observed_calibration_matches_handoff_and_keeps_aggregate_efficiencies(self):
        keys = ["Industry", "branch", "component", "unit_name"]
        old = self.templates["complex_industry"].set_index(keys)
        new = self.frames["complex_industry"].set_index(keys)
        self.assertEqual(set(old.index), set(new.index))
        for field in ["cap_mw", "efficiency", "share_fuel_2020", "combustion_CO2_t_per_MWh", "max_share_fuel"]:
            np.testing.assert_allclose(new.loc[old.index, field], old[field], rtol=1e-9, atol=1e-9, err_msg=field)
        for field in ["group", "include_in_the_model", "life_time", "decom_start_existing_cap", "decom_start_new", "final_life_cap"]:
            self.assertTrue(new.loc[old.index, field].eq(old[field]).all(), field)
        observed = new.efficiency_basis.eq("observed_JRC_useful_to_final_ratio")
        self.assertTrue(new.loc[observed, "efficiency"].gt(1).any())
        assumed_combustion = ~observed & ~new.index.get_level_values("unit_name").str.startswith("HP_industry_")
        self.assertTrue(new.loc[assumed_combustion, "efficiency"].le(1).all())

    def test_hr_ammonia_exception_does_not_apply_by_renaming_country(self):
        other = equipment_frames(self.components, self.branches, self.evidence, self.leaves, self.templates, "HU", True, "conservative")
        self.assertAlmostEqual(self.frames["Process_data"].excluded_H2_reforming_CO2_t.sum(), 535320.11)
        self.assertEqual(other["Process_data"].excluded_H2_reforming_CO2_t.sum(), 0)

    def test_regional_weights_preserve_energy_physical_output_and_index_units(self):
        mapping = pd.DataFrame([dict(country="HR", zone=z) for z in ["a", "b"]])
        with self.assertRaisesRegex(ValueError, "national"):
            allocations(mapping, ["HR"], None)
        weights = allocations(mapping, ["HR"], None, equal=True)
        result = regionalize(self.frames, weights, "HR")
        self.assertAlmostEqual(result["complex_industry"].cap_mw.sum(), self.frames["complex_industry"].cap_mw.sum())
        physical = result["Product_demand"].product_unit.eq("t_product")
        self.assertAlmostEqual(result["Product_demand"].loc[physical, "2020"].sum(), self.frames["Product_demand"].loc[self.frames["Product_demand"].product_unit.eq("t_product"), "2020"].sum())
        index = result["Process_data"].loc[result["Process_data"].activity_unit.eq("index")]
        initial = self.frames["Process_data"].loc[self.frames["Process_data"].activity_unit.eq("index")]
        self.assertAlmostEqual(index.reference_activity.sum(), initial.reference_activity.sum() * 2)
        self.assertAlmostEqual((index.reference_activity * index.energy_intensity_MWh_per_activity).sum(), initial.useful_energy_demand_MWh.sum())

    def test_regional_limits_preserve_blank_and_blocked_limits(self):
        frame = self.frames["complex_industry"].copy()
        frame.loc[0, "max_inv_period_2030"] = np.nan
        frame.loc[1, "max_inv_period_2030"] = 0.
        weights = allocations(pd.DataFrame([dict(country="HR", zone=z) for z in ["a", "b"]]), ["HR"], None, equal=True)
        result = regionalize({"complex_industry": frame}, weights, "HR")["complex_industry"]
        key = ["Industry", "branch", "component", "unit_name"]
        for row, expected in [(frame.iloc[0], None), (frame.iloc[1], 0.)]:
            match = pd.Series(True, index=result.index)
            for k in key:
                match &= result[k].eq(row[k])
            values = result.loc[match, "max_inv_period_2030"]
            self.assertTrue(values.isna().all() if expected is None else values.eq(expected).all())

    def test_technical_case_changes_potential_without_rewriting_observations(self):
        technical = equipment_frames(self.components, self.branches, self.evidence, self.leaves, self.templates, "HR", True, "technical_2050")["complex_industry"]
        keys = ["Industry", "branch", "component", "unit_name"]
        a, b = self.frames["complex_industry"].set_index(keys), technical.set_index(keys)
        for field in ["cap_mw", "efficiency", "share_fuel_2020", "combustion_CO2_t_per_MWh"]:
            np.testing.assert_allclose(a[field], b.loc[a.index, field])
        self.assertTrue((b.loc[a.index, "max_share_fuel"] >= a.max_share_fuel - 1e-10).all())


class IndustryWorkbookTests(unittest.TestCase):
    def test_zero_weight_regions_have_no_indexed_activity_or_physical_output(self):
        source=pd.DataFrame(dict(Industry=['A','A'],product_unit=['t_product','index'],**{'2020':[101.,100.],'2050':[120.,110.]}))
        process=pd.DataFrame(dict(Industry=['A','A'],activity_unit=['t_product','index'],product_output_t=[101.,np.nan],
                                 reference_activity=[101.,100.],useful_energy_demand_MWh=[300.,400.],historical_process_CO2_t=[10.,20.],
                                 excluded_H2_reforming_CO2_t=0.,energy_intensity_MWh_per_activity=[300/101,4.],process_CO2_t_per_activity=[10/101,.2],
                                 historical_process_CO2_t_per_activity=[10/101,.2],excluded_H2_reforming_CO2_t_per_activity=0.))
        allocation=pd.DataFrame([dict(country='HR',System='HR',zone=z,Industry='A',weight=w,allocation_basis='test') for z,w in [('a',0.),('b',1.)]])
        result=regionalize({'Product_demand':source,'Process_data':process},allocation,'HR')
        self.assertTrue(result['Product_demand'].loc[result['Product_demand'].zone.eq('a'),['2020','2050']].eq(0).all().all())
        zero=result['Process_data'].loc[result['Process_data'].zone.eq('a')]
        self.assertTrue(zero.reference_activity.eq(0).all())
        self.assertTrue(zero.useful_energy_demand_MWh.eq(0).all())
        self.assertEqual(result['Product_demand'].loc[result['Product_demand'].zone.eq('b'),'2020'].tolist(),[101.,100.])

    def test_regionalization_accepts_integer_product_data_without_rounding(self):
        source = pd.DataFrame({"Industry": ["A", "A"], "product_unit": ["t_product", "production_index"],
                               "2020": [101, 100], "2025": [111, 100]})
        allocation = pd.DataFrame([dict(country="HR", System="HR", zone="a", Industry="A", weight=.25, allocation_basis="test"),
                                   dict(country="HR", System="HR", zone="b", Industry="A", weight=.75, allocation_basis="test")])
        result = regionalize({"Product_demand": source}, allocation, "HR")["Product_demand"]
        self.assertEqual(result.loc[result.product_unit.eq("t_product"), "2020"].tolist(), [25.25, 75.75])
        self.assertEqual(result.loc[result.product_unit.eq("production_index"), "2020"].tolist(), [100., 100.])
        self.assertEqual(result.loc[result.product_unit.eq("t_product"), "2025"].sum(), 111.)
        self.assertEqual(source["2020"].tolist(), [101, 100])

    def test_uncached_numeric_source_formula_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.xlsx"
            b = Workbook(); b.active["A1"] = "=1+2"; b.save(path); b.close()
            with self.assertRaisesRegex(ValueError, "Uncached"):
                require_formula_caches(path)

    def test_new_component_costs_preserve_existing_formula_caches_and_other_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "costs.xlsx"
            b = Workbook(); b.active.title = "tech_cost_years"
            b.active.append(["year", "Gas_industry"]); b.active.append([2025, 8]); b.active.append([2030, "=B2*2"])
            b.create_sheet("keep")["A1"] = "unchanged"; b.save(path); b.close()
            with ZipFile(path) as source:
                members = {i.filename: source.read(i.filename) for i in source.infolist()}
                part = sheet_paths(source)["tech_cost_years"]
            members[part] = re.sub(rb"<v\s*/>|<v>\s*</v>", b"<v>16</v>", members[part])
            with ZipFile(path, "w") as output:
                for key, value in members.items(): output.writestr(key, value)
            added = sync_costs(path, pd.DataFrame([dict(component="new_process", unit_name="Gas_industry")]))
            self.assertEqual(len(added), 1)
            with ZipFile(path) as current:
                for key, value in members.items():
                    if key != part: self.assertEqual(current.read(key), value)
            b = load_workbook(path, data_only=False)
            self.assertEqual(b.active["B3"].value, "=B2*2")
            self.assertEqual(b.active["C3"].value, "=C2*2"); b.close()
            b = load_workbook(path, data_only=True)
            self.assertEqual(b.active["B3"].value, 16)
            self.assertEqual(b.active["C3"].value, 16); b.close()


if __name__ == "__main__":
    unittest.main()
