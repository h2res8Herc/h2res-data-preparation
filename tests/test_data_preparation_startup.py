"""Launcher and standalone frontend regressions; never run an energy model."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h2res_input_gui import DataPreparationGui, build_command


class PreparationFrontendTests(unittest.TestCase):
    def test_legacy_settings_cannot_turn_frontend_into_model_import_or_execution(self):
        app = DataPreparationGui.__new__(DataPreparationGui)
        settings = dict(countries="HR", spatial_level="country", out_root="prepared", data_root="cache",
                        sector_industry=True, industry_mode="complex", efuels=True, input_action="import model inputs",
                        model_root=r"D:\example-model", model_reference="model_reference")
        app.vars = {key: Mock(get=Mock(return_value=value)) for key, value in settings.items()}
        command = build_command(app.config())
        self.assertEqual(Path(command[1]).name, "generate_all_sector_inputs.py")
        for flag in ["--model-root", "--import-model-inputs", "--solve", "--read-with-model"]:
            self.assertNotIn(flag, command)
        self.assertIn("--model-export", command)
        self.assertIn("--complex-industry-sectors", command)

    @unittest.skipUnless(sys.platform == "win32", "Windows batch launcher")
    def test_new_and_legacy_launchers_handle_parentheses_in_package_path(self):
        for filename in ["START_DATA_PREPARATION.bat", "START_H2RES_GUI.bat"]:
            # The actual workspace includes both spaces and parentheses. -Check
            # exercises discovery and script startup without opening a window.
            with self.subTest(launcher=filename):
                result = subprocess.run(["cmd.exe", "/d", "/c", str(ROOT / filename), "-Check"], cwd=ROOT,
                                        input="\n", capture_output=True, text=True, timeout=45)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('"startup_check_passed": true', result.stdout)


if __name__ == "__main__":
    unittest.main()
