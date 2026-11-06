"""Check dependencies before network calls and output cleanup."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import preparation_dependencies as deps


class PreparationDependencyTests(unittest.TestCase):
    def test_power_requires_spatial_stack_even_without_vre(self):
        names = {item.module for item in deps.selected_dependencies(["power"], skip_vre=True)}
        self.assertTrue({"geopandas", "shapely", "pyproj", "pyogrio"}.issubset(names))
        self.assertNotIn("rasterstats", names)

    def test_complex_industry_does_not_require_raster_allocation(self):
        names = {item.module for item in deps.selected_dependencies(["industry"], industry_mode="complex")}
        self.assertEqual(names, {"numpy", "pandas", "openpyxl"})

    def test_regular_industry_includes_embedded_helper_dependencies(self):
        names = {item.module for item in deps.selected_dependencies(["industry"], industry_mode="categories")}
        self.assertTrue({"geopandas", "rasterio", "rasterstats", "pyxlsb"}.issubset(names))

    def test_cds_is_only_required_for_cds_downloads(self):
        names = lambda **kw: {d.module for d in deps.selected_dependencies(["heating"], **kw)}
        self.assertNotIn("cdsapi", names())
        self.assertIn("cdsapi", names(temperature_source="cds-netcdf"))
        self.assertNotIn("cdsapi", names(temperature_source="cds-netcdf", era5="cached.nc"))

    def test_missing_package_error_identifies_active_python_and_install_file(self):
        with patch.object(deps.importlib, "import_module", side_effect=ModuleNotFoundError("No module named 'geopandas'")):
            with self.assertRaises(ImportError) as failure:
                deps.require_dependencies([deps.Dependency("geopandas", "geopandas", "plant allocation")])
        self.assertIn(sys.executable, str(failure.exception))
        self.assertIn("requirements.txt", str(failure.exception))
        self.assertIn("geopandas", str(failure.exception))

    def test_raw_power_fails_before_downloading_or_deleting_prepared_files(self):
        path = ROOT / "power/generators/generate_genco_power_sector.py"
        spec = importlib.util.spec_from_file_location("power_dependency_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.build_parser().parse_args([])
        with patch.object(deps, "require_dependencies", side_effect=ImportError("missing geopandas")), \
             patch.object(module, "prepare_raw_sources") as download, \
             patch.object(module, "clean_built_outputs") as cleanup:
            with self.assertRaisesRegex(ImportError, "missing geopandas"):
                module.run_raw_builder(args)
            download.assert_not_called()
            cleanup.assert_not_called()

    def test_raw_power_cleanup_preserves_other_countries(self):
        path = ROOT / "power/generators/generate_genco_power_sector.py"
        spec = importlib.util.spec_from_file_location("power_cleanup_test", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for country in ("HR", "IT"):
                (root / f"genco_{country}_built.csv").write_text(country)
            module.clean_built_outputs(root, ["HR"])
            self.assertFalse((root / "genco_HR_built.csv").exists())
            self.assertEqual((root / "genco_IT_built.csv").read_text(), "IT")

    def test_failed_raw_builder_does_not_clear_previous_cache(self):
        path = ROOT / "power/generators/generate_genco_power_sector.py"
        spec = importlib.util.spec_from_file_location("power_failed_build_test", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = module.build_parser().parse_args([])
            args.built_dir = root / "built"
            args.built_dir.mkdir()
            old = args.built_dir / "genco_HR_built.csv"
            old.write_text("previous")
            source = root / "source.csv"
            source.write_text("header")
            for field in ("powerplants", "jrc_hydro", "template_genco", "hr_defaults_xlsx", "nuts3_geojson"):
                setattr(args, field, source)
            with patch.object(deps, "require_dependencies"), patch.object(module, "prepare_raw_sources"), \
                 patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ['builder'])), \
                 patch.object(module, "clean_built_outputs") as cleanup:
                with self.assertRaises(subprocess.CalledProcessError):
                    module.run_raw_builder(args)
                cleanup.assert_not_called()
            self.assertEqual(old.read_text(), "previous")

    def test_locked_raw_destination_retains_its_previous_contents(self):
        path = ROOT / "power/generators/generate_genco_power_sector.py"
        spec = importlib.util.spec_from_file_location("power_locked_output_test", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = module.build_parser().parse_args([])
            args.built_dir = root / "built"
            args.built_dir.mkdir()
            old = args.built_dir / "genco_HR_built.csv"
            old.write_text("previous")
            source = root / "source.csv"
            source.write_text("header")
            for field in ("powerplants", "jrc_hydro", "template_genco", "hr_defaults_xlsx", "nuts3_geojson"):
                setattr(args, field, source)

            def build(command, **kwargs):
                folder = Path(command[command.index("--out-dir") + 1])
                (folder / old.name).write_text("replacement")

            with patch.object(deps, "require_dependencies"), patch.object(module, "prepare_raw_sources"), \
                 patch.object(module.subprocess, "run", side_effect=build), \
                 patch.object(Path, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    module.run_raw_builder(args)
            self.assertEqual(old.read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
