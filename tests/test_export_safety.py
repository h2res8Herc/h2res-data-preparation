"""Fail early and retain the last export when a later preparation step fails."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_all_sector_inputs as runner
import model_input_bundle as bundle


class ExportSafetyTests(unittest.TestCase):
    def test_original_stage_lock_automatically_publishes_a_verified_copy(self):
        import csv
        import shutil
        from native_data_delivery import publish_outputs
        from sector_method_provenance import file_hash
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def complete(args,reference,stage):
                (stage/'data').mkdir(parents=True)
                (stage/'data/input.csv').write_text('finished data')
                (stage/'h2res_inputs').mkdir()
                shutil.copytree(stage/'data',stage/'h2res_inputs/data')
                (stage/'validation.json').write_text('{"ready":true}')
                (stage/'bundle_manifest.json').write_text(json.dumps({'reference_files':{'input.csv':{}}}))
                with (stage/'h2res_inputs/FILES.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=['file','sha256'])
                    writer.writeheader()
                    writer.writerow(dict(file='data/input.csv',sha256=file_hash(stage/'data/input.csv')))
                return dict(ready=True)
            calls=[]
            def locked_original(pairs,root,tag):
                calls.append(pairs)
                if len(calls)==1:
                    raise PermissionError('original staging path is locked')
                return publish_outputs(pairs,root,tag)
            with patch.object(bundle,'preflight_reference'),patch.object(bundle,'_export_bundle',side_effect=complete), \
                 patch('native_data_delivery.publish_outputs',side_effect=locked_original):
                report=bundle.export_bundle(SimpleNamespace(out_root=root),root/'reference')
            self.assertTrue(report['ready'])
            self.assertEqual(len(calls),2)
            self.assertEqual((root/'data/input.csv').read_text(),'finished data')
            self.assertFalse((root/'model_export_failure.json').exists())

    def test_final_native_publication_failure_keeps_the_completed_export_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data/inputs.csv").write_text("previous")
            def complete(args, reference, stage):
                (stage / "data").mkdir(parents=True)
                (stage / "data/inputs.csv").write_text("new validated inputs")
                (stage / "validation.json").write_text('{"ready":true}')
                (stage / "bundle_manifest.json").write_text('{}')
                return {"ready": True}
            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=complete), \
                 patch("native_data_delivery.publish_outputs", side_effect=PermissionError("directory locked")):
                with self.assertRaisesRegex(PermissionError, "directory locked"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            failure = json.loads((root / "model_export_failure.json").read_text())
            self.assertTrue(failure["recovery_input_coverage_passed"])
            recovered = Path(failure["unvalidated_recovery_bundle"])
            self.assertEqual((recovered / "data/inputs.csv").read_text(), "new validated inputs")
            self.assertEqual((root / "data/inputs.csv").read_text(), "previous")

    def test_package_publication_failure_preserves_validated_recovery_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def complete(args, reference, stage):
                stage.mkdir(parents=True, exist_ok=True)
                (stage / "validation.json").write_text('{"ready":true}')
                (stage / "prepared.csv").write_text("validated data")
                return {"ready": True}
            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=complete), \
                 patch("model_ready_package.build_package", side_effect=PermissionError("folder locked")):
                with self.assertRaises(PermissionError):
                    bundle.export_bundle(SimpleNamespace(out_root=root, model_ready_package=True), root / "reference")
            failure = json.loads((root / "model_export_failure.json").read_text())
            recovered = Path(failure["unvalidated_recovery_bundle"])
            self.assertTrue(failure["recovery_input_coverage_passed"])
            self.assertEqual(failure['phase'],'creating the native input folder and ZIP')
            self.assertIn('folder locked',failure['traceback'])
            self.assertEqual((recovered / "prepared.csv").read_text(), "validated data")
            self.assertFalse((root / "model_inputs").exists())

    def test_native_windows_error_fields_survive_export_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            error=FileNotFoundError(2,'The system cannot find the path specified','missing/technical_2050/input.xlsx')
            error.winerror=3
            with patch.object(bundle,'preflight_reference'),patch.object(bundle,'_export_bundle',side_effect=error):
                with self.assertRaises(FileNotFoundError):bundle.export_bundle(SimpleNamespace(out_root=root),root/'reference')
            failure=json.loads((root/'model_export_failure.json').read_text())
            self.assertEqual(failure['winerror'],3)
            self.assertEqual(failure['filename'],'missing/technical_2050/input.xlsx')
            self.assertIn('FileNotFoundError',failure['traceback'])
            self.assertEqual(failure['phase'],'building and validating native inputs')

    def test_failed_transformation_cannot_reuse_previous_positive_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model_inputs").mkdir()
            (root / "model_inputs/validation.json").write_text('{"ready":true}')
            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=ValueError("invalid new inputs")):
                with self.assertRaises(ValueError):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            failure = json.loads((root / "model_export_failure.json").read_text())
            self.assertNotIn("unvalidated_recovery_bundle", failure)
            self.assertTrue(json.loads((root / "model_inputs/validation.json").read_text())["ready"])

    def test_memory_failure_preserves_unvalidated_work_and_previous_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "data.csv").write_text("previous")
            def out_of_memory(args, reference, stage):
                (stage / "prepared.csv").write_text("prepared but not validated")
                raise MemoryError("allocation failed")
            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=out_of_memory):
                with self.assertRaisesRegex(MemoryError, "Unvalidated work was preserved"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            failure = json.loads((root / "model_export_failure.json").read_text())
            recovery = Path(failure["unvalidated_recovery_bundle"])
            self.assertEqual(recovery.parent, root)
            self.assertEqual((recovery / "prepared.csv").read_text(), "prepared but not validated")
            self.assertEqual((output / "data.csv").read_text(), "previous")
            self.assertFalse((root / "data").exists())

    def test_transformation_failure_leaves_old_bundle_and_user_files_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "data.csv").write_bytes(b"previous good data")
            (output / "notes.txt").write_bytes(b"user notes")

            def fail(args, reference, stage):
                (stage / "data.csv").write_bytes(b"partial replacement")
                raise TypeError("simulated incompatible source value")

            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=fail):
                with self.assertRaisesRegex(TypeError, "incompatible"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            self.assertEqual((output / "data.csv").read_bytes(), b"previous good data")
            self.assertEqual((output / "notes.txt").read_bytes(), b"user notes")
            self.assertFalse(list(root.glob("_model_export_*")))
            self.assertTrue(json.loads((root / "model_export_failure.json").read_text())["previous_bundle_retained"])

    def test_success_preserves_user_files_and_replaces_only_completed_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "notes.txt").write_text("user notes")

            def complete(args, reference, stage):
                (stage / "data.csv").write_text("completed replacement")
                return {"ready": True}

            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=complete):
                report = bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            self.assertTrue(report["ready"])
            self.assertEqual((output / "data.csv").read_text(), "completed replacement")
            self.assertEqual((output / "notes.txt").read_text(), "user notes")
            self.assertFalse(list(root.glob("_model_export_*")))

    def test_publication_failure_rolls_back_previous_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "data.csv").write_text("previous")
            real_replace = Path.replace

            def blocked(path, target):
                if path.name == "model_inputs" and path.parent.name.startswith("_model_export_"):
                    raise PermissionError("file locked")
                return real_replace(path, target)

            with patch.object(bundle, "preflight_reference"), \
                 patch.object(bundle, "_export_bundle", return_value={"ready": True}), \
                 patch.object(Path, "replace", blocked):
                with self.assertRaisesRegex(PermissionError, "previous bundle was retained"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            self.assertEqual((output / "data.csv").read_text(), "previous")

    def test_missing_reference_sheet_stops_before_downloading_or_generating(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            data = reference / "data"
            data.mkdir(parents=True)
            name = bundle.selected_workbook(False, "categories")
            with pd.ExcelWriter(data / name) as writer:
                pd.DataFrame({"System": ["HR"], "zone": ["HR1"], "active": ["Y"]}).to_excel(writer, sheet_name="active_zones", index=False)
                pd.DataFrame({"year": [2025]}).to_excel(writer, sheet_name="tech_cost_years", index=False)
            (reference / "manifest.json").write_text(json.dumps({"files": {name: {}}}))
            with patch("preparation_dependencies.require_for_args"), patch.object(runner, "download") as download, \
                 patch.object(runner, "run_industry") as generation, contextlib.redirect_stderr(io.StringIO()) as error:
                result = runner.main(["--countries", "HR", "--sectors", "industry", "--no-all-model-variants", "--model-reference", str(reference),
                                      "--out-root", str(root / "output"), "--data-root", str(root / "cache")])
            self.assertEqual(result, 2)
            self.assertIn("missing sheets", error.getvalue())
            download.assert_not_called()
            generation.assert_not_called()
            self.assertFalse((root / "output/model_inputs").exists())

    def test_failed_rollback_keeps_previous_data_outside_temporary_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "data.csv").write_text("previous")
            real_replace = Path.replace

            def locked(path, target):
                if ((path.name == "model_inputs" and path.parent.name.startswith("_model_export_"))
                        or path.name.startswith("_model_inputs_previous_")):
                    raise PermissionError("file locked")
                return real_replace(path, target)

            with patch.object(bundle, "preflight_reference"), \
                 patch.object(bundle, "_export_bundle", return_value={"ready": True}), \
                 patch.object(Path, "replace", locked):
                with self.assertRaisesRegex(OSError, "Previous data remain"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            backups = list(root.glob("_model_inputs_previous_*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "data.csv").read_text(), "previous")
            self.assertFalse(list(root.glob("_model_export_*")))

    def test_failed_readiness_check_keeps_new_diagnostics_and_previous_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "model_inputs"
            output.mkdir()
            (output / "validation.json").write_text('{"ready":true}')

            def incomplete(args, reference, stage):
                (stage / "validation.json").write_text('{"ready":false,"errors":["missing demand"]}')
                raise ValueError("Model bundle is incomplete")

            with patch.object(bundle, "preflight_reference"), patch.object(bundle, "_export_bundle", side_effect=incomplete):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    bundle.export_bundle(SimpleNamespace(out_root=root), root / "reference")
            self.assertTrue(json.loads((output / "validation.json").read_text())["ready"])
            failure = json.loads((root / "model_export_failure.json").read_text())
            self.assertEqual(failure["validation"]["errors"], ["missing demand"])

    def test_model_reference_cannot_be_inside_export_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "overwrite the portable model reference"):
                bundle.export_bundle(SimpleNamespace(out_root=root), root / "model_inputs/reference")


if __name__ == "__main__":
    unittest.main()
