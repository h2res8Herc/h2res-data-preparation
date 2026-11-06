"""Check selected preparation pipelines before downloads or output changes."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Dependency:
    module: str
    package: str
    purpose: str


BASE = [Dependency(name, name, "input tables") for name in ("numpy", "pandas", "openpyxl")]
SPATIAL = [Dependency(name, name, "spatial allocation and vector files") for name in
           ("geopandas", "shapely", "pyproj", "pyogrio")]


def selected_dependencies(sectors, *, industry_mode="categories", temperature_source="open-meteo",
                          skip_heating_raw=False, era5=None, skip_vre=False, export_only=False):
    result = list(BASE)
    if export_only:
        return result
    sectors = set(sectors)
    regular_industry = "industry" in sectors and industry_mode != "complex"
    raw_heating = "heating" in sectors and not skip_heating_raw
    if "power" in sectors or "transport" in sectors or regular_industry or raw_heating:
        result.extend(SPATIAL)
    if "transport" in sectors or regular_industry or raw_heating:
        result.append(Dependency("rasterio", "rasterio", "source raster allocation"))
    if "transport" in sectors:
        result.append(Dependency("osmium", "osmium", "paper-method rail, port and airport infrastructure"))
    if regular_industry:
        result.extend([Dependency("rasterstats", "rasterstats", "industry raster allocation"),
                       Dependency("pyxlsb", "pyxlsb", "industry source workbooks")])
    if "power" in sectors and not skip_vre:
        result.append(Dependency("requests", "requests", "wind and solar source requests"))
    if raw_heating:
        result.extend([Dependency("pycountry", "pycountry", "heating country identifiers"),
                       Dependency("xarray", "xarray", "heating weather arrays"),
                       Dependency("netCDF4", "netCDF4", "weather NetCDF input/output")])
        if temperature_source == "cds-netcdf" and not era5:
            result.append(Dependency("cdsapi", "cdsapi", "automatic CDS weather download"))
    return list({item.module: item for item in result}.values())


def dependencies_for_config(config):
    from preparation_options import skip_vre_for_config
    sectors = [s for s in ("power", "industry", "transport", "heating") if config.get("sector_" + s, False)]
    mode = "categories" if config.get("all_model_variants", True) and config.get("model_export", True) else config.get("industry_mode", "categories")
    return selected_dependencies(sectors, industry_mode=mode,
                                 temperature_source=config.get("temperature_source", "open-meteo"),
                                 skip_heating_raw=config.get("skip_heating_raw", False), era5=config.get("era5"),
                                 skip_vre=skip_vre_for_config(config),
                                 export_only=config.get("input_action", "generate") != "generate")


def missing_dependencies(required):
    missing = []
    for dependency in required:
        try:
            importlib.import_module(dependency.module)
        except (ImportError, OSError) as exc:
            missing.append({"module": dependency.module, "package": dependency.package,
                            "purpose": dependency.purpose, "error": str(exc)})
    return missing


def require_dependencies(required):
    missing = missing_dependencies(required)
    if missing:
        requirements = ROOT / ("requirements-cds.txt" if any(item["package"] == "cdsapi" for item in missing) else "requirements.txt")
        command = subprocess.list2cmdline([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
        details = "\n".join(f"  {item['package']}: {item['purpose']} ({item['error']})" for item in missing)
        raise ImportError(f"Missing or unusable packages in Python {sys.executable}:\n{details}\n"
                          f"Install the preparation dependencies with this interpreter:\n  {command}\n"
                          "In PowerShell, prefix the command with &. No downloads or preparation have started.")


def require_for_args(args):
    mode = "categories" if getattr(args, "all_model_variants", False) and args.model_export else args.industry_mode
    require_dependencies(selected_dependencies(args.sectors, industry_mode=mode,
                         temperature_source=args.temperature_source, skip_heating_raw=args.skip_heating_raw,
                         era5=args.era5, skip_vre=args.skip_vre_profiles,
                         export_only=args.export_only or args.import_model_inputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sectors", default="power,industry,transport,heating")
    parser.add_argument("--industry-mode", choices=("regular", "categories", "complex"), default="categories")
    args = parser.parse_args()
    required = selected_dependencies(args.sectors.split(","), industry_mode=args.industry_mode)
    missing = missing_dependencies(required)
    print(json.dumps({"python": sys.executable, "ready": not missing,
                      "checked_modules": [d.module for d in required], "missing": missing}, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
