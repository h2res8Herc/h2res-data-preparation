#!/usr/bin/env python3
"""Run the power, industry, transport and heating input pipelines together.

Default spatial resolution is NUTS3.  A single shared aggregation selection can
instead produce NUTS2, NUTS1, country-level or custom groupings of whole NUTS3
regions. Custom maps currently require complete selected-country coverage;
partial countries and independent offshore zones are not supported yet.
The sector algorithms remain in their standalone scripts; this file is the
single entry point that coordinates them and normalises their zone mappings.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from model_input_bundle import (
    DEFAULT_REFERENCE, export_bundle, export_complex_sector, import_model_inputs, reference_for,
    selected_workbook, validate_bundle, preflight_reference,
)
from scenario_config import apply_scenario, resolve_scenario
from openmeteo_quota import DEFAULT_MAX_WAIT, quota_run


SCRIPT_DIR = Path(__file__).resolve().parent
INDUSTRY_SCRIPT = SCRIPT_DIR / "industry" / "generate_industry_inputs_standalone.py"
TRANSPORT_SCRIPT = (
    SCRIPT_DIR / "transport" / "script" / "generate_transport_inputs_standalone.py"
)
HEATING_SCRIPT = SCRIPT_DIR / "heating" / "generate_heating_inputs_standalone.py"
POWER_SCRIPT = SCRIPT_DIR / "power" / "generators" / "generate_genco_power_sector.py"
POWER_AGGREGATOR = (
    SCRIPT_DIR / "power" / "generators" / "aggregate_genco_by_custom_zones_flexible_v2.py"
)
HYDRO_SCRIPT = SCRIPT_DIR / "power" / "hydro" / "generate_hydro_inputs_standalone.py"
VRE_SCRIPT = SCRIPT_DIR / "power" / "VRES_distributions" / "build_vre_capacity_weighted_cf_from_schema_openmeteo_weighted.py"
DEMAND_SCRIPT = SCRIPT_DIR / "power" / "demand" / "generate_electricity_demand_standalone.py"
NUTS_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
)
SECTORS = ("power", "industry", "transport", "heating")
ALL_COUNTRIES = (
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI",
    "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK",
)


def parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def run(command: list[object]) -> None:
    printable = [str(item) for item in command]
    print("\n>", subprocess.list2cmdline(printable), flush=True)
    subprocess.run(printable, check=True)


def download(url: str, path: Path, refresh: bool = False) -> Path:
    if path.exists() and path.stat().st_size > 0 and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    print(f"Downloading shared NUTS3 boundaries -> {path}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "h2res-all-inputs/1.0"})
    try:
        with urllib.request.urlopen(request) as response, partial.open("wb") as target:
            while block := response.read(1024 * 1024):
                target.write(block)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def read_custom_map(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    aliases = {
        "System": "country", "system": "country", "country": "country",
        "CNTR_CODE": "country",
        "nuts3": "nuts3", "nuts3_id": "nuts3", "NUTS3": "nuts3",
        "NUTS_ID": "nuts3", "zone_old": "nuts3",
        "zone": "zone", "zone_new": "zone",
        "system_new": "system_new", "System_new": "system_new",
        "macroregion": "system_new", "Macroregion": "system_new",
    }
    frame = frame.rename(columns={col: aliases[col] for col in frame if col in aliases})
    if frame.columns.duplicated().any():
        raise ValueError('Zone-map columns are ambiguous after resolving aliases; use country,nuts3,zone once each.')
    required = {"country", "nuts3", "zone"}
    if not required.issubset(frame.columns):
        raise ValueError(
            "Shared zone map needs country, nuts3 and zone columns "
            "(System/zone_old/zone_new aliases are also accepted)."
        )
    columns = ["country", "nuts3", "zone"]
    if "system_new" in frame.columns:
        columns.append("system_new")
    result = frame[columns].copy()
    if result.isna().any().any():
        raise ValueError('Custom zone-map fields cannot be blank. Independent offshore zones without a NUTS3 region are not supported yet. See docs/CUSTOM_ZONES.html.')
    for col in columns:
        result[col] = result[col].astype(str).str.strip()
    result["country"] = result["country"].str.upper()
    result['nuts3'] = result['nuts3'].str.upper()
    if result.empty or result.eq('').any().any():
        raise ValueError('Custom zone maps require nonempty country,nuts3,zone values; see docs/CUSTOM_ZONES.html.')
    result=result.drop_duplicates()
    duplicate = result.duplicated(["country", "nuts3"], keep=False)
    if duplicate.any():
        raise ValueError("The zone map assigns at least one NUTS3 region more than once.")
    return result


def validate_custom_map(mapping: pd.DataFrame, nuts_geojson: Path, countries: list[str]) -> None:
    """Reject unsupported partial maps before they can leak or redistribute data."""
    properties=[f['properties'] for f in json.loads(nuts_geojson.read_text(encoding='utf-8'))['features']]
    known={(str(p.get('CNTR_CODE','')).upper(),str(p.get('NUTS_ID','')).upper()) for p in properties}
    selected=mapping.loc[mapping.country.isin(countries)]
    present=set(selected[['country','nuts3']].itertuples(index=False,name=None))
    invalid=present-known
    if invalid:
        raise ValueError(f'Custom map has unknown country/NUTS3 pairs in the selected boundary vintage: {sorted(invalid)[:8]}. Offshore zones must not use invented NUTS3 IDs.')
    missing_countries=set(countries)-set(selected.country)
    if missing_countries:
        raise ValueError(f'Custom map has no rows for selected countries: {sorted(missing_countries)}')
    omitted={pair for pair in known if pair[0] in countries}-present
    if omitted:
        counts={c:sum(pair[0]==c for pair in omitted) for c in sorted({p[0] for p in omitted})}
        raise ValueError(f'Partial-country custom maps are not supported yet: omitted NUTS3 counts {counts}. Every selected country currently needs full coverage. See docs/CUSTOM_ZONES.html; adding an IT_REST zone models it rather than excluding it.')
    system='system_new' if 'system_new' in selected else 'country'
    conflicts=selected.groupby('zone')[system].nunique()
    if conflicts.gt(1).any():
        raise ValueError(f'Zone names must be unique across model systems: {conflicts[conflicts.gt(1)].index.tolist()}. Prefix them with the country code.')


def hierarchical_map(
    nuts_geojson: Path, countries: list[str], spatial_level: str
) -> pd.DataFrame:
    data = json.loads(nuts_geojson.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    lengths = {"nuts3": 5, "nuts2": 4, "nuts1": 3}
    requested = set(countries)
    for feature in data["features"]:
        props = feature.get("properties", {})
        nuts3 = str(props.get("NUTS_ID", "")).strip()
        country = str(props.get("CNTR_CODE", nuts3[:2])).strip().upper()
        if country not in requested or not nuts3:
            continue
        zone = country + "1" if spatial_level == "country" else nuts3[:lengths[spatial_level]]
        rows.append({"country": country, "nuts3": nuts3, "zone": zone})
    result = pd.DataFrame(rows).drop_duplicates()
    missing = requested - set(result.get("country", pd.Series(dtype=str)))
    if missing:
        raise ValueError(f"Countries absent from NUTS 2021 boundaries: {sorted(missing)}")
    return result


def write_sector_maps(mapping: pd.DataFrame, map_dir: Path) -> dict[str, Path]:
    map_dir.mkdir(parents=True, exist_ok=True)
    common = map_dir / "zone_map_common.csv"
    heating = map_dir / "zone_map_heating.csv"
    transport = map_dir / "zone_map_transport.csv"
    power = map_dir / "zone_map_power.csv"
    mapping.to_csv(common, index=False)
    mapping.rename(columns={"nuts3": "nuts3_id"}).to_csv(heating, index=False)
    mapping.to_csv(transport, index=False)
    mapping.rename(
        columns={"country": "System", "nuts3": "zone_old", "zone": "zone_new"}
    ).to_csv(power, index=False)
    return {
        "common": common, "heating": heating,
        "transport": transport, "power": power,
    }


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(0)
    valid = values.notna()
    if not valid.any():
        return np.nan
    total = weights[valid].sum()
    return float((values[valid] * weights[valid]).sum() / total) if total else float(
        values[valid].mean()
    )


def aggregate_industry_country(country_dir: Path, mapping: pd.DataFrame) -> None:
    final_dir = country_dir / "03_non_energy"
    units_path = final_dir / "industry_units_by_category_ALL_NON_ENERGY.csv"
    hourly_path = final_dir / "industry_hourly_distributions_by_category_ALL_NON_ENERGY.csv"
    units = pd.read_csv(units_path)
    hourly = pd.read_csv(hourly_path)
    local_map = mapping.rename(columns={"country": "System"})

    def attach(frame: pd.DataFrame) -> pd.DataFrame:
        merged = frame.merge(
            local_map, left_on=["System", "zone"], right_on=["System", "nuts3"],
            how="left", validate="many_to_one",
        )
        missing = merged["zone_y"].isna()
        if missing.any():
            bad = merged.loc[missing, ["System", "zone_x"]].drop_duplicates()
            raise ValueError(f"Unmapped industry zones:\n{bad.to_string(index=False)}")
        return merged.drop(columns=["nuts3", "zone_x"]).rename(columns={"zone_y": "zone"})

    units = attach(units)
    keys = ["System", "zone", "unit_name", "fuel_type", "Industry"]
    sum_cols = [
        col for col in (
            "cap_mw", "max_cap", "CC_cap", "CC_el_dem", "Reboiler_cap",
            "Tank_stor_cap", "CC_strip_heat_dem", "CC_strip_el_dem",
        ) if col in units
    ]
    numeric = set(units.select_dtypes(include="number").columns)
    rows: list[dict[str, object]] = []
    for key, group in units.groupby(keys, dropna=False, sort=False):
        row = dict(zip(keys, key))
        weights = pd.to_numeric(group.get("cap_mw", 0), errors="coerce").fillna(0)
        for col in units.columns:
            if col in keys:
                continue
            if col in sum_cols:
                row[col] = pd.to_numeric(group[col], errors="coerce").sum(min_count=1)
            elif col == "max_share_fuel":
                row[col] = pd.to_numeric(group[col], errors="coerce").max()
            elif col in numeric:
                row[col] = weighted_mean(group[col], weights)
            else:
                nonempty = group[col].dropna().astype(str)
                row[col] = nonempty.iloc[0] if len(nonempty) else pd.NA
        rows.append(row)
    aggregated = pd.DataFrame(rows, columns=units.columns)
    share_keys = ["System", "zone", "Industry"]
    total = aggregated.groupby(share_keys)["cap_mw"].transform("sum")
    aggregated["share_fuel_2020"] = np.where(
        total > 0, aggregated["cap_mw"] / total, 0.0
    )
    aggregated.to_csv(units_path, index=False)

    hourly = attach(hourly)
    value_cols = [col for col in hourly.columns if col not in {"period", "System", "zone"}]
    for col in value_cols:
        hourly[col] = pd.to_numeric(hourly[col], errors="coerce").fillna(0)
    hourly = hourly.groupby(["period", "System", "zone"], as_index=False)[value_cols].sum()
    hourly.to_csv(hourly_path, index=False)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_industry(args: argparse.Namespace, maps: dict[str, Path] | None) -> None:
    if args.industry_mode == "complex":
        if getattr(args, "all_model_variants", False) and args.model_export:
            from copy import copy
            common = copy(args)
            common.industry_mode = "categories"
            print("Preparing common regular/category observations; process variants are compiled during native export.", flush=True)
            run_industry(common, maps)
            return
        if not (args.model_reference / "manifest.json").exists():
            reference_for(args)
        export_complex_sector(args, pd.read_csv(args.out_root / "_zone_maps" / "zone_map_common.csv"))
        return
    out = args.out_root / "industry"
    command: list[object] = [
        sys.executable, INDUSTRY_SCRIPT, "--countries", ",".join(args.countries),
        "--nuts-level", "3", "--out-root", out,
        "--data-dir", args.data_root / "industry",
        "--nuts3", args.nuts3,
        "--year", str(args.industry_base_year),
        "--regional-allocation", getattr(args, "industry_regional_allocation", "require-weights"),
        "--download-sources" if args.industry_download else "--no-download-sources",
        "--efuels" if args.efuels else "--no-efuels",
    ]
    if args.refresh_sources:
        command.append("--refresh-sources")
    if args.industry_mode == "categories":
        command.append("--keep-heat-categories")
    run(command)
    if maps is None:
        return
    mapping = pd.read_csv(maps["common"])
    for country in args.countries:
        aggregate_industry_country(out / country, mapping)
    module = load_module("industry_standalone_for_combination", INDUSTRY_SCRIPT)
    final_dirs = [out / country / "03_non_energy" for country in args.countries]
    for final_dir in final_dirs:
        module.write_industry_variants(
            final_dir / module.UNITS_FILE, final_dir, args.efuels, args.industry_mode == "categories"
        )
        module.write_demand_views(final_dir / module.DIST_FILE, final_dir)
        module.validate_outputs(final_dir)
    module.combine_countries(final_dirs, out / "combined")


def run_transport(args: argparse.Namespace, maps: dict[str, Path] | None) -> None:
    command: list[object] = [
        sys.executable, TRANSPORT_SCRIPT, "--countries", ",".join(args.countries),
        "--out-root", args.out_root / "transport",
        "--data-dir", args.data_root / "transport",
        "--nuts3", args.nuts3,
    ]
    if maps:
        command.extend(["--zone-map", maps["transport"]])
    if args.efuels:
        command.append("--efuels")
    if args.refresh_sources:
        command.append("--refresh-sources")
    run(command)


def run_heating(args: argparse.Namespace, maps: dict[str, Path] | None) -> None:
    command: list[object] = [
        sys.executable, HEATING_SCRIPT, "--countries", ",".join(args.countries),
        "--out-root", args.out_root / "heating",
        "--data-dir", args.data_root / "heating",
        "--raw-output-root", args.data_root / "heating_raw",
        "--nuts3-geojson", args.nuts3,
        "--temperature-source", args.temperature_source,
        "--efuels" if args.efuels else "--no-efuels",
    ]
    shared_idees = args.data_root / "industry" / "JRC-IDEES-2021"
    if shared_idees.exists():
        command.extend(["--idees-root", shared_idees])
    if maps:
        command.extend(["--zone-map", maps["heating"]])
    if args.era5:
        command.extend(["--era5", args.era5])
    if args.population_tif:
        command.extend(["--population-tif", args.population_tif])
    if args.accept_population_terms:
        command.append("--accept-population-terms")
    if args.skip_heating_raw:
        command.extend(["--skip-raw-generation", "--input-root", args.heating_input_root])
    if args.refresh_sources:
        command.append("--refresh-sources")
    run(command)


def run_power(args: argparse.Namespace, maps: dict[str, Path]) -> None:
    out = args.out_root / "power"
    detailed = out / "_genco_nuts3_detailed.csv"
    aggregated = out / "_genco_spatial_detailed.csv"
    individual = out / "_genco_spatial_individual.csv"
    aggregation_schema = out / "_genco_aggregation_schema.csv"
    identity_schema = out / "_genco_individual_schema.csv"
    final = out / "GENCO.csv"
    command: list[object] = [
        sys.executable, POWER_SCRIPT, "--mode", "raw",
        "--countries", ",".join(args.countries),
        "--out", detailed, "--output-format", "detailed",
        "--nuts3-geojson", args.nuts3,
    ]
    if args.refresh_sources:
        command.append("--refresh-sources")
    run(command)
    power_map = pd.read_csv(maps["power"])
    targets_per_system = (
        power_map[["System", "zone_new"]]
        .drop_duplicates()
        .groupby("System")
        .size()
    )
    if targets_per_system.le(1).all():
        print(
            "Skipping NUTS3 border repair: every selected country has one custom target zone.",
            flush=True,
        )
    else:
        repair_power_nuts_assignments(detailed, args.nuts3)
    run([
        sys.executable, POWER_AGGREGATOR,
        "--in", detailed, "--zone-map", maps["power"], "--out", aggregated,
        "--schema-out", aggregation_schema,
        "--map-from", "NUTS3", "--policy", "DEFAULT=aggregate:1",
    ])
    run([
        sys.executable, POWER_AGGREGATOR,
        "--in", detailed, "--zone-map", maps["power"], "--out", individual,
        "--schema-out", identity_schema,
        "--map-from", "NUTS3", "--policy", "DEFAULT=keep",
    ])
    # The aggregator emits schema rows only for aggregated units.  Reuse its
    # complete zonal mapping and turn it into an identity mapping for profiles
    # that must retain one column per physical plant.
    identity_frame = pd.read_csv(aggregation_schema)
    identity_frame["new_unit_name"] = identity_frame["old_unit_name"]
    identity_frame.to_csv(identity_schema, index=False)
    module = load_module("power_genco_for_combination", POWER_SCRIPT)
    aggregated_frame = pd.read_csv(aggregated)
    individual_frame = pd.read_csv(individual)
    formatted_aggregated = module.format_sdewes18(aggregated_frame)
    formatted_individual = module.format_sdewes18(individual_frame)
    formatted = (
        formatted_individual
        if args.power_output_level == "individual"
        else formatted_aggregated
    )
    final.parent.mkdir(parents=True, exist_ok=True)
    formatted.to_csv(final, index=False)
    if args.power_output_level == "both":
        formatted_aggregated.to_csv(out / "GENCO_aggregated.csv", index=False)
        formatted_individual.to_csv(out / "GENCO_individual.csv", index=False)
    with pd.ExcelWriter(out / "power_inputs.xlsx", engine="openpyxl") as writer:
        formatted.to_excel(writer, sheet_name="GENCO", index=False)
        if args.power_output_level == "both":
            formatted_individual.to_excel(writer, sheet_name="GENCO_individual", index=False)
    print(f"Wrote model-ready power inputs: {final}", flush=True)

    if not args.skip_vre_profiles:
        levels = (
            ("aggregated", aggregation_schema)
            if args.power_output_level == "aggregated"
            else ("individual", identity_schema)
        )
        level_jobs = [levels] if args.power_output_level != "both" else [
            ("aggregated", aggregation_schema), ("individual", identity_schema)
        ]
        for level, vre_schema in level_jobs:
            country_files = []
            for country in args.countries:
                vre_command: list[object] = [
                    sys.executable, VRE_SCRIPT,
                    "--schema", vre_schema,
                    "--out-dir", out / "vre" / level,
                    "--country", country,
                    "--date-from", f"{args.vre_year}-01-01",
                    "--date-to", f"{args.vre_year}-12-31",
                    "--timezone", "UTC",
                    "--cache-dir", args.data_root / "vre_weather_cache",
                    "--weather-source", args.vre_weather_source,
                    "--ninja-dataset", args.renewables_ninja_dataset,
                    "--openmeteo-max-wait", args.openmeteo_max_wait,
                ]
                if args.vre_calibrate:
                    if not args.irena_xlsx or not args.irena_xlsx.exists():
                        raise FileNotFoundError(
                            "VRE calibration requested but IRENA workbook is missing: "
                            f"{args.irena_xlsx}"
                        )
                    vre_command.extend([
                        "--calibrate", "--irena-xlsx", args.irena_xlsx,
                        "--irena-year", args.vre_irena_year or args.vre_year,
                    ])
                run(vre_command)
                path = out / "vre" / level / f"vre_cf_{country}_{args.vre_year}.csv"
                if path.exists():
                    country_files.append(path)
            if country_files:
                combined = None
                for path in country_files:
                    frame = pd.read_csv(path)
                    combined = frame if combined is None else combined.merge(
                        frame, on="time", how="outer", validate="one_to_one"
                    )
                combined.sort_values("time").to_csv(
                    out / "vre" / level / f"AvailabilityFactors_VRE_{args.vre_year}.csv",
                    index=False,
                )

    if not args.skip_hydro_profiles:
        hydro_profiles = args.hydro_profiles
        hydro_units = args.hydro_units
        hydro_plants = args.hydro_plants
        hydro_output_level = (
            args.power_output_level
            if args.hydro_output_level == "match-power"
            else args.hydro_output_level
        )
        hydro_genco = individual if args.power_output_level == "individual" else aggregated
        hydro_schema = identity_schema if args.power_output_level == "individual" else aggregation_schema
        command = [
            sys.executable, HYDRO_SCRIPT,
            "--year", args.hydro_year,
            "--countries", ",".join(args.countries),
            "--detailed-genco", detailed,
            "--aggregated-genco", hydro_genco,
            "--aggregation-schema", hydro_schema,
            "--profiles", hydro_profiles,
            "--hydro-units", hydro_units,
            "--plants", hydro_plants,
            "--outdir", out / "hydro",
            "--output-level", hydro_output_level,
        ]
        run(command)

    if not args.skip_electricity_demand:
        demand_command: list[object] = [
            sys.executable, DEMAND_SCRIPT,
            "--countries", ",".join(args.countries),
            "--year", args.electricity_demand_year,
            "--out-dir", out / "demand",
            "--cache-dir", args.data_root / "entsoe_load",
            "--zone-map", maps["common"],
        ]
        if args.refresh_sources:
            demand_command.append("--refresh")
        run(demand_command)


def repair_power_nuts_assignments(detailed_path: Path, nuts_geojson: Path) -> None:
    """Repair border/source-coordinate assignments that land in another country."""
    import geopandas as gpd
    from shapely.geometry import Point

    frame = pd.read_csv(detailed_path)
    nuts = gpd.read_file(nuts_geojson)
    nuts["NUTS_ID"] = nuts["NUTS_ID"].astype(str)
    nuts["country"] = nuts["NUTS_ID"].str[:2]
    valid_by_country = {
        country: set(group["NUTS_ID"]) for country, group in nuts.groupby("country")
    }
    repaired = 0
    nuts_metric = nuts.to_crs("EPSG:3035")
    for idx, row in frame.iterrows():
        country = str(row.get("System", "")).strip().upper()
        current = str(row.get("NUTS3", "")).strip()
        boundary_country = "EL" if country == "GR" else country
        # BA and XK do not have official NUTS geometries in the bundled
        # Eurostat file. Keep the source assignments used by their packaged
        # power data; the custom map explicitly supplies those codes.
        if boundary_country not in valid_by_country:
            continue
        if current in valid_by_country.get(boundary_country, set()):
            continue
        lat = pd.to_numeric(pd.Series([row.get("lat")]), errors="coerce").iloc[0]
        lon = pd.to_numeric(pd.Series([row.get("lon")]), errors="coerce").iloc[0]
        candidates = nuts_metric[nuts_metric["country"].eq(boundary_country)]
        if pd.isna(lat) or pd.isna(lon) or candidates.empty:
            raise ValueError(
                f"Cannot repair power NUTS3 assignment for {row.get('unit_name')} "
                f"({country}, current={current})."
            )
        point = gpd.GeoSeries([Point(float(lon), float(lat))], crs="EPSG:4326").to_crs(
            "EPSG:3035"
        ).iloc[0]
        nearest_idx = candidates.geometry.distance(point).idxmin()
        replacement = str(candidates.loc[nearest_idx, "NUTS_ID"])
        print(
            f"Repairing cross-border power assignment: {row.get('unit_name')} "
            f"{current or '<missing>'} -> {replacement}",
            flush=True,
        )
        frame.at[idx, "NUTS3"] = replacement
        repaired += 1
    if repaired:
        frame.to_csv(detailed_path, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate power, industry, transport and heating inputs at NUTS3 "
            "or a shared aggregated spatial level."
        )
    )
    parser.add_argument("--countries", type=parse_csv, default=["HR"])
    parser.add_argument(
        "--sectors", type=parse_csv, default=list(SECTORS),
        help="Comma-separated subset of power,industry,transport,heating.",
    )
    parser.add_argument(
        "--spatial-level",
        choices=["nuts3", "nuts2", "nuts1", "country", "custom"],
        default="nuts3",
    )
    parser.add_argument(
        "--zone-map", type=Path,
        help="Required with --spatial-level custom; full-country country,nuts3,zone mapping. Examples: docs/CUSTOM_ZONES.html.",
    )
    parser.add_argument("--out-root", type=Path, default=SCRIPT_DIR / "outputs_all")
    parser.add_argument("--data-root", type=Path, default=SCRIPT_DIR / "data_all")
    parser.add_argument("--nuts3", type=Path)
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--efuels", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--industry-mode", choices=("regular", "categories", "complex"), default="categories",
                        help="Categories and complex industry are mutually exclusive model modes.")
    parser.add_argument("--industry-electricity-case", choices=("conservative", "technical_2050"), default="conservative")
    parser.add_argument("--industry-source-root", type=Path, help="Directory containing country JRC-IDEES-2023 Industry and both balance workbooks; otherwise use cache/public downloads")
    parser.add_argument("--industry-download", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--industry-base-year", type=int, default=2020)
    parser.add_argument("--industry-waste-allocation", choices=("strict", "sector-blend"), default="sector-blend",
                        help="Use exact single-class waste evidence, or an explicitly recorded sector-blend assumption where needed")
    parser.add_argument("--industry-zone-weights", type=Path, help="Complex industry regional allocation: country,zone,Industry,weight; '*' means every sector")
    parser.add_argument("--industry-regional-allocation", choices=("require-weights", "equal"), default="require-weights",
                        help="National JRC data need explicit weights at regional resolution; equal is an explicit proxy")
    parser.add_argument("--complex-industry-sectors", default="all", help="Complex sector selection: all or comma-separated native Industry labels")
    parser.add_argument("--model-root", type=Path,
                        help="Snapshot the live data from this model directory into the portable reference.")
    parser.add_argument("--model-reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--model-export", action=argparse.BooleanOptionalAction, default=True,
                        help="Export canonical data files and the selected current model workbook.")
    parser.add_argument("--refactored-export", action="store_true",
                        help="Also export data_refactored and H2RES_refactored_inputs.zip using the bus-based CSV contract.")
    parser.add_argument("--refactored-model-root", type=Path,
                        help="Optional refactored installation for actual-reader checks; separate from legacy --model-root.")
    parser.add_argument("--model-ready-package", action=argparse.BooleanOptionalAction, default=None,
                        help="Also write h2res_inputs and H2RES_model_inputs.zip with the selected flex_tech workbook and distributions.")
    parser.add_argument("--all-model-variants", action=argparse.BooleanOptionalAction, default=True,
                        help="Populate every native flex_tech/industry companion variant for the selected countries and write the ready-to-use data folder.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--export-only", action="store_true", help="Package existing sector outputs without downloading or regenerating sources.")
    actions.add_argument("--import-model-inputs", action="store_true",
                         help="Copy the supplied model's complete baseline inputs, preserving its original geography.")
    parser.add_argument("--require-model-ready", action="store_true",
                        help="Return an error if generated curves or model zone coverage are incomplete.")
    parser.add_argument("--scenario-preset", choices=("reference", "res100"),
                        help="Keep reference assumptions or target 100%% renewable energy.")
    parser.add_argument("--scenario-scope", choices=("all-energy", "electricity"))
    parser.add_argument("--scenario-config", type=Path, help="JSON scenario assumptions and investment overrides.")
    parser.add_argument("--planning-years", help="Comma-separated equally spaced decision years.")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--year-step", type=int)
    parser.add_argument("--renewable-target-year", type=int)
    parser.add_argument("--renewable-start-share", type=float, help="Starting electricity renewable-share assumption, from 0 to 1.")
    parser.add_argument("--investment-multiplier", type=float, help="Scale reference annual build limits; installed-capacity ceilings stay unchanged.")
    parser.add_argument("--era5", type=Path)
    parser.add_argument(
        "--temperature-source", choices=["open-meteo", "cds-netcdf"],
        default="open-meteo",
    )
    parser.add_argument("--population-tif", type=Path)
    parser.add_argument("--accept-population-terms", action="store_true")
    parser.add_argument("--skip-heating-raw", action="store_true")
    parser.add_argument("--heating-input-root", type=Path, default=SCRIPT_DIR / "heating")
    packaged_hydro = SCRIPT_DIR / "power" / "hydro" / "precomputed"
    bulk_hydro = SCRIPT_DIR / "power" / "hydro_bulk_europe"
    parser.add_argument("--hydro-year", type=int, default=2020)
    parser.add_argument(
        "--hydro-profiles", type=Path,
        default=(
            packaged_hydro / "runoff_shapes_2020.npz"
            if (packaged_hydro / "runoff_shapes_2020.npz").exists()
            else bulk_hydro / "outputs/profiles/runoff_shapes_2020.npz"
        ),
    )
    parser.add_argument(
        "--hydro-units", type=Path,
        default=(
            packaged_hydro / "hydro_units.csv"
            if (packaged_hydro / "hydro_units.csv").exists()
            else bulk_hydro / "outputs/dispaset/hydro_units.csv"
        ),
    )
    parser.add_argument(
        "--hydro-plants", type=Path,
        default=(
            packaged_hydro / "jrc-hydro-power-plant-database.csv"
            if (packaged_hydro / "jrc-hydro-power-plant-database.csv").exists()
            else bulk_hydro / "data/plants/jrc-hydro-power-plant-database.csv"
        ),
    )
    parser.add_argument("--skip-hydro-profiles", action="store_true")
    parser.add_argument(
        "--hydro-output-level",
        choices=("match-power", "aggregated", "individual", "both"),
        default="match-power",
        help="Hydro curve level; default follows --power-output-level.",
    )
    parser.add_argument(
        "--power-output-level",
        choices=("aggregated", "individual", "both"),
        default="aggregated",
        help="Write zonally aggregated plants, individual plants, or both.",
    )
    parser.add_argument("--skip-vre-profiles", action="store_true",
                        help="Skip wind/solar profiles for source-only or diagnostic exports. Complete H2RES exports always generate them, reusing cached weather.")
    parser.add_argument("--vre-year", type=int, default=2020)
    parser.add_argument("--vre-irena-year", type=int)
    parser.add_argument(
        "--vre-weather-source",
        choices=("openmeteo", "renewables-ninja"),
        default="openmeteo",
        help="Weather backend; Renewables.ninja reads RENEWABLES_NINJA_TOKEN.",
    )
    parser.add_argument("--renewables-ninja-dataset", default="merra2")
    parser.add_argument('--openmeteo-max-wait',type=float,default=DEFAULT_MAX_WAIT,
                        help='Maximum seconds per local-estimate pause (0: no cap); quota recovery never aborts the run')
    parser.add_argument(
        "--vre-calibrate", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--irena-xlsx", type=Path,
        default=SCRIPT_DIR / "power" / "VRES_distributions" / "IRENA_Statistics_Extract_2025H2.xlsx",
    )
    parser.add_argument("--electricity-demand-year", type=int, default=2020)
    parser.add_argument(
        "--skip-electricity-demand", action="store_true",
        help="Skip ENTSO-E national load download and EIGL NUTS3/model-zone allocation.",
    )
    return parser


def export_refactored_if_requested(args):
    if args.refactored_export:
        from refactored_input_export import export_refactored_bundle
        export_refactored_bundle(args.out_root / 'model_inputs', args.out_root,
            model_root=args.refactored_model_root, efuels=args.efuels, industry_mode=args.industry_mode,
            electricity_case=args.industry_electricity_case)


@quota_run(inherit=False)
def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if not np.isfinite(args.openmeteo_max_wait) or args.openmeteo_max_wait < 0:
            raise ValueError('--openmeteo-max-wait must be a finite nonnegative number of seconds')
        args.scenario = resolve_scenario(args)
        if args.refactored_export and not (args.model_export or args.export_only or args.import_model_inputs):
            raise ValueError("--refactored-export requires the native model export used as its prepared source")
        if args.refactored_model_root and not args.refactored_export:
            raise ValueError("--refactored-model-root requires --refactored-export")
        if args.refactored_export and args.scenario and args.scenario.get('preset')=='res100' and args.scenario.get('scope')=='all-energy':
            raise ValueError('Refactored export cannot enforce the legacy whole-energy RES preset with a prescribed baseline fleet; select reference or electricity scope')
        if args.model_ready_package is None:
            args.model_ready_package = bool(args.model_export or args.import_model_inputs or args.export_only)
        if args.model_ready_package:
            args.require_model_ready = True
        if args.model_ready_package and not (args.model_export or args.import_model_inputs or args.export_only):
            raise ValueError("--model-ready-package requires a model-data export")
        if args.scenario and not (args.model_export or args.import_model_inputs or args.export_only):
            raise ValueError("Scenario settings require a model-data export")
        args.countries = [country.upper() for country in args.countries]
        if (
            args.spatial_level == "custom"
            and args.zone_map is not None
            and any(country in {"ALL", "EU", "EU27", "EUROPE"} for country in args.countries)
        ):
            custom_selection = read_custom_map(args.zone_map)
            args.countries = list(dict.fromkeys(custom_selection["country"].tolist()))
            print(
                f"Expanded country selection to all {len(args.countries)} countries in the custom map.",
                flush=True,
            )
        elif any(country in {"ALL", "EU", "EU27", "EUROPE"} for country in args.countries):
            args.countries = list(ALL_COUNTRIES)
            print(f"Expanded country selection to all {len(args.countries)} supported countries.", flush=True)
        if args.spatial_level=='custom':
            if args.zone_map is None:raise ValueError('--zone-map is required with --spatial-level custom')
            custom_selection=read_custom_map(args.zone_map)
            boundary=args.nuts3 or SCRIPT_DIR/'power/data/NUTS_RG_20M_2021_4326_LEVL_3.geojson'
            if boundary.is_file():validate_custom_map(custom_selection,boundary,args.countries)
        args.sectors = [sector.lower() for sector in args.sectors]
        unknown = set(args.sectors) - set(SECTORS)
        if unknown:
            raise ValueError(f"Unknown sectors: {sorted(unknown)}")
        from preparation_options import vre_profiles_required
        if args.skip_vre_profiles and vre_profiles_required(
            args.sectors, model_export=args.model_export,
            model_ready_package=args.model_ready_package,
            require_model_ready=args.require_model_ready,
            existing_only=args.export_only or args.import_model_inputs,
        ):
            print("Complete H2RES inputs require wind/solar profiles; enabling their generation "
                  "despite --skip-vre-profiles. Cached weather will be reused.", flush=True)
            args.skip_vre_profiles = False
        if args.spatial_level == "custom" and args.zone_map is None:
            raise ValueError("--zone-map is required with --spatial-level custom")
        from preparation_dependencies import require_for_args
        require_for_args(args)
        from preparation_assets import validate_assets_for_args
        validate_assets_for_args(args)
        args.out_root = args.out_root.resolve()
        args.data_root = args.data_root.resolve()
        args.out_root.mkdir(parents=True, exist_ok=True)
        args.data_root.mkdir(parents=True, exist_ok=True)
        reference = reference_for(args) if args.model_export or args.import_model_inputs or args.export_only else None
        if reference is not None and not args.export_only:
            preflight_reference(args, reference)
        if args.import_model_inputs:
            output = import_model_inputs(reference, args.out_root)
            scenario = apply_scenario(output, selected_workbook(args.efuels, args.industry_mode, args.industry_electricity_case),
                                      args.scenario, efuels=args.efuels, industry_mode=args.industry_mode,
                                      electricity_case=args.industry_electricity_case)
            if scenario:
                manifest_path = output / "bundle_manifest.json"
                metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
                metadata["scenario"] = scenario
                manifest_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            report = validate_bundle(output, selected_workbook(args.efuels, args.industry_mode, args.industry_electricity_case),
                                     args.efuels, args.industry_mode, args.industry_electricity_case)
            (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Imported current model inputs: {output / 'data'}; ready={report['ready']}", flush=True)
            if args.require_model_ready and not report["ready"]:
                raise ValueError("Imported input coverage failed; see model_inputs/validation.json")
            if args.model_ready_package:
                from model_ready_package import build_package
                package = build_package(output, report)
                print(f"H2RES input files: {output / package['folder']}\nH2RES input ZIP: {output / package['archive']}; ready={package['ready']}", flush=True)
            export_refactored_if_requested(args)
            return 0
        if args.export_only:
            export_bundle(args, reference)
            export_refactored_if_requested(args)
            return 0
        if args.population_tif is None:
            for candidate in (
                SCRIPT_DIR / "data" / "ESTAT_OBS-VALUE-T_2021_V2.tiff",
                SCRIPT_DIR / "ESTAT_OBS-VALUE-T_2021_V2.tiff",
                args.data_root / "heating" / "ESTAT_OBS-VALUE-T_2021_V2.tiff",
            ):
                if candidate.exists():
                    args.population_tif = candidate
                    print(f"Using packaged population grid: {candidate}", flush=True)
                    break
        packaged_nuts3 = SCRIPT_DIR / "power" / "data" / "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
        args.nuts3 = args.nuts3 or (
            packaged_nuts3
            if packaged_nuts3.exists() and not args.refresh_sources
            else download(
                NUTS_URL, args.data_root / "NUTS_RG_20M_2021_4326_LEVL_3.geojson",
                args.refresh_sources,
            )
        )
        mapping = (
            read_custom_map(args.zone_map)
            if args.spatial_level == "custom"
            else hierarchical_map(args.nuts3, args.countries, args.spatial_level)
        )
        if args.spatial_level=='custom':validate_custom_map(mapping,args.nuts3,args.countries)
        maps = write_sector_maps(mapping, args.out_root / "_zone_maps")
        post_maps = None if args.spatial_level == "nuts3" else maps

        if "power" in args.sectors:
            run_power(args, maps)
        if "industry" in args.sectors:
            run_industry(args, post_maps)
        if "transport" in args.sectors:
            run_transport(args, post_maps)
        if "heating" in args.sectors:
            run_heating(args, post_maps)
        if args.model_export:
            export_bundle(args, reference)
            export_refactored_if_requested(args)
        print(f"\nAll requested sector outputs are under: {args.out_root}", flush=True)
        return 0
    except (
        OSError, ImportError, KeyError, ValueError, MemoryError,
        subprocess.CalledProcessError, urllib.error.URLError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
