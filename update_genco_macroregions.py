#!/usr/bin/env python3
"""Update European rows in the macroregion GENCO template."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


EUROPE = {
    "Baltics", "Central_EU", "East_EU", "Iberia",
    "Nordics", "South_EU", "West_EU",
}

FUEL_MAP = {
    "Biogas": "Biomass",
    "Solid Biomass": "Biomass",
    "Biomass": "Biomass",
    "Coal": "Coal",
    "Gas": "Gas",
    "Geothermal": "Geothermal",
    "Hydro": "Hydro",
    "Nuclear": "Nuclear",
    "Oil": "Oil",
    "Solar": "Solar",
    "Waste": "Waste",
    "Wind": "Wind",
}

SUM_COLUMNS = {
    "cap_mw", "max_cap", "final_life_cap", "STOCapacityGWh",
    "STOMaxChargingPower", "CHPMaxHeat",
}
MEDIAN_COLUMNS = {"decom_start_existing_cap", "life_time", "decom_start_new"}
WEIGHTED_COLUMNS = {
    "efficiency", "cost_no_fuel", "RampingCost", "CO2Intensity",
    "RampUpRate", "RampDownRate", "STOSelfDischarge",
    "STOChargingEfficiency", "CHPPowerToHeat", "CHPPowerLossFactor",
}


def target_technology(fuel: str, technology: str) -> str | None:
    if fuel == "Hydro":
        return technology if technology in {"HDAM", "HPHS", "HROR"} else None
    return {
        "Solar": "PHOT",
        "Wind": "WTON",
        "Biomass": "STUR",
        "Coal": "STUR",
        "Gas": "STUR",
        "Geothermal": "STUR",
        "Nuclear": "STUR",
        "Oil": "STUR",
        "Waste": "STUR",
    }.get(fuel)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(0)
    valid = values.notna()
    if not valid.any():
        return np.nan
    total = weights[valid].sum()
    if total > 0:
        return float((values[valid] * weights[valid]).sum() / total)
    return float(values[valid].mean())


def aggregate_group(group: pd.DataFrame, template_row: pd.Series) -> pd.Series:
    result = template_row.copy()
    weights = pd.to_numeric(group["cap_mw"], errors="coerce").fillna(0)
    for column in result.index:
        if column in SUM_COLUMNS and column in group:
            result[column] = pd.to_numeric(group[column], errors="coerce").sum(min_count=1)
        elif column in MEDIAN_COLUMNS and column in group:
            values = pd.to_numeric(group[column], errors="coerce")
            if values.notna().any():
                result[column] = float(values.median())
        elif column in WEIGHTED_COLUMNS and column in group:
            value = weighted_mean(group[column], weights)
            if pd.notna(value):
                result[column] = value
    return result


def build(template: pd.DataFrame, generated: pd.DataFrame) -> pd.DataFrame:
    source = generated[generated["System"].isin(EUROPE)].copy()
    source["target_fuel"] = source["fuel_type"].map(FUEL_MAP)
    source["target_technology"] = [
        target_technology(fuel, str(technology)) if pd.notna(fuel) else None
        for fuel, technology in zip(source["target_fuel"], source["technology"])
    ]
    source = source.dropna(subset=["target_fuel", "target_technology"])

    output_rows = []
    for _, template_row in template.iterrows():
        if template_row["System"] not in EUROPE:
            output_rows.append(template_row)
            continue
        matched = source[
            source["System"].eq(template_row["System"])
            & source["target_fuel"].eq(template_row["fuel_type"])
            & source["target_technology"].eq(template_row["technology"])
        ]
        if matched.empty:
            result = template_row.copy()
            for column in SUM_COLUMNS & set(result.index):
                result[column] = 0.0
        else:
            result = aggregate_group(matched, template_row)
        output_rows.append(result)

    result = pd.DataFrame(output_rows, columns=template.columns)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    template = pd.read_csv(args.template)
    generated = pd.read_csv(args.generated)
    result = build(template, generated)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False)
    european = result[result["System"].isin(EUROPE)]
    duplicates = european.duplicated(["System", "fuel_type", "technology"]).sum()
    print(f"Wrote {len(result)} rows ({len(european)} European, {len(result) - len(european)} preserved).")
    print(f"Duplicate European System/fuel/technology keys: {duplicates}")


if __name__ == "__main__":
    main()
