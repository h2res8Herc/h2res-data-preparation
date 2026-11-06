#!/usr/bin/env python3
"""Create plant- or zone-aggregated H2RES hydro curves from a compact package.

The slow ERA5/HydroBASINS calculation is deliberately outside this runtime
script. This script consumes the versioned plant runoff package, matches it to
the power GENCO rows, follows the power aggregation schema, and writes model-
ready ROR availability factors and HDAM/closed-loop HPHS scaled inflows.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0,str(PROJECT_ROOT))
from preparation_assets import PreparationAssetError,validate_hydro_profiles
DEFAULT_BULK = PROJECT_ROOT / "power" / "hydro_bulk_europe"
HYDRO_TECHS = {"HDAM", "HPHS", "HROR"}


def parse_csv(raw: str) -> list[str]:
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    radius = 6371.0
    p1, p2 = np.deg2rad(lat1), np.deg2rad(lat2)
    dp = p2 - p1
    dl = np.deg2rad(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def capped_generation(share: np.ndarray, target_mwh: float, capacity_mw: float) -> np.ndarray:
    target_mwh = min(max(float(target_mwh), 0.0), capacity_mw * len(share))
    if target_mwh == 0 or share.sum() <= 0:
        return np.zeros_like(share)
    low, high = 0.0, max(target_mwh, capacity_mw / max(float(share.max()), 1e-30))
    for _ in range(80):
        mid = (low + high) / 2
        if np.minimum(mid * share, capacity_mw).sum() < target_mwh:
            low = mid
        else:
            high = mid
    return np.minimum(high * share, capacity_mw)


def match_genco_to_plants(
    detailed: pd.DataFrame, plants: pd.DataFrame, countries: set[str], max_km: float
) -> pd.DataFrame:
    hydro = detailed[
        detailed["technology"].astype(str).str.upper().isin(HYDRO_TECHS)
        & detailed["System"].astype(str).str.upper().isin(countries)
    ].copy()
    plants = plants.copy()
    plants["id"] = plants["id"].astype(str)
    plants["country_code"] = plants["country_code"].astype(str).str.upper()
    plants["type"] = plants["type"].astype(str).str.upper()
    plants["capacity_mw"] = pd.to_numeric(plants["capacity_mw"], errors="coerce")
    plants = plants[plants["capacity_mw"].gt(0)].copy()

    rows = []
    for r in hydro.itertuples(index=False):
        country, tech = str(r.System).upper(), str(r.technology).upper()
        candidates = plants[(plants["country_code"] == country) & (plants["type"] == tech)]
        if candidates.empty:
            raise ValueError(f"No JRC candidates for {r.unit_name} ({country}/{tech})")
        lat, lon = float(r.lat), float(r.lon)
        distances = haversine_km(
            lat, lon, candidates["lat"].to_numpy(float), candidates["lon"].to_numpy(float)
        )
        position = int(np.nanargmin(distances))
        distance = float(distances[position])
        plant = candidates.iloc[position]
        if not math.isfinite(distance) or distance > max_km:
            raise ValueError(
                f"Hydro match exceeds {max_km:g} km: {r.unit_name} -> "
                f"{plant['id']} {plant['name']} ({distance:.2f} km)"
            )
        rows.append({
            "old_unit_name": str(r.unit_name),
            "plant_id": str(plant["id"]),
            "System": country,
            "technology": tech,
            "cap_mw_old": float(r.cap_mw),
            "match_distance_km": distance,
            "jrc_name": plant["name"],
        })
    # Preserve the schema when a country has no eligible hydro rows. Without
    # explicit columns, the subsequent groupby raises KeyError('plant_id')
    # instead of producing valid empty hydro outputs.
    result = pd.DataFrame(rows, columns=[
        "old_unit_name", "plant_id", "System", "technology", "cap_mw_old",
        "match_distance_km", "jrc_name",
    ])
    # A single JRC complex can legitimately correspond to multiple GENCO rows
    # (for example a reservoir and downstream station). Allocate its annual
    # generation by matched GENCO MW rather than rejecting or duplicating it.
    result["matched_plant_capacity_mw"] = result.groupby("plant_id")["cap_mw_old"].transform("sum")
    result["plant_match_count"] = result.groupby("plant_id")["old_unit_name"].transform("size")
    result["plant_capacity_share"] = result["cap_mw_old"] / result["matched_plant_capacity_mw"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument("--countries", type=parse_csv, required=True)
    parser.add_argument("--detailed-genco", type=Path, required=True)
    parser.add_argument("--aggregated-genco", type=Path, required=True)
    parser.add_argument("--aggregation-schema", type=Path, required=True)
    parser.add_argument(
        "--profiles", type=Path,
        default=DEFAULT_BULK / "outputs/profiles/runoff_shapes_2020.npz",
    )
    parser.add_argument(
        "--hydro-units", type=Path,
        default=DEFAULT_BULK / "outputs/dispaset/hydro_units.csv",
    )
    parser.add_argument(
        "--plants", type=Path,
        default=DEFAULT_BULK / "data/plants/jrc-hydro-power-plant-database.csv",
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--max-match-distance-km", type=float, default=20.0)
    parser.add_argument(
        "--output-level",
        choices=("aggregated", "individual", "both"),
        default="aggregated",
        help="Write zone-aggregated curves, individual-plant curves, or both.",
    )
    args = parser.parse_args()

    # Reject Git LFS pointers/source-ZIP placeholders before any plant mapping.
    validate_hydro_profiles(args.profiles)

    for path in (
        args.detailed_genco, args.aggregated_genco, args.aggregation_schema,
        args.profiles, args.hydro_units, args.plants,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    countries = set(args.countries)
    detailed = pd.read_csv(args.detailed_genco)
    aggregated = pd.read_csv(args.aggregated_genco)
    schema = pd.read_csv(args.aggregation_schema)
    plants = pd.read_csv(args.plants)
    mapping = match_genco_to_plants(
        detailed, plants, countries, args.max_match_distance_km
    )

    # All hydro rows are normally aggregated. Add identities for any explicitly
    # kept unit so the curve process remains compatible with alternative policy.
    schema_small = schema[["old_unit_name", "new_unit_name"]].dropna().drop_duplicates()
    missing_old = mapping.loc[
        ~mapping["old_unit_name"].isin(schema_small["old_unit_name"]), "old_unit_name"
    ]
    if len(missing_old):
        schema_small = pd.concat([
            schema_small,
            pd.DataFrame({"old_unit_name": missing_old, "new_unit_name": missing_old}),
        ], ignore_index=True)
    mapping = mapping.merge(schema_small, on="old_unit_name", how="left", validate="one_to_one")
    if mapping["new_unit_name"].isna().any():
        raise ValueError("At least one hydro GENCO row has no aggregation mapping.")

    package = np.load(args.profiles,allow_pickle=False)
    profile_ids = package["plant_id"].astype(str)
    profile_index = {v: i for i, v in enumerate(profile_ids)}
    shares = package["runoff_share"].astype(np.float64)
    timestamps = pd.to_datetime(package["time"], unit="h", origin="unix")
    if len(timestamps) not in (8760, 8784):
        raise ValueError(f"Hydro package has incomplete year: {len(timestamps)} hours")
    units = pd.read_csv(args.hydro_units)
    units["plant_id"] = units["plant_id"].astype(str)
    units = units.set_index("plant_id", drop=False)

    missing_profiles = set(mapping["plant_id"]) - set(profile_index)
    if missing_profiles:
        raise ValueError(f"Missing precomputed profiles: {sorted(missing_profiles)[:20]}")

    unit_curves: dict[str, np.ndarray] = {}
    for r in mapping.itertuples(index=False):
        meta = units.loc[r.plant_id]
        share = shares[profile_index[r.plant_id]]
        capacity = float(r.cap_mw_old)
        generation_share = float(r.plant_capacity_share)
        if r.technology == "HROR":
            generation = float(meta["annual_generation_mwh"]) * generation_share
            unit_curves[r.old_unit_name] = capped_generation(share, generation, capacity) / capacity
        elif r.technology == "HDAM":
            generation = float(meta["annual_generation_mwh"]) * generation_share
            efficiency = float(meta["discharge_efficiency"])
            unit_curves[r.old_unit_name] = share * (generation / efficiency) / capacity
        else:  # HPHS: default rule is closed-loop, hence no natural inflow.
            unit_curves[r.old_unit_name] = np.zeros_like(share)

    individual_availability: dict[str, np.ndarray] = {}
    individual_inflows: dict[str, np.ndarray] = {}
    individual_quality_rows = []
    for r in mapping.itertuples(index=False):
        curve = unit_curves[r.old_unit_name]
        if r.technology == "HROR":
            individual_availability[r.old_unit_name] = curve
        else:
            individual_inflows[r.old_unit_name] = curve
        individual_quality_rows.append({
            "unit_name": r.old_unit_name,
            "plant_id": r.plant_id,
            "System": r.System,
            "technology": r.technology,
            "capacity_mw": r.cap_mw_old,
            "plant_match_count": r.plant_match_count,
            "plant_capacity_share": r.plant_capacity_share,
            "max_value": float(curve.max()),
            "annual_equivalent_full_load_hours": float(curve.sum()),
        })

    aggregated_availability: dict[str, np.ndarray] = {}
    aggregated_inflows: dict[str, np.ndarray] = {}
    quality_rows = []
    for new_name, group in mapping.groupby("new_unit_name", sort=False):
        technologies = set(group["technology"])
        if len(technologies) != 1:
            raise ValueError(f"Aggregated hydro unit mixes technologies: {new_name}")
        tech = next(iter(technologies))
        capacities = group["cap_mw_old"].to_numpy(float)
        curves = np.vstack([unit_curves[x] for x in group["old_unit_name"]])
        combined = np.average(curves, axis=0, weights=capacities)
        if tech == "HROR":
            aggregated_availability[new_name] = combined
        else:
            aggregated_inflows[new_name] = combined
        quality_rows.append({
            "new_unit_name": new_name,
            "System": group["System"].iloc[0],
            "technology": tech,
            "capacity_mw": capacities.sum(),
            "plant_count": group["plant_id"].nunique(),
            "source_unit_count": len(group),
            "plant_ids": ";".join(dict.fromkeys(group["plant_id"])),
            "max_value": float(combined.max()),
            "annual_equivalent_full_load_hours": float(combined.sum()),
        })

    expected = set(
        aggregated.loc[
            aggregated["technology"].astype(str).str.upper().isin(HYDRO_TECHS),
            "unit_name",
        ].astype(str)
    )
    produced = set(aggregated_availability) | set(aggregated_inflows)
    if expected != produced:
        raise ValueError(
            f"Hydro curve/GENCO mismatch. Missing={sorted(expected-produced)[:10]}, "
            f"extra={sorted(produced-expected)[:10]}"
        )

    args.outdir.mkdir(parents=True, exist_ok=True)
    index = pd.DatetimeIndex(timestamps, name="Datetime")
    if args.output_level in ("aggregated", "both"):
        pd.DataFrame(aggregated_inflows, index=index).to_csv(
            args.outdir / f"ScaledInflows_{args.year}.csv"
        )
        pd.DataFrame(aggregated_availability, index=index).to_csv(
            args.outdir / f"AvailabilityFactors_HROR_{args.year}.csv"
        )
        pd.DataFrame(quality_rows).to_csv(
            args.outdir / "hydro_quality_report.csv", index=False
        )
    if args.output_level in ("individual", "both"):
        pd.DataFrame(individual_inflows, index=index).to_csv(
            args.outdir / f"ScaledInflows_{args.year}_individual.csv"
        )
        pd.DataFrame(individual_availability, index=index).to_csv(
            args.outdir / f"AvailabilityFactors_HROR_{args.year}_individual.csv"
        )
        pd.DataFrame(individual_quality_rows).to_csv(
            args.outdir / "hydro_quality_report_individual.csv", index=False
        )
    mapping.to_csv(args.outdir / "hydro_plant_to_power_unit.csv", index=False)
    print(
        f"Wrote hydro curves ({args.output_level}): "
        f"{len(aggregated_inflows)} aggregated storage / "
        f"{len(aggregated_availability)} aggregated ROR; "
        f"{len(individual_inflows)} individual storage / "
        f"{len(individual_availability)} individual ROR; "
        f"{len(timestamps)} hours."
    )


if __name__ == "__main__":
    try:
        main()
    except PreparationAssetError as error:
        print(f'ERROR: {error}',file=sys.stderr)
        raise SystemExit(2)
