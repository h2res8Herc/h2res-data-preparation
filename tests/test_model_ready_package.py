"""Selected native files, honest readiness and safe delivery publication."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import pandas as pd
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h2res_input_gui import build_command, missing_source_tokens
from model_ready_package import build_package, FOLDER, ARCHIVE
import model_input_bundle as bundle_module


class ModelReadyPackageTests(unittest.TestCase):
    def fixture(self, root, ready=True):
        data = root / "data"
        data.mkdir()
        for name in ("flex_tech_categories.xlsx", "flex_tech.xlsx", "policy.xlsx", "policy_efuel.xlsx", "policy_fuels.xlsx", "h2_terminals.xlsx"):
            book = Workbook()
            book.active.title = "test"
            book.active.append(["cost", "cached-formula"])
            book.active.append([341.663728186051, "=1+2"])
            book.save(data / name)
            book.close()
        (data / "industry_heat.csv").write_bytes(b"period,HR1\n1,1.25\n2,3.75\n")
        # A local extra file must not leak into the delivery just because it is CSV.
        (data / "private_notes.csv").write_bytes(b"not a model input")
        reference = {name: {} for name in ("flex_tech_categories.xlsx", "flex_tech.xlsx", "industry_heat.csv", "policy.xlsx", "policy_efuel.xlsx", "policy_fuels.xlsx", "h2_terminals.xlsx")}
        metadata = dict(industry_mode="categories", efuels=False, countries=["HR"], generated_sectors=["industry"],
                        reference_files=reference, generated_files=["industry_heat.csv"])
        (root / "bundle_manifest.json").write_text(json.dumps(metadata))
        report = dict(ready=ready, industry_mode="categories", efuels=False, technology_workbook="flex_tech_categories.xlsx",
                      industry_electricity_case="conservative", active_zones=["HR1"],
                      errors=[] if ready else ["electricity_demand.csv lacks selected zone"])
        (root / "validation.json").write_text(json.dumps(report))
        return report

    def test_delivery_contains_selected_workbook_and_distributions_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            summary = build_package(root, report)
            folder = root / summary["folder"]
            self.assertTrue(summary["ready"])
            self.assertEqual({path.name for path in (folder / "data").glob("flex_tech*.xlsx")}, {"flex_tech_categories.xlsx", "flex_tech.xlsx"})
            self.assertTrue(json.loads((folder / "package_manifest.json").read_text())["data_layout"]["matches_reference"])
            self.assertFalse((folder / "data/private_notes.csv").exists())
            for name in ("flex_tech_categories.xlsx", "industry_heat.csv"):
                self.assertEqual((folder / "data" / name).read_bytes(), (root / "data" / name).read_bytes())
            selection = json.loads((folder / "model_input_selection.json").read_text())
            self.assertEqual(selection["sector_sources"]["industry"], "generated")
            self.assertEqual(selection["sector_sources"]["heating"], "portable reference")
            self.assertTrue(selection["model_flags"]["model_industry_categories"])
            with ZipFile(root / summary["archive"]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(FOLDER + "/data/flex_tech_categories.xlsx", archive.namelist())
                self.assertNotIn(FOLDER + "/" + ARCHIVE, archive.namelist())
                self.assertEqual(archive.read(FOLDER + "/data/industry_heat.csv"), (root / "data/industry_heat.csv").read_bytes())
            files = pd.read_csv(folder / "FILES.csv")
            row = files.loc[files.file.eq("data/industry_heat.csv")].iloc[0]
            self.assertEqual(row.sha256, hashlib.sha256((root / "data/industry_heat.csv").read_bytes()).hexdigest())

    def test_technical_variant_packages_below_legacy_windows_path_limit(self):
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve()
            # Reproduce the user's 126-character output directory exactly.
            output=base/('case_'+'x'*(126-len(str(base))-6))
            self.assertEqual(len(str(output)),126)
            root=output/'_model_export_12345678'/'model_inputs'
            root.mkdir(parents=True)
            report=self.fixture(root)
            relative='variants/technical_2050/flex_tech_efuel_categories.xlsx'
            source=root/'data'/relative
            source.parent.mkdir(parents=True)
            source.write_bytes(b'untouched inactive variant')
            metadata=json.loads((root/'bundle_manifest.json').read_text())
            metadata['reference_files'][relative]={}
            (root/'bundle_manifest.json').write_text(json.dumps(metadata))
            old=root/'_input_package_12345678'/FOLDER/'data'/relative
            self.assertGreaterEqual(len(str(old)),260)
            copy=shutil.copy2
            destinations=[]
            def legacy_copy(src,dst,*args,**kwargs):
                destinations.append(str(dst))
                if len(str(dst))>=260:
                    error=FileNotFoundError('The system cannot find the path specified')
                    error.winerror=3
                    raise error
                return copy(src,dst,*args,**kwargs)
            with patch('model_ready_package.shutil.copy2',side_effect=legacy_copy):
                result=build_package(root,report)
            self.assertTrue(result['ready'])
            self.assertLess(max(map(len,destinations)),260)
            self.assertEqual((root/FOLDER/'data'/relative).read_bytes(),source.read_bytes())

    def test_recovery_rebuilds_missing_package_and_publishes_without_regeneration(self):
        from native_data_delivery import retry_prepared_publication
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            recovery=root/'_unpublished_model_inputs_test'
            recovery.mkdir()
            report=self.fixture(recovery)
            (recovery/'data/private_notes.csv').unlink()
            report['variants']=[{k:report[k] for k in ('ready','technology_workbook','efuels','industry_mode','industry_electricity_case')},
                                dict(ready=True,technology_workbook='flex_tech.xlsx',efuels=False,industry_mode='regular',industry_electricity_case='conservative')]
            (recovery/'validation.json').write_text(json.dumps(report))
            (root/'data').mkdir();(root/'data/previous.txt').write_text('old data')
            def valid(path,filename,efuels,mode,case):
                return dict(ready=True,technology_workbook=filename,efuels=efuels,industry_mode=mode,
                            industry_electricity_case=case,active_zones=['HR1'],errors=[],warnings=[])
            with patch.object(bundle_module,'validate_bundle',side_effect=valid) as validate:
                result=retry_prepared_publication(recovery,root)
            self.assertTrue(result['ready'])
            self.assertEqual(validate.call_count,2)
            self.assertTrue((root/'model_inputs/h2res_inputs'/ARCHIVE).is_file())
            self.assertEqual((root/'data/industry_heat.csv').read_bytes(),(root/'model_inputs/data/industry_heat.csv').read_bytes())
            self.assertFalse((root/'data/previous.txt').exists())

    def test_missing_package_recovery_revalidates_before_replacing_live_data(self):
        from native_data_delivery import retry_prepared_publication
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);recovery=root/'_unpublished_model_inputs_test';recovery.mkdir()
            self.fixture(recovery);(recovery/'data/private_notes.csv').unlink()
            (root/'data').mkdir();(root/'data/previous.txt').write_text('old data')
            with patch.object(bundle_module,'validate_bundle',return_value=dict(ready=False,errors=['missing profile'])), \
                 patch('model_ready_package.build_package') as package:
                with self.assertRaisesRegex(ValueError,'missing profile'):
                    retry_prepared_publication(recovery,root)
                package.assert_not_called()
            self.assertEqual((root/'data/previous.txt').read_text(),'old data')
            self.assertTrue((recovery/'data/industry_heat.csv').is_file())

    def test_incomplete_data_cannot_be_published_as_h2res_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root, ready=False)
            with self.assertRaisesRegex(ValueError, "electricity_demand.csv"):
                build_package(root, report)
            self.assertFalse((root / FOLDER).exists())

    def test_incomplete_update_retains_last_valid_input_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            build_package(root, report)
            previous = (root / FOLDER / ARCHIVE).read_bytes()
            report.update(ready=False, errors=["missing country profile"])
            with self.assertRaisesRegex(ValueError, "missing country profile"):
                build_package(root, report)
            self.assertEqual((root / FOLDER / ARCHIVE).read_bytes(), previous)

    def test_failed_archive_creation_keeps_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            build_package(root, report)
            archive = root / FOLDER / ARCHIVE
            previous = archive.read_bytes()
            created=[]
            def staging(**kwargs):
                temporary=tempfile.TemporaryDirectory(**kwargs)
                created.append(Path(temporary.name))
                return temporary
            with patch("model_ready_package.ZipFile", side_effect=OSError("disk full")), \
                 patch('model_ready_package.TemporaryDirectory',side_effect=staging):
                with self.assertRaisesRegex(OSError, "disk full"):
                    build_package(root, report)
            self.assertEqual(archive.read_bytes(), previous)
            self.assertEqual(len(created),1)
            self.assertFalse(created[0].exists())

    def test_locked_publication_restores_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            build_package(root, report)
            previous = (root / FOLDER / ARCHIVE).read_bytes()
            real_replace = Path.replace

            def locked(path, target):
                if path.name == FOLDER and path.parent.name.startswith("_ip_"):
                    raise PermissionError("locked")
                return real_replace(path, target)

            with patch.object(Path, "replace", locked), self.assertRaises(PermissionError):
                build_package(root, report)
            self.assertEqual((root / FOLDER / ARCHIVE).read_bytes(), previous)

    def test_source_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            path = root / "bundle_manifest.json"
            metadata = json.loads(path.read_text())
            metadata["reference_files"]["../private.csv"] = {}
            path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "outside the bundle"):
                build_package(root, report)

    def test_full_model_tree_keeps_sources_readme_and_technical_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            additions = {"README.md": b"model data paths", "sources/source.xlsx": b"source archive bytes",
                         "variants/technical_2050/flex_tech_efuel_categories.xlsx": b"alternative archive bytes"}
            path = root / "bundle_manifest.json"
            metadata = json.loads(path.read_text())
            metadata.update(data_layout="model-directory-mirror", data_directories=["sources", "variants", "variants/technical_2050"])
            for name, contents in additions.items():
                target = root / "data" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
                metadata["reference_files"][name] = {}
            path.write_text(json.dumps(metadata))
            result = build_package(root, report)
            with ZipFile(root / result["archive"]) as archive:
                for name, contents in additions.items():
                    self.assertEqual(archive.read(FOLDER + "/data/" + name), contents)
            packaged = {p.relative_to(root / FOLDER / "data").as_posix() for p in (root / FOLDER / "data").rglob('*') if p.is_file()}
            self.assertEqual(packaged, set(metadata["reference_files"]))

    def test_gui_selects_package_without_enabling_model_execution(self):
        config = dict(countries="HR", spatial_level="country", out_root="out", data_root="cache", sector_industry=True,
                      industry_mode="categories", model_export=True)
        command = build_command(config)
        self.assertIn("--model-ready-package", command)
        self.assertNotIn("--solve", command)
        config["model_ready_package"] = False
        self.assertIn("--no-model-ready-package", build_command(config))
        config.update(model_ready_package=True, model_export=False)
        self.assertIn("--no-model-ready-package", build_command(config))

    def test_reexport_needs_no_api_tokens(self):
        config = dict(input_action="export existing outputs", sector_power=True, vre_weather_source="renewables-ninja")
        self.assertEqual(missing_source_tokens(config, {}), [])
        config["input_action"] = "generate"
        self.assertEqual(len(missing_source_tokens(config, {})), 2)
        config.update(skip_vre=True, skip_electricity_demand=True)
        # Source-only runs may skip weather. Complete packages still need it.
        config["model_export"] = False
        self.assertEqual(missing_source_tokens(config, {}), [])

    def test_standalone_rechecks_coverage_instead_of_trusting_old_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = self.fixture(root)
            current = {**saved, "ready": False, "errors": ["changed profile is incomplete"]}
            with patch.object(bundle_module, "validate_bundle", return_value=current) as validate:
                with self.assertRaisesRegex(ValueError, "changed profile is incomplete"):
                    build_package(root)
            validate.assert_called_once()
            self.assertFalse((root / FOLDER).exists())

    def test_cli_model_package_enforces_complete_coverage(self):
        import generate_all_sector_inputs as runner
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for flags, required in (([], True), (["--no-model-ready-package"], False)):
                with self.subTest(flags=flags), patch("preparation_dependencies.require_for_args"), \
                     patch.object(runner, "reference_for", return_value=root / "reference"), \
                     patch.object(runner, "export_bundle") as export:
                    self.assertEqual(runner.main(["--export-only", "--out-root", str(root / "out"),
                                                  "--data-root", str(root / "cache"), *flags]), 0)
                    self.assertEqual(export.call_args.args[0].require_model_ready, required)

    def test_configuration_change_preserves_native_tree_and_updates_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.fixture(root)
            build_package(root, report)
            metadata_path = root / "bundle_manifest.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["industry_mode"] = "regular"
            metadata_path.write_text(json.dumps(metadata))
            report.update(industry_mode="regular", technology_workbook="flex_tech.xlsx")
            (root / "validation.json").write_text(json.dumps(report))
            build_package(root, report)
            self.assertEqual({p.name for p in (root / FOLDER / "data").glob("flex_tech*.xlsx")}, {"flex_tech.xlsx", "flex_tech_categories.xlsx"})
            self.assertEqual(json.loads((root / FOLDER / "model_input_selection.json").read_text())["technology_workbook"], "data/flex_tech.xlsx")
            self.assertTrue((root / "data/flex_tech_categories.xlsx").is_file())

    def test_failed_packaging_does_not_replace_previous_native_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model_inputs").mkdir()
            previous = root / "model_inputs/keep.txt"
            previous.write_text("previous bundle")
            with patch.object(bundle_module, "preflight_reference"), \
                 patch.object(bundle_module, "_export_bundle", return_value={"ready": True}), \
                 patch("model_ready_package.build_package", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    bundle_module.export_bundle(SimpleNamespace(out_root=root, model_ready_package=True), root / "reference")
            self.assertEqual(previous.read_text(), "previous bundle")


if __name__ == "__main__":
    unittest.main()
