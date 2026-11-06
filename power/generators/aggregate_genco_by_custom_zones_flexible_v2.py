#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from typing import Dict, Tuple, Optional, List

import numpy as np
import pandas as pd


def _mode_nonempty(s: pd.Series):
    s = s.dropna().astype(str)
    s = s[~s.isin(["", "nan", "None"])]
    if s.empty:
        return np.nan
    return s.mode().iloc[0]


def _clean_unit_name(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip()
    s = re.sub(r"\s+", "_", s)
    s = s.replace(";", "_").replace(",", "_").replace("\t", "_")
    s = re.sub(r"_+", "_", s)
    return s


def _ensure_numeric(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def _is_chp_row(df: pd.DataFrame) -> pd.Series:
    if "CHPType" not in df.columns:
        return pd.Series(False, index=df.index)
    s = df["CHPType"].astype(str).str.strip()
    bad = {"", "nan", "none", "0", "no", "n", "false"}
    return ~s.str.lower().isin(bad)


def _parse_policy(policy_str: str) -> Dict[str, Tuple[str, Optional[int]]]:
    policy: Dict[str, Tuple[str, Optional[int]]] = {}
    if not policy_str:
        return policy

    parts = [p.strip() for p in policy_str.split(";") if p.strip()]
    for p in parts:
        if "=" not in p:
            raise ValueError(f"Bad policy token '{p}'. Use KEY=keep or KEY=aggregate:K")
        key, rhs = p.split("=", 1)
        key = key.strip().upper()
        rhs = rhs.strip().lower()

        if rhs == "keep":
            policy[key] = ("keep", None)
        elif rhs.startswith("aggregate"):
            if ":" in rhs:
                _, kstr = rhs.split(":", 1)
                k = int(kstr.strip())
            else:
                k = 1
            if k < 1:
                raise ValueError(f"Aggregate K must be >=1 for '{p}'")
            policy[key] = ("aggregate", k)
        else:
            raise ValueError(f"Bad policy RHS '{rhs}' in '{p}'. Use keep or aggregate:K")

    return policy


def _policy_lookup(
    tech: str,
    is_chp: bool,
    policy: Dict[str, Tuple[str, Optional[int]]],
    chp_separate: bool,
    precedence: str,  # tech_first or chp_first
) -> Tuple[str, int, str]:
    tech_key = ("" if tech is None else str(tech)).strip().upper()
    chp_key = "CHP" if is_chp else "NONCHP"

    def get_default():
        if "DEFAULT" in policy:
            m, k = policy["DEFAULT"]
            return m, int(k or 1), "DEFAULT"
        return "keep", 1, "IMPLICIT_KEEP"

    if precedence == "tech_first":
        if tech_key in policy:
            m, k = policy[tech_key]
            return m, int(k or 1), tech_key
        if chp_separate and chp_key in policy:
            m, k = policy[chp_key]
            return m, int(k or 1), chp_key
        return get_default()

    # chp_first
    if chp_separate and chp_key in policy:
        m, k = policy[chp_key]
        return m, int(k or 1), chp_key
    if tech_key in policy:
        m, k = policy[tech_key]
        return m, int(k or 1), tech_key
    return get_default()


def _apply_zone_mapping(df: pd.DataFrame, zone_map: pd.DataFrame, map_from_col: str) -> pd.DataFrame:
    need = {"System", "zone_old", "zone_new"}
    if not need.issubset(zone_map.columns):
        raise ValueError(f"zone-map must contain columns {sorted(list(need))}. Found: {list(zone_map.columns)}")

    df = df.copy()
    z = zone_map.copy()
    optional = ["system_new"] if "system_new" in z.columns else []
    for c in ["System", "zone_old", "zone_new", *optional]:
        z[c] = z[c].astype(str).str.strip()

    df["System"] = df["System"].astype(str).str.strip()
    if map_from_col not in df.columns:
        raise ValueError(f"--map-from '{map_from_col}' not found in input columns: {list(df.columns)}")
    df[map_from_col] = df[map_from_col].astype(str).str.strip()

    merged = df.merge(
        z.rename(columns={"zone_old": map_from_col}),
        on=["System", map_from_col],
        how="left",
        suffixes=("", "_map"),
    )

    # If a country has exactly one target in the custom map, safely use it for
    # plants whose source NUTS3 is blank or nonstandard. This is especially
    # useful for country-to-macroregion maps.
    target_cols = ["zone_new", *optional]
    country_targets = z[["System", *target_cols]].drop_duplicates()
    unique_target_systems = country_targets.groupby("System").size()
    unique_target_systems = set(unique_target_systems[unique_target_systems.eq(1)].index)
    if unique_target_systems:
        fallback = country_targets[country_targets["System"].isin(unique_target_systems)].set_index("System")
        missing = merged["zone_new"].isna() & merged["System"].isin(unique_target_systems)
        merged.loc[missing, "zone_new"] = merged.loc[missing, "System"].map(fallback["zone_new"])
        if "system_new" in merged.columns:
            merged.loc[missing, "system_new"] = merged.loc[missing, "System"].map(fallback["system_new"])

    # zone_new if matched else keep previous Zone (important for debugging)
    merged["Zone_new"] = np.where(merged["zone_new"].notna(), merged["zone_new"], merged.get("Zone", np.nan))
    merged["Zone_old"] = merged.get("Zone", np.nan)
    merged["Zone"] = merged["Zone_new"]

    # A custom map may promote zones to systems (for example countries into
    # macroregions).  Matching is performed against the original System first.
    if "system_new" in merged.columns:
        merged["System_old"] = merged["System"]
        merged["System"] = np.where(
            merged["system_new"].notna(), merged["system_new"], merged["System"]
        )

    merged.drop(columns=[c for c in ["zone_new", "system_new"] if c in merged.columns], inplace=True)
    return merged


def _bin_by_capacity(cap: pd.Series, k: int) -> pd.Series:
    k = int(max(1, k))
    idx = cap.sort_values(ascending=False).index
    bin_sum = np.zeros(k, dtype=float)
    bin_id = pd.Series(index=cap.index, dtype=int)
    for i in idx:
        b = int(np.argmin(bin_sum))
        bin_id.loc[i] = b
        v = cap.loc[i]
        bin_sum[b] += 0.0 if pd.isna(v) else float(v)
    return bin_id


def _wavg(x: pd.Series, w: pd.Series) -> float:
    x = pd.to_numeric(x, errors="coerce")
    w = pd.to_numeric(w, errors="coerce")
    m = (~x.isna()) & (~w.isna())
    if not m.any():
        return float(x.mean(skipna=True)) if x.notna().any() else np.nan
    ws = w[m].sum()
    if ws == 0:
        return float(x[m].mean()) if x[m].notna().any() else np.nan
    return float((x[m] * w[m]).sum() / ws)


def _aggregate_one(g: pd.DataFrame, unit_name: str) -> pd.Series:
    out = {}
    for c in ["System", "Zone", "fuel_type", "technology"]:
        if c in g.columns:
            out[c] = g[c].iloc[0]
    out["unit_name"] = _clean_unit_name(unit_name)

    w = pd.to_numeric(g["cap_mw"], errors="coerce") if "cap_mw" in g.columns else pd.Series(np.nan, index=g.index)

    sum_cols = [c for c in ["cap_mw", "final_life_cap", "STOCapacity", "STOMaxChargingPower", "CHPMaxHeat"] if c in g.columns]
    for c in sum_cols:
        out[c] = pd.to_numeric(g[c], errors="coerce").sum(min_count=1)

    wavg_cols = [c for c in [
        "efficiency", "cost_no_fuel", "RampingCost", "CO2Intensity",
        "RampUpRate", "RampDownRate", "STOSelfDischarge", "STOChargingEfficiency",
        "CHPPowerToHeat", "CHPPowerLossFactor"
    ] if c in g.columns]
    for c in wavg_cols:
        out[c] = _wavg(g[c], w)

    med_cols = [c for c in ["decom_start_existing_cap", "life_time", "decom_start_new"] if c in g.columns]
    for c in med_cols:
        out[c] = float(pd.to_numeric(g[c], errors="coerce").median(skipna=True)) if pd.to_numeric(g[c], errors="coerce").notna().any() else np.nan

    if "CHPType" in g.columns:
        out["CHPType"] = _mode_nonempty(g["CHPType"])
    for c in ["lat", "lon"]:
        if c in g.columns:
            out[c] = _wavg(g[c], w)
    if "NUTS3" in g.columns:
        out["NUTS3"] = _mode_nonempty(g["NUTS3"])

    return pd.Series(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--zone-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--schema-out", default=None, help="Optional CSV to write aggregation schema (old->new mapping).")

    ap.add_argument("--drop-battery", action="store_true")
    ap.add_argument("--chp-separate", action="store_true")
    ap.add_argument("--policy-precedence", choices=["tech_first", "chp_first"], default="tech_first")
    ap.add_argument("--map-from", default="Zone")
    ap.add_argument("--policy", default="DEFAULT=keep")
    ap.add_argument("--base-group-cols", default="System,Zone,fuel_type,technology")

    args = ap.parse_args()

    df = pd.read_csv(args.in_csv)
    zmap = pd.read_csv(args.zone_map)
    policy = _parse_policy(args.policy)

    if args.drop_battery:
        m1 = df["fuel_type"].astype(str).str.strip().str.lower().eq("battery") if "fuel_type" in df.columns else False
        m2 = df["technology"].astype(str).str.strip().str.lower().eq("battery") if "technology" in df.columns else False
        df = df[~(m1 | m2)].copy()

    df["_is_chp"] = _is_chp_row(df)

    # map zones; keep Zone_old/Zone_new columns for schema
    df = _apply_zone_mapping(df, zmap, args.map_from)

    # policy per row
    tech_series = df["technology"] if "technology" in df.columns else pd.Series("", index=df.index)
    pol_mode, pol_k, pol_used = [], [], []
    for tech, is_chp in zip(tech_series, df["_is_chp"]):
        mode, k, used = _policy_lookup(str(tech), bool(is_chp), policy, args.chp_separate, args.policy_precedence)
        pol_mode.append(mode)
        pol_k.append(k)
        pol_used.append(used)

    df["_policy_mode"] = pol_mode
    df["_policy_k"] = pol_k
    df["_policy_used"] = pol_used

    # Keep rows
    keep_df = df[df["_policy_mode"] == "keep"].copy()
    if "unit_name" in keep_df.columns:
        keep_df["unit_name"] = keep_df["unit_name"].map(_clean_unit_name)

    # Aggregate rows
    agg_df = df[df["_policy_mode"] == "aggregate"].copy()

    base_group_cols = [c.strip() for c in args.base_group_cols.split(",") if c.strip()]
    for c in base_group_cols:
        if c not in df.columns:
            raise ValueError(f"--base-group-cols includes '{c}' but column missing: {c}")

    group_cols = base_group_cols.copy()
    if args.chp_separate and "CHPType" in df.columns and "CHPType" not in group_cols:
        group_cols.append("CHPType")

    # ensure numeric for weights
    _ensure_numeric(df, ["cap_mw", "lat", "lon"])

    schema_rows = []  # mapping old unit -> new unit
    out_rows = []

    # Identity mappings make downstream profile builders work when plants are
    # retained individually instead of aggregated.
    for _, r in keep_df.iterrows():
        schema_rows.append({
            "new_unit_name": r.get("unit_name", np.nan),
            "old_unit_name": r.get("unit_name", np.nan),
            "System": r.get("System", np.nan),
            "Zone_old": r.get("Zone_old", np.nan),
            "Zone_new": r.get("Zone_new", np.nan),
            "fuel_type": r.get("fuel_type", np.nan),
            "technology": r.get("technology", np.nan),
            "CHPType": r.get("CHPType", np.nan),
            "cap_mw_old": r.get("cap_mw", np.nan),
            "NUTS3": r.get("NUTS3", np.nan),
            "lat": r.get("lat", np.nan),
            "lon": r.get("lon", np.nan),
        })

    if not agg_df.empty:
        for k_val, dk in agg_df.groupby("_policy_k", dropna=False):
            k_val = int(k_val) if pd.notna(k_val) else 1
            k_val = max(1, k_val)

            for gkey, g in dk.groupby(group_cols, dropna=False):
                g = g.copy()

                sys_ = g["System"].iloc[0] if "System" in g.columns else "SYS"
                zone_ = g["Zone"].iloc[0] if "Zone" in g.columns else "ZONE"
                fuel_ = g["fuel_type"].iloc[0] if "fuel_type" in g.columns else "FUEL"
                tech_ = g["technology"].iloc[0] if "technology" in g.columns else "TECH"
                chp_tag = "CHP" if bool(g["_is_chp"].iloc[0]) else "NONCHP"

                kk = min(k_val, len(g))
                if kk <= 1:
                    new_name = _clean_unit_name(f"{sys_}_{zone_}_{fuel_}_{tech_}_{chp_tag}_AGG")
                    out_rows.append(_aggregate_one(g, new_name))

                    # schema: every old -> this new
                    for _, r in g.iterrows():
                        schema_rows.append({
                            "new_unit_name": new_name,
                            "old_unit_name": r.get("unit_name", np.nan),
                            "System": r.get("System", np.nan),
                            "Zone_old": r.get("Zone_old", np.nan),
                            "Zone_new": r.get("Zone_new", np.nan),
                            "fuel_type": r.get("fuel_type", np.nan),
                            "technology": r.get("technology", np.nan),
                            "CHPType": r.get("CHPType", np.nan),
                            "cap_mw_old": r.get("cap_mw", np.nan),
                            "NUTS3": r.get("NUTS3", np.nan),
                            "lat": r.get("lat", np.nan),
                            "lon": r.get("lon", np.nan),
                        })
                else:
                    cap = pd.to_numeric(g["cap_mw"], errors="coerce").fillna(0.0) if "cap_mw" in g.columns else pd.Series(0.0, index=g.index)
                    bin_id = _bin_by_capacity(cap, kk)

                    for b in range(kk):
                        gg = g[bin_id == b]
                        if gg.empty:
                            continue
                        new_name = _clean_unit_name(f"{sys_}_{zone_}_{fuel_}_{tech_}_{chp_tag}_AGG{b+1}")
                        out_rows.append(_aggregate_one(gg, new_name))

                        for _, r in gg.iterrows():
                            schema_rows.append({
                                "new_unit_name": new_name,
                                "old_unit_name": r.get("unit_name", np.nan),
                                "System": r.get("System", np.nan),
                                "Zone_old": r.get("Zone_old", np.nan),
                                "Zone_new": r.get("Zone_new", np.nan),
                                "fuel_type": r.get("fuel_type", np.nan),
                                "technology": r.get("technology", np.nan),
                                "CHPType": r.get("CHPType", np.nan),
                                "cap_mw_old": r.get("cap_mw", np.nan),
                                "NUTS3": r.get("NUTS3", np.nan),
                                "lat": r.get("lat", np.nan),
                                "lon": r.get("lon", np.nan),
                            })

    out_agg = pd.DataFrame(out_rows) if out_rows else pd.DataFrame()

    # Combine keep + agg
    if out_agg.empty:
        out_final = keep_df.copy()
    else:
        all_cols = list(dict.fromkeys(list(keep_df.columns) + list(out_agg.columns)))
        out_final = pd.concat([keep_df.reindex(columns=all_cols), out_agg.reindex(columns=all_cols)], ignore_index=True)

    # drop internal cols
    for c in ["_is_chp", "_policy_mode", "_policy_k", "_policy_used"]:
        if c in out_final.columns:
            out_final.drop(columns=[c], inplace=True)

    out_final.to_csv(args.out, index=False)
    print(f"GENCO written: {args.out}  (rows={len(out_final):,})")

    if args.schema_out:
        schema_df = pd.DataFrame(schema_rows)
        schema_df.to_csv(args.schema_out, index=False)
        print(f"Schema written: {args.schema_out}  (rows={len(schema_df):,})")


if __name__ == "__main__":
    main()
