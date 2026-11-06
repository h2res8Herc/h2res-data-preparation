"""Data conventions shared by the portable generators and H2RES 1 November 2026."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

INVESTMENT_YEARS = range(2025, 2051)
CAPTURE_LIMITS = ("CC_max_inv_period", "Reboiler_max_inv_period", "Tank_stor_max_inv_period")
CAPTURE_DEFAULTS = {
    "CC_cap": 0.0, "CC_el_dem": 0.113806, "Reboiler_cap": 0.0,
    "Tank_stor_cap": 0.0, "CC_capture_rate": 0.9,
    "CC_strip_heat_dem": 1.0, "CC_strip_el_dem": 0.002654, "CC_active": "N",
}
REGULAR_FUELS = {
    "diesel": "Oil", "fuel_oil": "Oil", "LPG": "Oil", "kerosene": "Oil",
    "bitumen": "Oil", "petrol": "Oil",
    "H2": "Hydrogen", "non_energy_gas": "non_energy", "non_energy_oil": "non_energy",
}
TRANSPORT_UNIT_ALIASES = {
    # National source tables describe shipping geography; the live model uses
    # these short/long route identifiers for the same two service sectors.
    "ICE_MARINE_DOM": "ICE_MARINE_SHORT",
    "ICE_MARINE_INT": "ICE_MARINE_LONG",
}


def transport_identifiers(frame: pd.DataFrame) -> pd.DataFrame:
    """Use live model names in fleet rows and cached hourly profile columns."""
    result = frame.rename(columns=TRANSPORT_UNIT_ALIASES).copy()
    if result.columns.duplicated().any():
        raise ValueError("Transport inputs contain duplicate unit columns after normalizing legacy shipping names")
    for column in ("unit_name", "compat_parent", "sector_prim"):
        if column in result:
            result[column] = result[column].replace(TRANSPORT_UNIT_ALIASES)
    return result


def industry_label(value: object) -> str:
    """Keep the exact reader identifiers, including the parentheses in NES."""
    label = re.sub(r"\s*\[.*?\]\s*$", "", str(value).strip())
    label = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    label = label.replace("_and_", "_")
    if label == "Not_elsewhere_specified_industry":
        return "Not_elsewhere_specified_(industry)"
    return label


def industry_category(value: object) -> str:
    match = re.search(r"\[([^]]+)\]\s*$", str(value))
    return re.sub(r"[\s-]+", "_", match.group(1).strip()) if match else "all"


def annual_limits(frame: pd.DataFrame, *, process: bool = True, capture: bool = True) -> pd.DataFrame:
    """Append missing years; zero and blank retain their different model meanings."""
    result = frame.copy()
    additions = {}
    prefixes = (["max_inv_period"] if process else []) + (list(CAPTURE_LIMITS) if capture else [])
    for prefix in prefixes:
        for year in INVESTMENT_YEARS:
            name = f"{prefix}_{year}"
            if name not in result:
                additions[name] = result[prefix] if prefix in result else np.nan
    if additions:
        result = pd.concat([result, pd.DataFrame(additions, index=result.index)], axis=1)
    validate_limits(result)
    return result


def validate_limits(frame: pd.DataFrame) -> None:
    for name in frame:
        if not re.fullmatch(r"(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?", str(name)):
            continue
        values = frame[name].replace(r"^\s*$", np.nan, regex=True)
        numeric = pd.to_numeric(values, errors="coerce")
        bad = values.notna() & (numeric.isna() | ~np.isfinite(numeric) | numeric.lt(0))
        if bad.any():
            raise ValueError(f"Invalid non-negative investment limit in {name}, rows {frame.index[bad].tolist()[:5]}")


def model_calendar(frame: pd.DataFrame, time_column: str | None = None) -> pd.DataFrame:
    """Use the model's 8760-hour calendar, dropping February 29 by date only."""
    result = frame.copy()
    time_column = time_column or next((c for c in ("timestamp", "time", "Datetime") if c in result), None)
    if time_column:
        stamps = pd.to_datetime(result[time_column], utc=True, errors="raise")
        result = result.loc[~((stamps.dt.month == 2) & (stamps.dt.day == 29))].copy()
        stamps = pd.to_datetime(result[time_column], utc=True, errors="raise")
        unique = pd.DatetimeIndex(stamps.unique()).sort_values()
        if len(unique) != 8760 or not (unique[1:] - unique[:-1]).isin([pd.Timedelta(hours=1), pd.Timedelta(hours=25)]).all():
            raise ValueError("Hourly input must cover one complete 8760-hour model year")
        if unique.year.nunique() != 1 or unique[0].month != 1 or unique[0].day != 1 or unique[0].hour != 0:
            raise ValueError("Hourly input must start at January 1, 00:00")
        period_lookup = {stamp: number for number, stamp in enumerate(unique, 1)}
        result["period"] = stamps.map(period_lookup).astype(int)
        result = result.drop(columns=time_column)
    if "period" not in result:
        if len(result) != 8760:
            raise ValueError("An input without timestamps must have exactly 8760 rows")
        result.insert(0, "period", np.arange(1, 8761))
    periods = pd.to_numeric(result["period"], errors="raise")
    if set(periods) != set(range(1, 8761)):
        raise ValueError("Hourly periods must be exactly 1 through 8760")
    return result[["period"] + [c for c in result if c != "period"]].reset_index(drop=True)
