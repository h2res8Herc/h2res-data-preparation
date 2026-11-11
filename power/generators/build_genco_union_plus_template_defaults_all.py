#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 12 12:05:49 2026

@author: lukah
"""

r"""
Continue from build_genco_union_powerplants_jrc_hydro_all.py:

1) Build per-country table:
   - Hydro storage file: keep ALL rows
   - Powerplants file: keep ALL rows EXCEPT hydro plants (Fueltype == 'Hydro')

2) KEEP ALL original columns from both sources (no deletion).

3) ADD any missing columns from a GENCO template CSV.

4) Populate the GENCO columns (unit_name..Zone) by importing from source columns
   (like done in the modified HR Excel).

5) Learn defaults from a user-modified HR file (xlsx):
   - Reprocessed columns are the GENCO columns: unit_name..Zone (+ optionally lat/lon)
   - Compute defaults per (fuel_type, technology) for numeric columns (median) and CHPType (mode)
   - Apply defaults to fill missing GENCO fields in all countries:
       (fuel,tech) -> fuel -> global

6) Normalize fuel_type and technology to GENCO coding:
   - Technology e.g. "Steam Turbine" -> "STUR"
   - Fuel e.g. "Hard Coal" -> "Coal"

IMPORTANT FIX:
- For HYDRO, STOCapacity must come from E_MWh (preferred), else E_GWh*1000, else storage_capacity_MWh.

FINAL REQUIREMENTS:
- unit_name: no spaces (spaces -> '_'), collapse separators
- Delete all columns BEFORE unit_name in the output (unit_name becomes first column)
- BUT keep lat/lon columns (ensure they exist and are populated if possible)
- Create new column NUTS3 by spatially joining (lon,lat) to NUTS level-3 polygons from a GeoJSON.
"""

import argparse
import sys
from pathlib import Path
import re
import numpy as np
import pandas as pd

import geopandas as gpd
from shapely.geometry import Point
PROJECT_ROOT=Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:sys.path.insert(0,str(PROJECT_ROOT))
from power_asset_inventory import partition_generator_assets, write_asset_inventory

# -----------------------------
# Normalization mappings
# -----------------------------
FUEL_MAP = {
    "hard coal": "Coal",
    "lignite": "Coal",
    "coal": "Coal",
    "natural gas": "Gas",
    "gas": "Gas",
    "oil": "Oil",
    "biomass": "Biomass",
    "waste": "Waste",
    "nuclear": "Nuclear",
    "wind": "Wind",
    "solar": "Solar",
    "hydro": "Hydro",
    # keep unknowns as-is (title-cased)
}

TECH_MAP = {
    "steam turbine": "STUR",
    "sturb": "STUR",
    "st": "STUR",
    "ccgt": "COMC",
    "combined cycle": "COMC",
    "ocgt": "GTUR",
    "gas turbine": "GTUR",
    "engine": "ICEN",
    "pv": "PHOT",
    "photovoltaic": "PHOT",
    "onshore": "WTON",
    "offshore": "WTOF",
    "run-of-river": "HROR",
    "run of river": "HROR",
    "reservoir": "HDAM",
    "pumped storage": "HPHS",
    # keep already-coded GENCO techs:
    "st ur": "STUR",
    "wton": "WTON",
    "phot": "PHOT",
    "icen": "ICEN",
    "comc": "COMC",
    "gtur": "GTUR",
    "hdam": "HDAM",
    "hror": "HROR",
    "hphs": "HPHS",
    "hdaz": "HDAZ",
}

GENCO_KEY_COLS = ["unit_name", "cap_mw", "fuel_type", "technology", "System", "Zone"]

DEFAULTABLE_COLS = [
    "decom_start_existing_cap", "life_time", "decom_start_new", "final_life_cap",
    "efficiency", "cost_no_fuel", "RampingCost", "CO2Intensity",
    "RampUpRate", "RampDownRate", "CHPType",
    "STOCapacity", "STOSelfDischarge", "STOMaxChargingPower", "STOChargingEfficiency",
    "CHPPowerToHeat", "CHPPowerLossFactor", "CHPMaxHeat",
]

KEEP_TAIL_COLS = ["lat", "lon"]


# -----------------------------
# Utilities
# -----------------------------
def _first_existing_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _clean_unit_name(s):
    """
    Short, filesystem-safe unit name:
    - trim
    - collapse whitespace
    - replace spaces with _
    - remove/replace separators that can break CSV parsing
    """
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "_")
    s = s.replace(";", "_").replace(",", "_").replace("\t", "_")
    s = re.sub(r"_+", "_", s)
    return s


def normalize_fuel(x):
    s = "" if x is None else str(x)
    s2 = s.strip().lower()
    if not s2:
        return np.nan
    return FUEL_MAP.get(s2, s.strip().title())


def normalize_tech(x):
    s = "" if x is None else str(x)
    s2 = s.strip().lower()
    if not s2:
        return np.nan
    return TECH_MAP.get(s2, s.strip().upper() if len(s.strip()) <= 5 else s.strip())


def country_to_iso2(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    is_iso2 = s.str.fullmatch(r"[A-Za-z]{2}")
    out = s.where(is_iso2, other=s)

    name_to_iso2 = {
        "ALBANIA": "AL",
        "AUSTRIA": "AT",
        "BELGIUM": "BE",
        "BOSNIA AND HERZEGOVINA": "BA",
        "BULGARIA": "BG",
        "CROATIA": "HR",
        "CZECH REPUBLIC": "CZ",
        "CZECHIA": "CZ",
        "DENMARK": "DK",
        "ESTONIA": "EE",
        "FINLAND": "FI",
        "FRANCE": "FR",
        "GERMANY": "DE",
        "GREECE": "GR",
        "HUNGARY": "HU",
        "IRELAND": "IE",
        "ITALY": "IT",
        "KOSOVO": "XK",
        "LATVIA": "LV",
        "LITHUANIA": "LT",
        "LUXEMBOURG": "LU",
        "MOLDOVA": "MD",
        "MONTENEGRO": "ME",
        "NETHERLANDS": "NL",
        "NORTH MACEDONIA": "MK",
        "NORWAY": "NO",
        "POLAND": "PL",
        "PORTUGAL": "PT",
        "ROMANIA": "RO",
        "SERBIA": "RS",
        "SLOVAKIA": "SK",
        "SLOVENIA": "SI",
        "SPAIN": "ES",
        "SWEDEN": "SE",
        "SWITZERLAND": "CH",
        "UKRAINE": "UA",
        "UNITED KINGDOM": "UK",
        "CYPRUS": "CY",
        "MALTA": "MT",
    }
    out = out.map(lambda x: name_to_iso2.get(str(x).strip().upper(), x))
    out = out.map(lambda x: {"EL": "GR", "GB": "UK"}.get(str(x).strip().upper(), x))
    return out.astype(str).str.upper()


def mode_nonempty(series: pd.Series):
    s = series.dropna().astype(str)
    s = s[~s.isin(["", "nan", "None"])]
    if s.empty:
        return np.nan
    return s.mode().iloc[0]


def build_defaults_from_hr_xlsx(path_xlsx: str):
    path = Path(path_xlsx)
    if path.suffix.lower() in {".csv", ".txt"}:
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    if "fuel_type" not in df.columns or "technology" not in df.columns:
        raise ValueError("HR defaults file must contain columns 'fuel_type' and 'technology'.")

    df = df.copy()
    df["fuel_type"] = df["fuel_type"].map(normalize_fuel)
    df["technology"] = df["technology"].map(normalize_tech)

    num_cols = [c for c in DEFAULTABLE_COLS if c != "CHPType" and c in df.columns]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    grp_ft = df.groupby(["fuel_type", "technology"], dropna=False)
    grp_f = df.groupby(["fuel_type"], dropna=False)

    defaults_by_ft = {}
    defaults_by_f = {}

    med_ft = grp_ft[num_cols].median(numeric_only=True) if num_cols else pd.DataFrame()
    med_f = grp_f[num_cols].median(numeric_only=True) if num_cols else pd.DataFrame()

    chp_ft = grp_ft["CHPType"].apply(mode_nonempty) if "CHPType" in df.columns else None
    chp_f = grp_f["CHPType"].apply(mode_nonempty) if "CHPType" in df.columns else None
    chp_g = mode_nonempty(df["CHPType"]) if "CHPType" in df.columns else np.nan

    for idx in med_ft.index:
        d = {}
        for c in num_cols:
            v = med_ft.loc[idx, c]
            if not (isinstance(v, float) and np.isnan(v)):
                d[c] = v
        if chp_ft is not None:
            v = chp_ft.loc[idx]
            if not (isinstance(v, float) and np.isnan(v)):
                d["CHPType"] = v
        defaults_by_ft[idx] = d

    for fuel in med_f.index:
        d = {}
        for c in num_cols:
            v = med_f.loc[fuel, c]
            if not (isinstance(v, float) and np.isnan(v)):
                d[c] = v
        if chp_f is not None:
            v = chp_f.loc[fuel]
            if not (isinstance(v, float) and np.isnan(v)):
                d["CHPType"] = v
        defaults_by_f[fuel] = d

    defaults_global = {}
    if num_cols:
        gmed = df[num_cols].median(numeric_only=True)
        for c in num_cols:
            v = gmed.get(c, np.nan)
            if not (isinstance(v, float) and np.isnan(v)):
                defaults_global[c] = v
    if "CHPType" in df.columns and not (isinstance(chp_g, float) and np.isnan(chp_g)):
        defaults_global["CHPType"] = chp_g

    return defaults_by_ft, defaults_by_f, defaults_global


def lookup_default(col, fuel, tech, defaults_by_ft, defaults_by_f, defaults_global):
    if (fuel, tech) in defaults_by_ft and col in defaults_by_ft[(fuel, tech)]:
        return defaults_by_ft[(fuel, tech)][col]
    if fuel in defaults_by_f and col in defaults_by_f[fuel]:
        return defaults_by_f[fuel][col]
    return defaults_global.get(col, np.nan)


def add_nuts3_column(
    df: pd.DataFrame,
    nuts_path: str,
    out_col: str = "NUTS3",
    nuts_id_col: str = "NUTS_ID",
    levl_col: str = "LEVL_CODE",
    levl_val: int = 3,
    lat_col: str = "lat",
    lon_col: str = "lon",
) -> pd.DataFrame:

    df = df.copy()

    # Ensure column exists and is object dtype
    if out_col not in df.columns:
        df[out_col] = None
    df[out_col] = df[out_col].astype("object")

    if lat_col not in df.columns or lon_col not in df.columns:
        return df

    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")
    ok = lat.notna() & lon.notna()

    if not ok.any():
        return df

    # Create GeoDataFrame of points (keep original index!)
    pts = gpd.GeoDataFrame(
        df.loc[ok].copy(),
        geometry=gpd.points_from_xy(lon[ok], lat[ok]),
        crs="EPSG:4326",
    )

    nuts = gpd.read_file(nuts_path)

    if levl_col in nuts.columns:
        nuts = nuts[nuts[levl_col] == levl_val].copy()

    if nuts_id_col not in nuts.columns:
        raise ValueError(f"NUTS geojson missing '{nuts_id_col}'")

    nuts = nuts[[nuts_id_col, "geometry"]].copy()

    # CRITICAL FIX: remove index_right/index_left if present
    for bad in ["index_right", "index_left"]:
        if bad in pts.columns:
            pts = pts.drop(columns=[bad])
        if bad in nuts.columns:
            nuts = nuts.drop(columns=[bad])

    # STEP 1 — spatial join (intersects)
    joined = gpd.sjoin(
        pts,
        nuts,
        how="left",
        predicate="intersects",
    )

    df.loc[joined.index, out_col] = joined[nuts_id_col].values

    # STEP 2 — nearest fallback
    still_missing = ok & df[out_col].isna()

    if still_missing.any():
        print(f"Assigning nearest NUTS3 for {still_missing.sum()} border/outside points")

        pts_missing = gpd.GeoDataFrame(
            df.loc[still_missing].copy(),
            geometry=gpd.points_from_xy(
                pd.to_numeric(df.loc[still_missing, lon_col], errors="coerce"),
                pd.to_numeric(df.loc[still_missing, lat_col], errors="coerce"),
            ),
            crs="EPSG:4326",
        )

        # Project to metric CRS for proper nearest
        pts_proj = pts_missing.to_crs(3035)
        nuts_proj = nuts.to_crs(3035)

        # Remove problematic columns again
        for bad in ["index_right", "index_left"]:
            if bad in pts_proj.columns:
                pts_proj = pts_proj.drop(columns=[bad])
            if bad in nuts_proj.columns:
                nuts_proj = nuts_proj.drop(columns=[bad])

        joined_nearest = gpd.sjoin_nearest(
            pts_proj,
            nuts_proj,
            how="left",
        )

        df.loc[joined_nearest.index, out_col] = joined_nearest[nuts_id_col].values

    return df


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--powerplants", required=True)
    ap.add_argument("--jrc-hydro", required=True)
    ap.add_argument("--template-genco", required=True)
    ap.add_argument("--hr-defaults-xlsx", required=True)
    ap.add_argument("--out-dir", required=True)

    ap.add_argument("--powerplants-country-col", default="Country")
    ap.add_argument("--powerplants-fuel-col", default="Fueltype")
    ap.add_argument("--powerplants-tech-col", default="Technology")
    ap.add_argument("--powerplants-name-col", default="Name")
    ap.add_argument("--powerplants-cap-col", default="Capacity")

    ap.add_argument("--hydro-country-col", default="country_code")
    ap.add_argument("--hydro-name-col", default="name")
    ap.add_argument("--hydro-cap-col", default="capacity_mw")
    ap.add_argument("--hydro-type-col", default="type")

    ap.add_argument("--zone-mode", default="country1", choices=["country1", "country"])
    ap.add_argument("--countries", default="auto")

    ap.add_argument("--decom-start-existing-cap", type=float, default=20.0)
    ap.add_argument("--life-time", type=float, default=25.0)
    ap.add_argument("--decom-start-new", type=float, default=25.0)

    # NUTS3 mapping
    ap.add_argument("--nuts3-geojson", required=True)
    ap.add_argument("--nuts3-id-col", default="NUTS_ID")
    ap.add_argument("--nuts3-level-col", default="LEVL_CODE")
    ap.add_argument("--nuts3-level", type=int, default=3)
    ap.add_argument("--nuts3-out-col", default="NUTS3")

    args = ap.parse_args()

    pp = pd.read_csv(args.powerplants)
    hydro = pd.read_csv(args.jrc_hydro)
    templ = pd.read_csv(args.template_genco)

    defaults_by_ft, defaults_by_f, defaults_global = build_defaults_from_hr_xlsx(args.hr_defaults_xlsx)

    pp_non_hydro = pp[pp[args.powerplants_fuel_col].astype(str).str.strip().str.lower() != "hydro"].copy()
    pp_non_hydro["country_code"] = country_to_iso2(pp_non_hydro[args.powerplants_country_col])

    hydro = hydro.copy()
    hydro["country_code"] = country_to_iso2(hydro[args.hydro_country_col])
    hydro_capacity = pd.to_numeric(hydro[args.hydro_cap_col], errors="coerce")
    invalid_hydro_capacity = hydro_capacity.isna() | (hydro_capacity <= 0)
    if invalid_hydro_capacity.any():
        print(
            f"Skipping {int(invalid_hydro_capacity.sum()):,} hydro rows with "
            "missing/non-positive capacity.",
            flush=True,
        )
        hydro = hydro.loc[~invalid_hydro_capacity].copy()

    if args.countries.strip().lower() != "auto":
        countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    else:
        countries = sorted(set(pp_non_hydro["country_code"].dropna().unique()).union(
            set(hydro["country_code"].dropna().unique())
        ))

    def zone_for(country_iso2: str) -> str:
        return country_iso2 if args.zone_mode == "country" else f"{country_iso2}1"

    available = set(pp_non_hydro.country_code.dropna()) | set(hydro.country_code.dropna())
    missing_countries = set(countries) - available
    if missing_countries:
        raise ValueError(f"No plant records in the selected raw sources for countries {sorted(missing_countries)}. Supply a source with coverage for these countries; no GENCO files were written.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_cols = list(dict.fromkeys(list(hydro.columns) + list(pp_non_hydro.columns) + list(templ.columns)))

    for c in countries:
        h_c = hydro[hydro["country_code"] == c].copy()
        p_c = pp_non_hydro[pp_non_hydro["country_code"] == c].copy()
        p_c,excluded=partition_generator_assets(p_c,fuel=args.powerplants_fuel_col,
                                               technology=args.powerplants_tech_col,capacity=args.powerplants_cap_col)
        write_asset_inventory(excluded,out_dir/f'genco_{c}_excluded_assets.csv',len(p_c)+len(h_c))
        if h_c.empty and p_c.empty:
            continue

        h_c = h_c.reindex(columns=all_cols)
        p_c = p_c.reindex(columns=all_cols)
        out = pd.concat([h_c, p_c], ignore_index=True)
        # Prevent pandas dtype warnings for string columns
        for sc in ["unit_name", "fuel_type", "technology", "CHPType", "System", "Zone", "NUTS3"]:
            if sc in out.columns:
                out[sc] = out[sc].astype("object")

        for col in templ.columns:
            if col not in out.columns:
                out[col] = np.nan

        # guarantee lat/lon
        for col in KEEP_TAIL_COLS:
            if col not in out.columns:
                out[col] = np.nan

        # fill lat/lon from any available columns (FIRST NON-NULL WINS)
        # include more candidates (common in powerplants datasets)
        lat_candidates = ["lat", "latitude", "Latitude", "LAT", "Lat", "y", "Y"]
        lon_candidates = ["lon", "longitude", "Longitude", "LON", "Lon", "lng", "Lng", "x", "X"]

        # Start with numeric coercion of existing lat/lon
        out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
        out["lon"] = pd.to_numeric(out["lon"], errors="coerce")

        # If lat/lon are missing, fill from other columns (in priority order)
        for cand in lat_candidates:
            if cand in out.columns and cand != "lat":
                src = pd.to_numeric(out[cand], errors="coerce")
                m = out["lat"].isna() & src.notna()
                out.loc[m, "lat"] = src.loc[m]
        for cand in lon_candidates:
            if cand in out.columns and cand != "lon":
                src = pd.to_numeric(out[cand], errors="coerce")
                m = out["lon"].isna() & src.notna()
                out.loc[m, "lon"] = src.loc[m]

        # unit_name
        if "unit_name" in out.columns:
            mask = out["unit_name"].isna() | (out["unit_name"].astype(str).isin(["", "nan", "None"]))
            if args.hydro_name_col in out.columns:
                m = mask & out[args.hydro_name_col].notna()
                out.loc[m, "unit_name"] = out.loc[m, args.hydro_name_col]
            if args.powerplants_name_col in out.columns:
                m = mask & out[args.powerplants_name_col].notna()
                out.loc[m, "unit_name"] = out.loc[m, args.powerplants_name_col]
            out["unit_name"] = out["unit_name"].map(_clean_unit_name)

        # cap_mw
        if "cap_mw" in out.columns:
            mask = out["cap_mw"].isna()
            if args.hydro_cap_col in out.columns:
                m = mask & out[args.hydro_cap_col].notna()
                out.loc[m, "cap_mw"] = out.loc[m, args.hydro_cap_col]
            if args.powerplants_cap_col in out.columns:
                m = mask & out[args.powerplants_cap_col].notna()
                out.loc[m, "cap_mw"] = out.loc[m, args.powerplants_cap_col]
            out["cap_mw"] = pd.to_numeric(out["cap_mw"], errors="coerce")

        # Identify hydro rows
        is_hydro_row = pd.Series(False, index=out.index)
        if args.hydro_cap_col in out.columns:
            is_hydro_row = is_hydro_row | out[args.hydro_cap_col].notna()
        if args.hydro_name_col in out.columns:
            is_hydro_row = is_hydro_row | out[args.hydro_name_col].notna()
        if "fuel_type" in out.columns:
            is_hydro_row = is_hydro_row | (out["fuel_type"].astype(str).str.strip().str.lower() == "hydro")

        # fuel_type
        if "fuel_type" in out.columns:
            mask = out["fuel_type"].isna() | (out["fuel_type"].astype(str).isin(["", "nan", "None"]))
            out.loc[mask & is_hydro_row, "fuel_type"] = "Hydro"
            if args.powerplants_fuel_col in out.columns:
                m = mask & out[args.powerplants_fuel_col].notna()
                out.loc[m, "fuel_type"] = out.loc[m, args.powerplants_fuel_col]
            out["fuel_type"] = out["fuel_type"].map(normalize_fuel)

        # technology
        if "technology" in out.columns:
            mask = out["technology"].isna() | (out["technology"].astype(str).isin(["", "nan", "None"]))
            if args.hydro_type_col in out.columns:
                m = mask & out[args.hydro_type_col].notna()
                out.loc[m, "technology"] = out.loc[m, args.hydro_type_col]
            if args.powerplants_tech_col in out.columns:
                m = mask & out[args.powerplants_tech_col].notna()
                out.loc[m, "technology"] = out.loc[m, args.powerplants_tech_col]
            out["technology"] = out["technology"].map(normalize_tech)

        # System / Zone
        if "System" in out.columns:
            out["System"] = c
        if "Zone" in out.columns:
            out["Zone"] = zone_for(c)

        # STOCapacity hydro fix
        if "STOCapacity" in out.columns:
            out["STOCapacity"] = pd.to_numeric(out["STOCapacity"], errors="coerce")
            e_mwh_col = _first_existing_col(out, ["E_MWh", "e_mwh", "E_mwh"])
            e_gwh_col = _first_existing_col(out, ["E_GWh", "e_gwh", "E_gwh"])
            stor_col = _first_existing_col(out, ["storage_capacity_MWh", "storage_capacity_mwh"])

            if e_mwh_col is not None:
                emwh = pd.to_numeric(out[e_mwh_col], errors="coerce")
                m = is_hydro_row & out["STOCapacity"].isna() & emwh.notna()
                out.loc[m, "STOCapacity"] = emwh.loc[m]
            elif e_gwh_col is not None:
                egwh = pd.to_numeric(out[e_gwh_col], errors="coerce")
                m = is_hydro_row & out["STOCapacity"].isna() & egwh.notna()
                out.loc[m, "STOCapacity"] = (egwh.loc[m] * 1000.0)
            elif stor_col is not None:
                sstor = pd.to_numeric(out[stor_col], errors="coerce")
                m = is_hydro_row & out["STOCapacity"].isna() & sstor.notna()
                out.loc[m, "STOCapacity"] = sstor.loc[m]

        # Optional: STOMaxChargingPower from pumping_MW when present
        if "STOMaxChargingPower" in out.columns:
            out["STOMaxChargingPower"] = pd.to_numeric(out["STOMaxChargingPower"], errors="coerce")
            pump_col = _first_existing_col(out, ["pumping_MW", "pump_MW", "P_pump_MW"])
            if pump_col is not None:
                p = pd.to_numeric(out[pump_col], errors="coerce")
                m = is_hydro_row & out["STOMaxChargingPower"].isna() & p.notna()
                out.loc[m, "STOMaxChargingPower"] = p.loc[m]

        # Apply HR-derived defaults
        if "fuel_type" in out.columns and "technology" in out.columns:
            for col in DEFAULTABLE_COLS:
                if col not in out.columns:
                    continue
                if col != "CHPType":
                    out[col] = pd.to_numeric(out[col], errors="coerce")
                    miss = out[col].isna()
                    if miss.any():
                        vals = [
                            lookup_default(col, f, t, defaults_by_ft, defaults_by_f, defaults_global)
                            for f, t in zip(out.loc[miss, "fuel_type"], out.loc[miss, "technology"])
                        ]
                        out.loc[miss, col] = vals
                else:
                    miss = out[col].isna() | out[col].astype(str).isin(["", "nan", "None"])
                    if miss.any():
                        vals = [
                            lookup_default(col, f, t, defaults_by_ft, defaults_by_f, defaults_global)
                            for f, t in zip(out.loc[miss, "fuel_type"], out.loc[miss, "technology"])
                        ]
                        out.loc[miss, col] = vals

        # Hard defaults for decommission
        if "decom_start_existing_cap" in out.columns:
            out["decom_start_existing_cap"] = pd.to_numeric(out["decom_start_existing_cap"], errors="coerce").fillna(
                args.decom_start_existing_cap
            )
        if "life_time" in out.columns:
            out["life_time"] = pd.to_numeric(out["life_time"], errors="coerce").fillna(args.life_time)
        if "decom_start_new" in out.columns:
            out["decom_start_new"] = pd.to_numeric(out["decom_start_new"], errors="coerce").fillna(args.decom_start_new)

        # Ensure unique unit_name
        if "unit_name" in out.columns:
            out["unit_name"] = out["unit_name"].map(_clean_unit_name)
            out["unit_name"] = pd.Series(out["unit_name"]).fillna("").astype(str)
            seen = {}
            uniq = []
            for n in out["unit_name"].tolist():
                base = n if n else "unit"
                if base not in seen:
                    seen[base] = 1
                    uniq.append(base)
                else:
                    seen[base] += 1
                    uniq.append(f"{base}_{seen[base]}")
            out["unit_name"] = uniq

        # ---- ADD NUTS3 column (uses current lat/lon) BEFORE trimming columns ----
        out = add_nuts3_column(
            out,
            nuts_path=args.nuts3_geojson,
            out_col=args.nuts3_out_col,
            nuts_id_col=args.nuts3_id_col,
            levl_col=args.nuts3_level_col,
            levl_val=args.nuts3_level,
            lat_col="lat",
            lon_col="lon",
        )

        # FINAL: delete all columns before unit_name BUT keep lat/lon (+ NUTS3) WITH DATA
        if "unit_name" in out.columns:
            lat_vals = pd.to_numeric(out["lat"], errors="coerce").to_numpy() if "lat" in out.columns else None
            lon_vals = pd.to_numeric(out["lon"], errors="coerce").to_numpy() if "lon" in out.columns else None
            nuts_vals = out[args.nuts3_out_col].astype(object).to_numpy() if args.nuts3_out_col in out.columns else None

            cols = list(out.columns)
            i = cols.index("unit_name")
            out = out[cols[i:]].copy()

            if lat_vals is not None:
                out["lat"] = lat_vals
            if lon_vals is not None:
                out["lon"] = lon_vals
            if nuts_vals is not None:
                out[args.nuts3_out_col] = nuts_vals


        # ---------------------------------
        # DROP Battery rows
        # ---------------------------------
        if "fuel_type" in out.columns:
            mask_fuel_batt = out["fuel_type"].astype(str).str.strip().str.lower() == "battery"
        else:
            mask_fuel_batt = pd.Series(False, index=out.index)

        if "technology" in out.columns:
            mask_tech_batt = out["technology"].astype(str).str.strip().str.lower() == "battery"
        else:
            mask_tech_batt = pd.Series(False, index=out.index)

        before_rows = len(out)
        out = out[~(mask_fuel_batt | mask_tech_batt)].copy()
        after_rows = len(out)

        if before_rows != after_rows:
            print(f"[{c}] Dropped {before_rows - after_rows} Battery rows")



        out_path = out_dir / f"genco_{c}_built.csv"
        out.to_csv(out_path, index=False)
        print(f"[{c}] hydro_rows={len(h_c):,} powerplants_rows={len(p_c):,} total={len(out):,} -> {out_path}")

    print(f"Done. Files in: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"ERROR: {exc}") from None
