"""Allocate represented building final energy with occupied area, weather and guest nights."""
from pathlib import Path

import numpy as np
import pandas as pd


def evidence_path(cache, country, year):
    name = f"occupancy_{country}_{year}.csv"
    local = Path(cache) / name
    if local.is_file():
        return local
    bundled = Path(__file__).with_name(name)
    if bundled.is_file():
        return bundled
    return None


def balance_fuels(prior, target):
    """Keep district heating fixed, and fit remaining fuels to both annual margins."""
    district = prior.get("district_heating", pd.Series(0., index=prior.index))
    residual = target - district.to_numpy()
    if residual.min() < -1e-6:
        zone = prior.index[np.argmin(residual)]
        raise ValueError(f"District heating exceeds the occupancy-based building total in {zone}. Review the district allocation or occupancy evidence.")
    residual = np.maximum(residual, 0)
    other = prior.drop(columns="district_heating", errors="ignore")
    result = prior.copy()
    if len(other.columns):
        matrix = other.to_numpy(dtype=float, copy=True)
        totals = matrix.sum(axis=0)
        for _ in range(10000):
            rows = matrix.sum(axis=1)
            matrix *= np.divide(residual, rows, out=np.zeros_like(rows), where=rows > 0)[:, None]
            cols = matrix.sum(axis=0)
            matrix *= np.divide(totals, cols, out=np.zeros_like(cols), where=cols > 0)
            if np.max(np.abs(matrix.sum(axis=1) - residual)) < 1e-6:
                break
        result[other.columns] = matrix
    if (not np.allclose(result.sum(axis=1), target, rtol=0, atol=1e-6)
            or not np.allclose(result.sum(), prior.sum(), rtol=1e-12, atol=1e-6)):
        raise ValueError("Regional fuel evidence cannot satisfy county and national heating totals")
    return result


def allocate(annual, residential, tertiary, stats, degree_hours, evidence, year, output):
    zones = pd.Index(stats.nuts3_id, name="nuts3_id")
    data = pd.read_csv(evidence).set_index("nuts3_id", verify_integrity=True)
    nights_columns = [f"nights_{month}" for month in range(1, 13)]
    if set(data.index) != set(zones):
        raise ValueError(f"Occupancy evidence must cover exactly the NUTS 3 regions for this run: {evidence}")
    data = data.loc[zones, ["occupied_m2", *nights_columns]].astype(float)
    if not np.isfinite(data).all().all() or (data < 0).any().any():
        raise ValueError(f"Invalid occupied area or commercial nights in {evidence}")
    prior = annual.pivot(index="nuts3_id", columns="fuel", values="annual_mwh").loc[zones]
    represented = {"gas", "oil", "coal", "biomass", "electric_heater", "heat_pump", "district_heating"}
    dates = pd.date_range(f"{year}-01-01", f"{year+1}-01-01", freq="h", inclusive="left")
    months = dates[~((dates.month == 2) & (dates.day == 29))].month.to_numpy() - 1
    hdd = np.stack([degree_hours[zone] for zone in zones])
    pop = stats.pop_sum.to_numpy()[:, None]
    guest = data[nights_columns].to_numpy()[:, months] / np.bincount(months)[months]
    area = data.occupied_m2.to_numpy()[:, None]
    flat = np.ones(len(months))
    lodging_share = 0.10
    components = {}
    excluded = {}
    for sector, amounts in (("residential", residential), ("tertiary", tertiary)):
        for use, fuels in amounts.items():
            total = sum(v for f, v in fuels.items() if f in represented)
            for fuel, mwh in fuels.items():
                if fuel not in represented and mwh:
                    excluded[f"{sector}/{use}/{fuel}"] = mwh
            space = use == "space_heating"
            shape = hdd if space else flat
            if sector == "residential":
                groups = [("residential", 1., area if space else pop)]
            else:
                groups = [("other_services", 1-lodging_share, pop), ("accommodation", lodging_share, guest)]
            for label, fraction, weight in groups:
                weights = weight * shape
                key = f"{label}_{use}_MWh"
                if not np.isfinite(weights).all() or weights.min() < 0 or (total > 0 and weights.sum() <= 0):
                    raise ValueError(f"No valid hourly allocation weights for {key}")
                components[key] = weights * (total*fraction / weights.sum() if total else 0.)
    hourly = sum(components.values())
    targets = hourly.sum(axis=1)
    if not np.isclose(targets.sum(), prior.to_numpy().sum(), rtol=1e-10):
        raise ValueError("Building end uses do not reconcile to represented national fuel inputs")
    balanced = balance_fuels(prior, targets)
    annual = annual.copy()
    annual["annual_mwh"] = balanced.stack().reindex(pd.MultiIndex.from_frame(annual[["nuts3_id", "fuel"]])).to_numpy()
    normalized = np.divide(hourly, targets[:, None], out=np.zeros_like(hourly), where=targets[:, None] > 0)
    detail = pd.DataFrame({"nuts3_id": np.repeat(zones, 12), "month": np.tile(np.arange(1,13), len(zones))})
    for key, values in components.items():
        detail[key] = np.column_stack([values[:, months == m].sum(axis=1) for m in range(12)]).ravel()
    detail.to_csv(output / "building_heat_end_uses_monthly.csv", index=False)
    return annual, dict(zip(zones, normalized)), dict(
        allocation="occupied_area_and_monthly_guest_nights_v1", occupancy_file=evidence.name,
        accommodation_fraction_of_each_tertiary_end_use=lodging_share, excluded_source_MWh=excluded)
