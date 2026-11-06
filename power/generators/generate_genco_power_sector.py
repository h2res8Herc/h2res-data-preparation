#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Single entry point for power-sector GENCO table generation.

The normal pipeline rebuilds per-country GENCO files from raw sources:

1) non-hydro units from the powerplants database,
2) hydro units from the JRC hydro database,
3) template/default GENCO parameters from an HR reference GENCO file,
4) NUTS3 assignment from a NUTS GeoJSON.

It then combines the per-country files into one power-sector GENCO table.
Hydro inflow distributions and VRES profile/API generation are intentionally
out of scope for this script.

Examples
--------
Run the full raw-source pipeline:
    python generators/generate_genco_power_sector.py \
      --powerplants data/powerplants.csv \
      --nuts3-geojson data/NUTS_RG_20M_2021_4326.geojson

Run the full raw-source pipeline for selected countries:
    python generators/generate_genco_power_sector.py \
      --powerplants data/powerplants.csv \
      --nuts3-geojson data/NUTS_RG_20M_2021_4326.geojson \
      --countries HR,SI,IT

Combine already-built local country files only:
    python generators/generate_genco_power_sector.py --mode built
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DEFAULT_EXISTING_BUILT_DIR = SCRIPT_DIR / "genco_built_all"
DEFAULT_RAW_BUILT_DIR = SCRIPT_DIR / "genco_built_from_raw"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_POWERPLANTS = DEFAULT_DATA_DIR / "powerplants.csv"
DEFAULT_HYDRO = DEFAULT_DATA_DIR / "jrc-hydro-power-plant-database.csv"
DEFAULT_NUTS3 = DEFAULT_DATA_DIR / "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
DEFAULT_INTERNAL_GENCO = DEFAULT_DATA_DIR / "genco_reference_defaults.csv"
DEFAULT_OUT = SCRIPT_DIR / "genco_power_sector.csv"
DEFAULT_TEMPLATE_GENCO = DEFAULT_EXISTING_BUILT_DIR / "genco_HR_built.csv"
DEFAULT_HR_DEFAULTS = DEFAULT_EXISTING_BUILT_DIR / "genco_HR_built.csv"

POWERPLANTS_URL = "https://raw.githubusercontent.com/PyPSA/powerplantmatching/master/powerplants.csv"
JRC_HYDRO_URL = (
    "https://raw.githubusercontent.com/energy-modelling-toolkit/"
    "hydro-power-database/master/data/jrc-hydro-power-plant-database.csv"
)
NUTS3_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
)

GENCO_COLUMNS = [
    "unit_name",
    "cap_mw",
    "fuel_type",
    "decom_start_existing_cap",
    "life_time",
    "decom_start_new",
    "final_life_cap",
    "efficiency",
    "cost_no_fuel",
    "RampingCost",
    "CO2Intensity",
    "technology",
    "RampUpRate",
    "RampDownRate",
    "CHPType",
    "STOCapacity",
    "STOSelfDischarge",
    "STOMaxChargingPower",
    "STOChargingEfficiency",
    "CHPPowerToHeat",
    "CHPPowerLossFactor",
    "CHPMaxHeat",
    "System",
    "Zone",
    "NUTS3",
    "lat",
    "lon",
]

SDEWES18_COLUMNS = [
    "unit_name",
    "cap_mw",
    "max_cap",
    "fuel_type",
    "decom_start_existing_cap",
    "life_time",
    "decom_start_new",
    "final_life_cap",
    "efficiency",
    "cost_no_fuel",
    "RampingCost",
    "CO2Intensity",
    "technology",
    "RampUpRate",
    "RampDownRate",
    "CHPType",
    "STOCapacityGWh",
    "STOSelfDischarge",
    "STOMaxChargingPower",
    "STOChargingEfficiency",
    "CHPPowerToHeat",
    "CHPPowerLossFactor",
    "CHPMaxHeat",
    "System",
    "Zone",
]

REFERENCE_DEFAULT_ROWS = [
    ("Coal_STUR_REF", 1, "Coal", 20, 35, 25, 1, 0.38, 0, 0, 0.34, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Gas_COMC_REF", 1, "Gas", 20, 30, 25, 1, 0.55, 0, 0, 0.20, "COMC", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Gas_GTUR_REF", 1, "Gas", 20, 30, 25, 1, 0.39, 0, 0, 0.20, "GTUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Gas_STUR_REF", 1, "Gas", 20, 30, 25, 1, 0.42, 0, 0, 0.20, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Oil_STUR_REF", 1, "Oil", 20, 30, 25, 1, 0.38, 0, 0, 0.27, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Oil_COMC_REF", 1, "Oil", 20, 30, 25, 1, 0.40, 0, 0, 0.27, "COMC", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Nuclear_STUR_REF", 1, "Nuclear", 20, 50, 25, 1, 0.33, 0, 0, 0.00, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Biomass_STUR_REF", 1, "Biomass", 20, 25, 25, 1, 0.35, 0, 0, 0.00, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Waste_STUR_REF", 1, "Waste", 20, 25, 25, 1, 0.30, 0, 0, 0.00, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Geothermal_STUR_REF", 1, "Geothermal", 20, 25, 25, 1, 0.90, 0, 0, 0.00, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Wind_WTON_REF", 1, "Wind", 20, 25, 25, 1, 1.00, 0, 0, 0.00, "WTON", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Wind_WTOF_REF", 1, "Wind", 20, 25, 25, 1, 1.00, 0, 0, 0.00, "WTOF", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Solar_PHOT_REF", 1, "Solar", 20, 25, 25, 1, 1.00, 0, 0, 0.00, "PHOT", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Hydro_HDAM_REF", 1, "Hydro", 20, 50, 25, 1, 0.90, 0, 0, 0.00, "HDAM", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Hydro_HROR_REF", 1, "Hydro", 20, 50, 25, 1, 0.90, 0, 0, 0.00, "HROR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Hydro_HPHS_REF", 1, "Hydro", 20, 50, 25, 1, 0.90, 0, 0, 0.00, "HPHS", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
    ("Other_STUR_REF", 1, "Other", 20, 25, 25, 1, 0.35, 0, 0, 0.00, "STUR", 1, 1, "N", 0, 0, 0, 0.9, 0, 0, 0, "REF", "REF1", "", "", ""),
]


def parse_countries(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    countries = [c.strip().upper() for c in raw.split(",") if c.strip()]
    return countries or None


def download_file(url: str, out_path: Path, refresh: bool = False) -> Path:
    if out_path.exists() and not refresh:
        print(f"Using cached source: {out_path}", flush=True)
        return out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}", flush=True)
    print(f"  -> {out_path}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "h2res-genco-builder/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    out_path.write_bytes(data)
    return out_path


def write_internal_reference_genco(out_path: Path) -> Path:
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(REFERENCE_DEFAULT_ROWS, columns=GENCO_COLUMNS)
    df.to_csv(out_path, index=False)
    print(f"Wrote internal GENCO reference defaults: {out_path}", flush=True)
    return out_path


def normalize_jrc_hydro_file(path: Path) -> None:
    df = pd.read_csv(path)
    changed = False

    rename = {
        "installed_capacity_MW": "capacity_mw",
        "avg_annual_generation_GWh": "annual_generation_gwh",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
            changed = True

    if "annual_generation_gwh" in df.columns and "annual_generation_mwh" not in df.columns:
        df["annual_generation_mwh"] = pd.to_numeric(df["annual_generation_gwh"], errors="coerce") * 1000.0
        changed = True

    if "capacity_mw" not in df.columns:
        raise ValueError(
            f"JRC hydro source {path} does not contain capacity_mw or installed_capacity_MW"
        )

    required = ["name", "capacity_mw", "type", "country_code", "lat", "lon"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"JRC hydro source {path} is missing required columns: {missing}")

    if changed:
        df.to_csv(path, index=False)
        print(f"Normalized JRC hydro columns in: {path}", flush=True)


def prepare_raw_sources(args: argparse.Namespace) -> None:
    if args.download_sources:
        download_file(args.powerplants_url, args.powerplants, refresh=args.refresh_sources)
        download_file(args.jrc_hydro_url, args.jrc_hydro, refresh=args.refresh_sources)
        download_file(args.nuts3_url, args.nuts3_geojson, refresh=args.refresh_sources)

    if args.template_genco is None:
        args.template_genco = DEFAULT_TEMPLATE_GENCO if DEFAULT_TEMPLATE_GENCO.exists() else DEFAULT_INTERNAL_GENCO
    if args.hr_defaults_xlsx is None:
        args.hr_defaults_xlsx = DEFAULT_HR_DEFAULTS if DEFAULT_HR_DEFAULTS.exists() else DEFAULT_INTERNAL_GENCO

    for path in [args.template_genco, args.hr_defaults_xlsx]:
        if path == DEFAULT_INTERNAL_GENCO or (
            path is not None
            and path.name == DEFAULT_INTERNAL_GENCO.name
            and not path.exists()
        ):
            write_internal_reference_genco(path)

    normalize_jrc_hydro_file(args.jrc_hydro)


def is_iso2_built_file(path: Path) -> bool:
    return re.fullmatch(r"genco_[A-Z]{2}_built\.csv", path.name) is not None


def built_file_country(path: Path) -> str:
    m = re.fullmatch(r"genco_(.+)_built\.csv", path.name)
    if not m:
        raise ValueError(f"Not a GENCO built file name: {path.name}")
    return m.group(1).upper()


def discover_built_files(
    built_dir: Path,
    countries: Sequence[str] | None,
    include_country_name_files: bool,
) -> list[Path]:
    if not built_dir.exists():
        raise FileNotFoundError(f"Built GENCO directory not found: {built_dir}")

    files = sorted(built_dir.glob("genco_*_built.csv"))
    if not include_country_name_files:
        files = [p for p in files if is_iso2_built_file(p)]

    if countries:
        wanted = set(countries)
        files = [p for p in files if built_file_country(p) in wanted]
        missing = sorted(wanted - {built_file_country(p) for p in files})
        if missing:
            raise FileNotFoundError(
                "Missing built GENCO files for countries: "
                + ", ".join(missing)
                + f" in {built_dir}"
            )

    if not files:
        raise FileNotFoundError(f"No built GENCO CSV files selected in {built_dir}")

    return files


def read_genco_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in GENCO_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing GENCO columns: {missing}")

    df = df[GENCO_COLUMNS].copy()
    df["source_file"] = path.name
    return df


def make_unit_names_unique(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    keys = df["unit_name"].fillna("unit").astype(str)

    counts: dict[str, int] = {}
    used: set[str] = set()
    out: list[str] = []
    for i, name in enumerate(keys):
        system = str(df.iloc[i].get("System", "") or "").strip()
        base = name.strip() or "unit"
        scoped = f"{system}_{base}" if system and not base.startswith(f"{system}_") else base

        counts[scoped] = counts.get(scoped, 0) + 1
        candidate = scoped if counts[scoped] == 1 else f"{scoped}_{counts[scoped]}"
        while candidate in used:
            counts[scoped] += 1
            candidate = f"{scoped}_{counts[scoped]}"
        used.add(candidate)
        out.append(candidate)

    df["unit_name"] = out
    return df


def format_sdewes18(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["max_cap"] = out["cap_mw"]

    if "STOCapacity" in out.columns:
        out["STOCapacityGWh"] = pd.to_numeric(out["STOCapacity"], errors="coerce") / 1000.0
    elif "STOCapacityGWh" not in out.columns:
        out["STOCapacityGWh"] = pd.NA

    for col in SDEWES18_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA

    return out[SDEWES18_COLUMNS].copy()


def combine_built_genco(
    built_dir: Path,
    out_csv: Path,
    countries: Sequence[str] | None,
    include_country_name_files: bool,
    keep_source_file: bool,
    output_format: str,
) -> pd.DataFrame:
    files = discover_built_files(built_dir, countries, include_country_name_files)
    frames = [read_genco_csv(path) for path in files]
    out = pd.concat(frames, ignore_index=True)

    numeric_cols = [
        "cap_mw",
        "decom_start_existing_cap",
        "life_time",
        "decom_start_new",
        "final_life_cap",
        "efficiency",
        "cost_no_fuel",
        "RampingCost",
        "CO2Intensity",
        "RampUpRate",
        "RampDownRate",
        "STOCapacity",
        "STOSelfDischarge",
        "STOMaxChargingPower",
        "STOChargingEfficiency",
        "CHPPowerToHeat",
        "CHPPowerLossFactor",
        "CHPMaxHeat",
        "lat",
        "lon",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out[out["fuel_type"].astype(str).str.strip().str.lower().ne("battery")].copy()
    out = out[out["technology"].astype(str).str.strip().str.lower().ne("battery")].copy()
    out = make_unit_names_unique(out)

    out = out.sort_values(["System", "Zone", "fuel_type", "technology", "unit_name"])
    if output_format == "sdewes18":
        out = format_sdewes18(out)
    else:
        final_cols = GENCO_COLUMNS + (["source_file"] if keep_source_file else [])
        out = out[final_cols]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False, quoting=csv.QUOTE_MINIMAL)

    print(f"Combined {len(files)} built country files", flush=True)
    print(f"Wrote {len(out):,} GENCO rows to: {out_csv}", flush=True)
    return out


def clean_built_outputs(built_dir: Path, countries: Sequence[str] | None = None,
                        keep_names: set[str] | None = None) -> None:
    built_dir = built_dir.resolve()
    if built_dir == DEFAULT_EXISTING_BUILT_DIR.resolve():
        raise ValueError(f"Refusing to clean reference built directory: {built_dir}")
    if not built_dir.exists():
        return
    removed = 0
    for path in built_dir.glob("genco_*_built.csv"):
        if keep_names and path.name in keep_names:
            continue
        if countries and built_file_country(path) not in set(countries):
            continue
        path.unlink()
        removed += 1
    if removed:
        print(f"Removed {removed} stale raw built GENCO files from: {built_dir}", flush=True)


def require_path(path: Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"--{label} is required in raw mode")
    if not path.exists():
        raise FileNotFoundError(
            f"{label} not found: {path}\n"
            "Raw mode reads raw powerplants + JRC hydro and then combines them. "
            "Use the default --download-sources behavior, place the file next to the script, "
            "or pass its path explicitly."
        )
    return path


def run_raw_builder(args: argparse.Namespace) -> None:
    # The raw builder imports its spatial stack. Check it before downloading
    # sources or clearing a previously prepared country's files.
    root = SCRIPT_DIR.parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from preparation_dependencies import selected_dependencies, require_dependencies
    require_dependencies(selected_dependencies(["power"], skip_vre=True))
    if args.built_dir.resolve() == DEFAULT_EXISTING_BUILT_DIR.resolve():
        raise ValueError(f"Raw generation must not overwrite reference GENCO files: {args.built_dir}")
    builder = SCRIPT_DIR / "build_genco_union_plus_template_defaults_all.py"
    require_path(builder, "builder")
    prepare_raw_sources(args)

    powerplants = require_path(args.powerplants, "powerplants")
    jrc_hydro = require_path(args.jrc_hydro, "jrc-hydro")
    template_genco = require_path(args.template_genco, "template-genco")
    hr_defaults_xlsx = require_path(args.hr_defaults_xlsx, "hr-defaults-xlsx")
    nuts3_geojson = require_path(args.nuts3_geojson, "nuts3-geojson")

    cmd = [
        sys.executable,
        str(builder),
        "--powerplants",
        str(powerplants),
        "--jrc-hydro",
        str(jrc_hydro),
        "--template-genco",
        str(template_genco),
        "--hr-defaults-xlsx",
        str(hr_defaults_xlsx),
        "--nuts3-geojson",
        str(nuts3_geojson),
        "--out-dir",
        str(args.built_dir),
        "--zone-mode",
        args.zone_mode,
    ]

    if args.countries:
        cmd.extend(["--countries", ",".join(args.countries)])

    print("Building per-country GENCO files from raw powerplants + JRC hydro...", flush=True)
    from tempfile import TemporaryDirectory
    args.built_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.built_dir.parent, prefix="_genco_build_") as folder:
        cmd[cmd.index("--out-dir") + 1] = folder
        subprocess.run(cmd, check=True)
        # A failed build leaves prior country caches intact. A selected-country
        # refresh must also leave other countries' cached tables alone.
        args.built_dir.mkdir(parents=True, exist_ok=True)
        produced = list(Path(folder).glob("genco_*_built.csv"))
        for path in produced:
            # Replace in one operation. A locked destination retains its old
            # contents, whereas unlinking it first could lose that cache.
            path.replace(args.built_dir / path.name)
        if args.clean_built_dir:
            clean_built_outputs(args.built_dir, args.countries, keep_names={path.name for path in produced})


def print_summary(df: pd.DataFrame) -> None:
    cap_by_fuel = (
        df.groupby("fuel_type", dropna=False)["cap_mw"]
        .sum(min_count=1)
        .sort_values(ascending=False)
        .head(20)
    )
    rows_by_system = df["System"].value_counts(dropna=False).sort_index()

    print("")
    print("Rows by System:")
    print(rows_by_system.to_string())
    print("")
    print("Capacity by fuel_type (MW):")
    print(cap_by_fuel.round(3).to_string())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Generate the H2RES power-sector GENCO table from raw powerplants + JRC hydro."
    )

    ap.add_argument("--mode", choices=["raw", "built"], default="raw")
    ap.add_argument("--built-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--countries", type=parse_countries, default=None, help='Comma-separated ISO2 list, e.g. "HR,SI,IT".')
    ap.add_argument("--include-country-name-files", action="store_true")
    ap.add_argument("--keep-source-file", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--output-format", choices=["sdewes18", "detailed"], default="sdewes18")

    ap.add_argument("--rebuild-built", action="store_true", help="Deprecated alias for --mode raw.")
    ap.add_argument("--powerplants", type=Path, default=DEFAULT_POWERPLANTS)
    ap.add_argument("--jrc-hydro", type=Path, default=DEFAULT_HYDRO)
    ap.add_argument("--template-genco", type=Path, default=None)
    ap.add_argument("--hr-defaults-xlsx", type=Path, default=None)
    ap.add_argument("--nuts3-geojson", type=Path, default=DEFAULT_NUTS3)
    ap.add_argument("--zone-mode", choices=["country1", "country"], default="country1")
    ap.add_argument("--download-sources", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--refresh-sources", action="store_true")
    ap.add_argument("--clean-built-dir", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--powerplants-url", default=POWERPLANTS_URL)
    ap.add_argument("--jrc-hydro-url", default=JRC_HYDRO_URL)
    ap.add_argument("--nuts3-url", default=NUTS3_URL)

    return ap


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.rebuild_built:
        args.mode = "raw"

    if args.built_dir is None:
        args.built_dir = DEFAULT_RAW_BUILT_DIR if args.mode == "raw" else DEFAULT_EXISTING_BUILT_DIR

    try:
        if args.mode == "raw":
            run_raw_builder(args)
        else:
            print("Combining existing built GENCO files without rereading raw sources...", flush=True)

        df = combine_built_genco(
            built_dir=args.built_dir,
            out_csv=args.out,
            countries=args.countries,
            include_country_name_files=args.include_country_name_files,
            keep_source_file=args.keep_source_file,
            output_format=args.output_format,
        )
    except (FileNotFoundError, ImportError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.summary:
        print_summary(df)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
