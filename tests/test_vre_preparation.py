"""Required wind/solar sourcing must not fail only after other sectors finish."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_all_sector_inputs as runner
from h2res_input_gui import build_command, missing_source_tokens
from preparation_dependencies import dependencies_for_config
from preparation_options import skip_vre_for_config

spec = importlib.util.spec_from_file_location(
    "vre_preparation_test", ROOT / "power/VRES_distributions/build_vre_capacity_weighted_cf_from_schema_openmeteo_weighted.py")
vre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vre)


class VrePreparationTests(unittest.TestCase):
    def test_runner_defaults_to_overnight_weather_quota_wait(self):
        args=runner.build_parser().parse_args([])
        self.assertEqual(args.openmeteo_max_wait,93600.)
        shorter=runner.build_parser().parse_args(['--openmeteo-max-wait','3600'])
        self.assertEqual(shorter.openmeteo_max_wait,3600.)

    def config(self, **changes):
        config = dict(countries="HR", spatial_level="country", out_root="prepared", data_root="cache",
                      sector_power=True, power_output_level="individual", hydro_output_level="individual",
                      hydro_year="2020", vre_year="2020", electricity_demand_year="2020",
                      vre_weather_source="renewables-ninja", vre_calibrate=False,
                      skip_vre=True, skip_electricity_demand=True)
        return {**config, **changes}

    def test_gui_includes_provider_and_calibration_when_profiles_are_required(self):
        command = build_command(self.config())
        self.assertNotIn("--skip-vre-profiles", command)
        self.assertEqual(command[command.index("--vre-weather-source") + 1], "renewables-ninja")
        self.assertIn("--no-vre-calibrate", command)
        self.assertIn("requests", {d.module for d in dependencies_for_config(self.config())})
        self.assertEqual(len(missing_source_tokens(self.config(), {})), 1)

    def test_source_only_and_export_only_choices_are_preserved(self):
        self.assertTrue(skip_vre_for_config(self.config(model_export=False)))
        self.assertTrue(skip_vre_for_config(self.config(model_ready_package=False, require_model_ready=False)))
        self.assertTrue(skip_vre_for_config(self.config(input_action="export existing outputs")))
        self.assertFalse(skip_vre_for_config(self.config(model_ready_package=False, require_model_ready=True)))
        self.assertEqual(missing_source_tokens(self.config(input_action="export existing outputs"), {}), [])

    def test_old_gui_skip_flag_is_normalized_before_dependencies_or_downloads(self):
        for extra, skip_expected in [([], False), (["--no-model-export"], True), (["--export-only"], True),
                                     (["--import-model-inputs"], True)]:
            with self.subTest(extra=extra):
                with patch("preparation_dependencies.require_for_args", side_effect=ImportError("stop at preflight")) as deps, \
                     patch.object(runner, "download") as download, patch.object(runner, "run_power") as power, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = runner.main(["--countries", "HR", "--sectors", "power", "--skip-vre-profiles", *extra])
                self.assertEqual(result, 2)
                self.assertEqual(deps.call_args.args[0].skip_vre_profiles, skip_expected)
                download.assert_not_called()
                power.assert_not_called()

    def test_weather_failure_stops_at_first_unit_and_preserves_previous_curves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / "schema.csv"
            pd.DataFrame(dict(new_unit_name=["HR_A", "HR_B"], technology=["PHOT", "PHOT"],
                              cap_mw_old=[1, 2], lat=[45, 46], lon=[16, 17], System=["HR", "HR"])).to_csv(schema, index=False)
            previous = root / "vre_cf_HR_2020.csv"
            previous.write_bytes(b"previous curves")
            with patch.object(sys, "argv", ["vre", "--schema", str(schema), "--out-dir", str(root),
                                            "--date-from", "2020-01-01", "--date-to", "2020-12-31"]), \
                 patch.object(vre, "fetch_openmeteo_hourly", side_effect=RuntimeError("service unavailable")) as fetch, \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "HR_A.*service unavailable"):
                    vre.main()
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(previous.read_bytes(), b"previous curves")
            summary = pd.read_csv(root / "summary_HR.csv")
            self.assertEqual(summary.status.tolist(), ["ALL_SITES_FAILED"])

    def test_wind_request_uses_power_curve_units_and_reuses_weather_cache(self):
        response = Mock()
        response.status_code=200
        response.json.return_value = {"hourly": {"time": pd.date_range('2020-01-01',periods=24,freq='h').astype(str).tolist(),
                                                 "windspeed_100m": [6.0]*24, "windspeed_10m": [4.0]*24}}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(vre.requests, "get", return_value=response) as fetch, patch.object(vre.time, "sleep"), \
                 patch.dict('os.environ', {'H2RES_OPENMETEO_QUOTA_DB':str(Path(directory)/'quota.sqlite3')}):
                args = dict(lat=45, lon=16, date_from="2020-01-01", date_to="2020-01-01", timezone="UTC",
                            want_pv=False, want_wind=True, cache_dir=Path(directory))
                first = vre.fetch_openmeteo_hourly(**args)
                second = vre.fetch_openmeteo_hourly(**args)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(fetch.call_args.kwargs["params"]["wind_speed_unit"], "ms")
                pd.testing.assert_frame_equal(first, second)


if __name__ == "__main__":
    unittest.main()
