"""Scenario controls, native workbook conventions and launcher integration."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_all_sector_inputs import build_parser
from h2res_input_gui import build_command
from run_model_scenario import configure, prepare_source, native_variant_files
from scenario_config import investment_tables, parse_years, renewable_curve, resolve_scenario, setup_table
from scenario_runtime import fuel_kind


class ScenarioTests(unittest.TestCase):
    def test_copied_launcher_uses_all_native_variant_paths_without_preparation_imports(self):
        from model_variants import configurations
        from model_input_bundle import selected_workbook,selected_complex_workbook
        for efuels,mode,case in configurations():
            workbook,companion=native_variant_files(efuels,mode,case)
            self.assertEqual(workbook,selected_workbook(efuels,mode,case))
            self.assertEqual(companion,selected_complex_workbook(efuels,case) if mode=='complex' else None)

    def test_reference_launcher_preserves_policy_bytes_and_carries_configuration(self):
        from scenario_config import write_reference_launcher
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir()
            path=root/'data/policy.xlsx'
            pd.DataFrame(dict(years_all=[2020,2025])).to_excel(path,sheet_name='setup',index=False)
            before=path.read_bytes()
            record=write_reference_launcher(root,'flex_tech_categories.xlsx',efuels=False,industry_mode='categories',electricity_case='conservative')
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(record['years'],[2020,2025])
            self.assertTrue((root/'run_model_scenario.py').is_file())
            self.assertTrue((root/'scenario_runtime.py').is_file())
            self.assertEqual(json.loads((root/'scenario.json').read_text())['industry_mode'],'categories')

    def test_legacy_generation_policy_multiplier_tracks_new_generator_identifiers(self):
        import os
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'model_inputs').mkdir()
            (root/'model_inputs/generator_input_links.json').write_text(json.dumps([dict(workbook='flex_tech.xlsx',generators=[
                dict(unit_name='HR_New_Solar',investment_donor_columns=['HR_PV','HR_PV_1'])])]))
            settings=dict(technology_workbook='flex_tech.xlsx',efuels=False,preset='reference',scope='all-energy',industry_electricity_case='conservative')
            namespace=dict(generation_annual_build_limit_multipliers={'HR_PV':2.,'HR_PV_1':2.})
            try:
                configure(namespace,settings,root,'test')
                self.assertEqual(namespace['generation_annual_build_limit_multipliers']['HR_New_Solar'],2.)
            finally:
                os.chdir(previous)

    def test_conflicting_legacy_multipliers_require_explicit_generated_plant_choice(self):
        import os
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'generator_input_links.json').write_text(json.dumps([dict(workbook='flex_tech.xlsx',generators=[
                dict(unit_name='HR_New_Solar',investment_donor_columns=['HR_PV','HR_PV_1'])])]))
            settings=dict(technology_workbook='flex_tech.xlsx',efuels=False,preset='reference',scope='all-energy',industry_electricity_case='conservative')
            namespace=dict(generation_annual_build_limit_multipliers={'HR_PV':2.,'HR_PV_1':1.})
            try:
                with self.assertRaisesRegex(ValueError,'Mixed legacy investment multipliers'):
                    configure(namespace,settings,root,'test')
            finally:
                os.chdir(previous)

    def args(self, *options):
        return build_parser().parse_args(list(options))

    def test_default_preserves_reference(self):
        self.assertIsNone(resolve_scenario(self.args()))

    def test_model_data_redirection_preserves_variant_subdirectories(self):
        import os
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            namespace = {"flex_tech_dat": "./data/variants/technical_2050/flex_tech_efuel_categories.xlsx",
                         "variant_source": "./data/variants/technical_2050/flex_tech_efuel_categories.xlsx"}
            scenario = dict(technology_workbook="variants/technical_2050/flex_tech_efuel_categories.xlsx",
                            industry_electricity_case="technical_2050", efuels=True, preset="reference", scope="all-energy")
            try:
                configure(namespace, scenario, root, "test")
            finally:
                os.chdir(previous)
            expected = str(root / "data/variants/technical_2050/flex_tech_efuel_categories.xlsx")
            self.assertEqual(namespace["flex_tech_dat"], expected)
            self.assertEqual(namespace["variant_source"], expected)

    def test_plain_reader_checks_requested_configuration_not_model_defaults(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from validate_model_inputs import read_with_model
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, bundle = root / "model", root / "bundle"
            (model / "scripts").mkdir(parents=True)
            (bundle / "data").mkdir(parents=True)
            pd.DataFrame(dict(period=[1],System=['HR'],zone=['HR1'],**{'all':[0.]})).to_csv(bundle/'data/industry_category_profiles.csv',index=False)
            (model / "main.py").write_text("model_efuel = True\nmodel_industry_categories = False\n"
                                          "flex_tech_dat = './data/wrong.xlsx'\ndef exec_script(path):\n    pass\n")
            (model / "scripts/read_process_data.py").write_text(
                "assert model_efuel is False\nassert model_industry_categories is True\n"
                "assert flex_tech_dat.endswith('flex_tech_categories.xlsx')\nSystems=['HR']\nzones=['HR1']\nyears=[2025]\nperiods=[1]\n")
            with patch.dict(sys.modules, {"gurobipy": SimpleNamespace()}):
                report = read_with_model(model, bundle, industry_mode="categories", efuels=False)
            self.assertTrue(report["reader_completed"])
            self.assertEqual(Path(report["technology_workbook"]), bundle / "data/flex_tech_categories.xlsx")

    def test_full_energy_requires_renewable_fuel_pathways(self):
        with self.assertRaisesRegex(ValueError, "efuels"):
            resolve_scenario(self.args("--scenario-preset", "res100"))
        result = resolve_scenario(self.args("--scenario-preset", "res100", "--efuels"))
        self.assertEqual(result["scope"], "all-energy")
        self.assertEqual(result["target_year"], 2050)

    def test_explicit_years_and_range(self):
        result = resolve_scenario(self.args("--start-year", "2025", "--end-year", "2045", "--year-step", "5"))
        self.assertEqual(result["years"], [2025, 2030, 2035, 2040, 2045])
        with self.assertRaises(ValueError):
            resolve_scenario(self.args("--year-step", "0"))
        with self.assertRaises(ValueError):
            resolve_scenario(self.args("--planning-years", "2025,2030", "--start-year", "2025"))
        for raw in ("2030,2025", "2025,2025", "2025,2030,2040", "2025.5,2030"):
            with self.assertRaises(ValueError):
                parse_years(raw)

    def test_json_and_cli_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.json"
            path.write_text(json.dumps({"preset": "res100", "years": [2025, 2030, 2035], "target_year": 2035}), encoding="utf-8")
            result = resolve_scenario(self.args("--scenario-config", str(path), "--efuels", "--renewable-target-year", "2030"))
            self.assertEqual(result["target_year"], 2030)
            self.assertEqual(result["years"], [2025, 2030, 2035])

    def test_invalid_json_years_are_rejected_without_truncation_or_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.json"
            for config in ({"start_year": 2025.5}, {"year_step": 1.5}, {"target_year": float('inf')},
                           {"years": [None, 2030]}, {"years": 2025}, {"years": [True, 2030]}):
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(config=config), self.assertRaises(ValueError):
                    resolve_scenario(self.args("--scenario-config", str(path)))

    def test_investment_overrides_cannot_change_transport_history_or_hide_invalid_limits(self):
        fleet = pd.DataFrame({"number": [150], "max_share": [1], 2030: [500]})
        for column in ("number", "max_share"):
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, "not an annual investment"):
                investment_tables({"transport_all": fleet}, 1., [{"sheet": "transport_all", "column": column, "value": .5}])
        result = investment_tables({"transport_all": fleet}, 1., [{"sheet": "transport_all", "column": 2030, "value": .5}])
        self.assertEqual(result["transport_all"][2030].item(), .5)
        self.assertEqual(result["transport_all"].number.item(), 150)
        for invalid in ("bad", -1., float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                investment_tables({"Industry_data": pd.DataFrame({"max_inv_period": [invalid]})}, 2., [])

    def test_rps_curve_reaches_deadline_and_keeps_other_systems(self):
        source = pd.DataFrame({"System": ["HR", "SI"], 2025: [.4, .3], 2030: [.6, .5], 2035: [.8, .7], 2040: [.9, .8]})
        result, evidence = renewable_curve(source, ["HR"], [2025, 2030, 2035, 2040], 2035)
        self.assertAlmostEqual(result.loc[0, 2030], .7)
        self.assertEqual(result.loc[0, 2035], 1.)
        self.assertEqual(result.loc[0, 2040], 1.)
        self.assertTrue(result.iloc[1].equals(source.iloc[1]))
        self.assertIn("not a measured", evidence[0]["basis"])
        with self.assertRaises(ValueError):
            renewable_curve(source, ["NEW"], [2025, 2030], 2030)
        result, _ = renewable_curve(source, ["NEW"], [2025, 2030], 2030, .2)
        self.assertEqual(result.loc[result.System.eq("NEW"), 2030].item(), 1.)

    def test_rps_requires_a_modeled_terminal_year(self):
        source = pd.DataFrame({"System": ["HR"], 2025: [.4], 2030: [.6]})
        with self.assertRaises(ValueError):
            renewable_curve(source, ["HR"], [2025, 2030], 2040)

    def test_integer_rps_columns_accept_fractional_targets(self):
        source = pd.DataFrame({"System": ["HR", "IT"], 2025: [0, 0], 2030: [0, 0], 2050: [1, 1]})
        result, _ = renewable_curve(source, ["HR"], [2025, 2030, 2035, 2040, 2045, 2050], 2050, .1)
        self.assertEqual(result.loc[0, 2025], .1)
        self.assertAlmostEqual(result.loc[0, 2030], .28)
        self.assertEqual(result.loc[0, 2050], 1.)
        self.assertEqual(result.loc[1, 2030], 0.)
        self.assertEqual(source.loc[0, 2030], 0)

    def test_fractional_overrides_preserve_unselected_integer_limits(self):
        tables = {"Industry_data": pd.DataFrame({"zone": ["a", "b"], "max_inv_period": [0, 100]})}
        changed = investment_tables(tables, 1., [{"sheet": "Industry_data", "column": "max_inv_period",
                                                 "where": {"zone": "a"}, "value": .125}])
        self.assertEqual(changed["Industry_data"].max_inv_period.tolist(), [.125, 100.])
        self.assertEqual(tables["Industry_data"].max_inv_period.tolist(), [0, 100])

    def test_investment_limits_preserve_capacity_and_blank_semantics(self):
        tables = {"Industry_data": pd.DataFrame({"zone": ["HR1", "HR1"], "cap_mw": [10., 20.],
                    "max_cap": [100., 200.], "max_inv_period": [5., 0.],
                    "max_inv_period_2030": [7., 0.], "CC_max_inv_period_2030": [np.nan, 0.]}),
                  "cap_inv_lim": pd.DataFrame({"year": [2025, 2030], "zone": ["HR1", "HR1"], "PV": [10., 0.]})}
        updated = investment_tables(tables, 2., [{"sheet": "cap_inv_lim", "column": "PV", "years": [2030], "value": 13.}])
        self.assertEqual(updated["Industry_data"].max_inv_period_2030.tolist(), [14., 0.])
        self.assertTrue(pd.isna(updated["Industry_data"].CC_max_inv_period_2030.iloc[0]))
        self.assertEqual(updated["Industry_data"].max_cap.tolist(), [100., 200.])
        self.assertEqual(updated["Industry_data"].cap_mw.tolist(), [10., 20.])
        self.assertEqual(updated["cap_inv_lim"].PV.tolist(), [20., 13.])
        with self.assertRaises(ValueError):
            investment_tables(tables, 1., [{"sheet": "Industry_data", "column": "max_cap", "value": 0.}])

    def test_setup_controls_stay_in_first_row(self):
        source = pd.DataFrame({"years_all": [2025, 2026], "chunk_size": [1., np.nan], "step_size": [1., np.nan],
                               "first_hour": [1., np.nan], "last_hour": [8760., np.nan]})
        result = setup_table(source, [2025, 2030, 2035])
        self.assertEqual(result.years_all.tolist(), [2025, 2030, 2035])
        self.assertEqual(result.dropna().iloc[0].last_hour, 8760.)
        self.assertTrue(pd.isna(result.chunk_size.iloc[1]))

    def test_launcher_injects_flags_and_exec_hook(self):
        source = "model_efuel = False\nmodel_industry_categories = False\ndef exec_script(path):\n    raise RuntimeError('old executor')\nexec_script('builder.py')\n"
        events = []
        ns = {"_scenario_configure": lambda g: events.append(("configure", g["model_efuel"])),
              "_scenario_execute": lambda path, g: events.append((path, g["model_industry_categories"]))}
        tree = prepare_source(source, {"model_efuel": True, "model_industry_categories": True})
        exec(compile(tree, "test_main.py", "exec"), ns)
        self.assertEqual(events, [("configure", True), ("builder.py", True)])
        prefix = prepare_source(source, {"model_efuel": True}, prefix_only=True)
        self.assertFalse(any(isinstance(node, ast.FunctionDef) and node.name == "exec_script" for node in prefix.body))

    def test_gui_passes_scenario_without_overriding_json_with_defaults(self):
        config = {"countries": "HR", "spatial_level": "country", "out_root": "out", "data_root": "data",
                  "sector_industry": True, "efuels": True, "scenario_preset": "res100", "scenario_scope": "all-energy",
                  "planning_years": "2025,2030,2035", "renewable_target_year": "2035", "investment_multiplier": "2"}
        command = build_command(config)
        self.assertIn("--planning-years", command)
        self.assertEqual(command[command.index("--renewable-target-year") + 1], "2035")
        config.update(scenario_preset="reference", scenario_config="custom.json")
        command = build_command(config)
        self.assertNotIn("--scenario-preset", command)
        self.assertIn("--scenario-config", command)

    def test_nuclear_and_fossil_waste_are_not_zero_carbon_renewables(self):
        self.assertEqual(fuel_kind("Nuclear"), "nonrenewable")
        self.assertEqual(fuel_kind("Waste"), "nonrenewable")
        self.assertEqual(fuel_kind("H2"), "secondary")
        with self.assertRaises(ValueError):
            fuel_kind("unclassified fuel")


if __name__ == "__main__":
    unittest.main()
