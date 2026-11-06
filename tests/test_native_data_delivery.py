"""Native delivery atomicity and the Excel table-repair regression."""
from copy import copy
from pathlib import Path
import json
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from excel_integrity import workbook_errors
from model_input_bundle import replace_sheets, sheet_paths, TECH_WORKBOOKS, selected_workbook
from model_variants import configurations, reusable_complex, apply_variant_investments, branch_allocation_weights
from native_data_delivery import publish_outputs
from default_model_inputs import default_rows, complete_defaults
from filesystem_publish import replace_with_retry


class NativeDeliveryTests(unittest.TestCase):
    def test_publication_retries_a_transient_windows_folder_lock(self):
        locked = PermissionError("temporary scanner lock")
        locked.winerror = 5
        destination = Path("published")
        with patch.object(Path, "replace", side_effect=[locked, destination]) as rename, patch("filesystem_publish.time.sleep") as sleep:
            self.assertEqual(replace_with_retry(Path("stage"), destination), destination)
        self.assertEqual(rename.call_count, 2)
        sleep.assert_called_once()

    def test_streamed_integrity_checks_styles_and_table_links_after_headers(self):
        from excel_integrity import _worksheet_metadata, MAIN, REL
        xml = (f'<worksheet xmlns="{MAIN}" xmlns:r="{REL}"><sheetData>'
               '<row r="1"><c r="A1" t="inlineStr"><is><t>System</t></is></c></row>'
               '<row r="2"><c r="A2" s="999" t="inlineStr"><is><t>HR</t></is></c></row>'
               '</sheetData><tableParts count="1"><tablePart r:id="rId1"/></tableParts></worksheet>')
        refs, values, invalid = _worksheet_metadata(io.BytesIO(xml.encode()), {"A1"}, [], 1)
        self.assertEqual(refs, {"rId1"})
        self.assertEqual(values, {"A1": "System"})
        self.assertTrue(invalid)

    def test_excel_integrity_cache_tracks_contents_across_renames(self):
        from excel_integrity import _INTEGRITY_CACHE
        _INTEGRITY_CACHE.clear()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.xlsx"
            second = Path(directory) / "second.xlsx"
            first.write_bytes(b"first contents")
            second.write_bytes(first.read_bytes())
            with patch("excel_integrity._workbook_errors", return_value=[]) as check:
                self.assertEqual(workbook_errors(first), [])
                self.assertEqual(workbook_errors(second), [])
                self.assertEqual(check.call_count, 1)
                second.write_bytes(b"changed contents")
                self.assertEqual(workbook_errors(second), [])
                self.assertEqual(check.call_count, 2)

    def test_excel_integrity_streams_worksheet_parts(self):
        from excel_integrity import _INTEGRITY_CACHE
        _INTEGRITY_CACHE.clear()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "streamed.xlsx"
            book = Workbook()
            book.active.append(["System", "zone"])
            book.active.append(["HR", "HR023"])
            book.active.add_table(Table(displayName="Zones", ref="A1:B2"))
            book.save(path)
            original_read = ZipFile.read
            def bounded(archive, name, *args, **kwargs):
                filename = name.filename if hasattr(name, "filename") else name
                if filename.startswith("xl/worksheets/") and filename.endswith(".xml"):
                    raise AssertionError("Worksheet integrity must use bounded streaming reads")
                return original_read(archive, name, *args, **kwargs)
            with patch.object(ZipFile, "read", bounded):
                self.assertEqual(workbook_errors(path), [])

    def test_process_region_weights_conserve_each_branch_and_default_zero_branches(self):
        industry = pd.DataFrame(dict(zone=["a", "b"], Industry=["Steel", "Steel"], cap_mw=[3., 1.]))
        mapping = pd.DataFrame(dict(country=["HR", "HR"], zone=["a", "b"]))
        output = branch_allocation_weights(industry, mapping, ["Steel", "Paper"])
        self.assertEqual(output.loc[output.Industry.eq("Steel"), "weight"].tolist(), [.75, .25])
        self.assertEqual(output.loc[output.Industry.eq("Paper"), "weight"].tolist(), [.5, .5])
        self.assertTrue(output.groupby("Industry").weight.sum().eq(1.).all())

    def test_cached_process_variant_is_invalidated_by_changed_observations_or_geography(self):
        from model_input_bundle import sha256
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.xlsx"
            template.write_bytes(b"assumptions")
            for name in ["process.xlsx", "industry_heat.csv", "industry_electricity.csv", "industry_inputs.xlsx"]:
                (root / name).write_bytes(b"cached")
            allocation = pd.DataFrame(dict(country=["HR"], System=["HR"], zone=["HR1"], Industry=["Steel"], weight=[1.]))
            allocation.to_csv(root / "industry_allocation.csv", index=False)
            metadata = dict(base_year=2020, efuels=True, electricity_case="conservative", source_reconciliation_passed=True,
                            inherited_template_sha256=sha256(template), selected_industries=["Steel"], complex_workbook="process.xlsx",
                            sources=[dict(country="HR", waste_allocation="sector-blend", files={"source.xlsx": "original"})])
            (root / "complex_generation.json").write_text(json.dumps(metadata))
            options = dict(countries=["HR"], base_year=2020, efuels=True, case="conservative", template=template,
                           allocation=allocation, sources={"HR": {"source.xlsx": "original"}}, sectors=["Steel"], waste="sector-blend")
            with patch("excel_integrity.workbook_errors", return_value=[]):
                self.assertTrue(reusable_complex(root, **options))
                self.assertFalse(reusable_complex(root, **{**options, "sources": {"HR": {"source.xlsx": "changed"}}}))
                changed = allocation.assign(zone="HR2")
                self.assertFalse(reusable_complex(root, **{**options, "allocation": changed}))
                metadata["efuels"] = False
                (root / "complex_generation.json").write_text(json.dumps(metadata))
                self.assertFalse(reusable_complex(root, **{**options, "efuels": False}))
                from industry.fuel_representation import REGULAR_FUEL_METHOD
                metadata["regular_fuel_representation"] = REGULAR_FUEL_METHOD
                (root / "complex_generation.json").write_text(json.dumps(metadata))
                self.assertTrue(reusable_complex(root, **{**options, "efuels": False}))
                template.write_bytes(b"changed assumptions")
                self.assertFalse(reusable_complex(root, **options))

    def test_scenario_investment_multiplier_applies_once_to_each_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for name, limit in [("selected.xlsx", 20.), ("alternative.xlsx", 10.)]:
                with pd.ExcelWriter(data / name) as book:
                    pd.DataFrame(dict(cap_mw=[7., 0.], max_inv_period=[limit, 0.])).to_excel(book, sheet_name="Industry_data", index=False)
            from model_input_bundle import selected_complex_workbook
            for e in (False, True):
                for c in ("conservative", "technical_2050"):
                    with pd.ExcelWriter(data / selected_complex_workbook(e, c)) as book:
                        for sheet in ["complex_industry", "CC"]:
                            pd.DataFrame(dict(cap_mw=[7.], max_inv_period=[10.])).to_excel(book, sheet_name=sheet, index=False)
            apply_variant_investments(data, dict(investment_multiplier=2., investment_overrides=[]),
                                      [{"technology_workbook": "selected.xlsx"}, {"technology_workbook": "alternative.xlsx"}], "selected.xlsx")
            for name in ["selected.xlsx", "alternative.xlsx"]:
                table = pd.read_excel(data / name, "Industry_data")
                self.assertEqual(table.max_inv_period.tolist(), [20., 0.])
                self.assertEqual(table.cap_mw.tolist(), [7., 0.])

    def test_defaults_prefer_the_requested_country_and_preserve_existing_rows(self):
        frame = pd.DataFrame(dict(System=["HR", "IT"], zone=["HR1", "IT1"], capacity=[9., 3.]))
        output, notes = default_rows(frame, {("IT", "IT1"), ("IT", "IT2")})
        self.assertEqual(output.capacity.tolist(), [9., 3., 3.])
        self.assertEqual(notes[0]["donor_zone"], "IT1")
        self.assertIn("not a sourced observation", notes[0]["basis"])

    def test_system_defaults_are_added_once_for_multiple_zones(self):
        output, _ = default_rows(pd.DataFrame(dict(System=["HR"], price=[2.])), {("IT", "IT1"), ("IT", "IT2")})
        self.assertEqual(output.System.tolist(), ["HR", "IT"])

    def test_defaults_cannot_mask_a_missing_generated_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            path = data / "heating_individual.csv"
            path.write_bytes(b"period,HR1\n1,2\n")
            complete_defaults(data, {("IT", "IT1")}, [path.name], [], "unused.xlsx", [])
            self.assertEqual(path.read_bytes(), b"period,HR1\n1,2\n")

    def test_default_generator_identifiers_match_their_default_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            pd.DataFrame(dict(System=["HR"], Zone=["HR1"], unit_name=["HR_Wind"], technology=["WTON"])).to_csv(data / "generators.csv", index=False)
            pd.DataFrame(dict(period=[1, 2], HR_Wind=[.2, .5])).to_csv(data / "renewable_availability.csv", index=False)
            pd.DataFrame(dict(period=[1, 2])).to_csv(data / "hydro_inflows.csv", index=False)
            complete_defaults(data, {("IT", "IT1")}, [], [], "unused.xlsx", [])
            fleet = pd.read_csv(data / "generators.csv")
            unit = fleet.loc[fleet.System.eq("IT"), "unit_name"].item()
            curve = pd.read_csv(data / "renewable_availability.csv")
            self.assertEqual(curve[unit].tolist(), [.2, .5])

    def test_every_native_technology_path_has_a_generated_configuration(self):
        names = [selected_workbook(e, m, c) for e, m, c in configurations()]
        self.assertEqual(set(names), set(TECH_WORKBOOKS))
        self.assertEqual(len(names), len(set(names)))

    def test_broken_zip_has_an_actionable_integrity_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.xlsx"
            path.write_bytes(b"not an Excel package")
            self.assertIn("invalid Excel package", workbook_errors(path)[0])

    def test_sheet_replacement_keeps_excel_table_relationships_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "active_zones"
            sheet.append(["System", "zone", "active"])
            sheet.append(["HR", "HR1", "Y"])
            sheet.add_table(Table(displayName="ActiveZones", ref="A1:C2"))
            book.save(path)
            replace_sheets(path, {"active_zones": pd.DataFrame({"System": ["IT", "IT"],
                                                                 "zone": ["IT1", "IT2"], "active": ["Y", "Y"]})})
            self.assertEqual(workbook_errors(path), [])
            restored = load_workbook(path)
            self.assertEqual(restored["active_zones"].tables["ActiveZones"].ref, "A1:C3")
            self.assertEqual(restored["active_zones"]["B3"].value, "IT2")
            restored.close()

    def test_integrity_check_rejects_orphaned_excel_table_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.xlsx"
            book = Workbook()
            book.active.append(["System", "zone"])
            book.active.append(["HR", "HR1"])
            book.active.add_table(Table(displayName="Zones", ref="A1:B2"))
            book.save(path)
            with ZipFile(path) as source:
                part = sheet_paths(source)[book.active.title]
                members = [(copy(i), source.read(i.filename)) for i in source.infolist()]
            broken = Path(directory) / "broken.xlsx"
            import re
            with ZipFile(broken, "w", ZIP_DEFLATED) as target:
                for info, payload in members:
                    if info.filename == part:
                        payload = re.sub(rb"<tableParts.*?</tableParts>", b"", payload)
                    target.writestr(info, payload)
            self.assertTrue(any("relationships disagree" in error for error in workbook_errors(broken)))

    def test_data_and_report_are_published_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "data").mkdir()
            (stage / "data/generators.csv").write_text("new")
            (stage / "manifest.json").write_text("ready")
            (root / "data").mkdir()
            (root / "data/obsolete.csv").write_text("old")
            publish_outputs([(stage / "data", root / "data"), (stage / "manifest.json", root / "manifest.json")], root, "test")
            self.assertEqual([p.name for p in (root / "data").iterdir()], ["generators.csv"])
            self.assertEqual((root / "manifest.json").read_text(), "ready")
            self.assertFalse(list(root.glob("_previous_*")))

    def test_failure_in_second_publication_restores_both_previous_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            for name in ["data", "model_inputs"]:
                (stage / name).mkdir()
                (stage / name / "value").write_text("new")
                (root / name).mkdir()
                (root / name / "value").write_text("old")
            real_replace = Path.replace
            def locked(path, target):
                if path == stage / "data":
                    raise PermissionError("open Excel workbook")
                return real_replace(path, target)
            with patch.object(Path, "replace", locked):
                with self.assertRaisesRegex(PermissionError, "previous bundle was retained"):
                    publish_outputs([(stage / "model_inputs", root / "model_inputs"), (stage / "data", root / "data")], root, "test")
            for name in ["data", "model_inputs"]:
                self.assertEqual((root / name / "value").read_text(), "old")


if __name__ == "__main__":
    unittest.main()
