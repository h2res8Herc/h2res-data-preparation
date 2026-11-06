"""Explicit service-preserving assumptions for the native non-eFuel tables.

Purchased heat and waste remain observations in the raw source tables. The
ordinary non-eFuel model represents their service with its available equipment.
Material feedstocks and unbuilt future technologies never receive that service.
"""
from __future__ import annotations

import math

REGULAR_FUEL_METHOD = "proportional_supported_industry_service_v1"
UNSUPPORTED_REGULAR = frozenset({"heat", "waste"})
REGULAR_ENERGY_FUELS = frozenset({"Gas", "Coal", "Oil", "Biomass", "Electricity", "Hydrogen"})


def redistribute_service_mix(amounts, fallback=None):
    """Return supported amounts and an audit of heat/waste reassignment.

    The caller supplies useful-service weights, not raw input MW. A fallback
    mix may describe the same industry's other categories in the same zone.
    If no supported incumbent exists, gas is an explicit equipment assumption.
    """
    amounts = {fuel: float(value) for fuel, value in amounts.items()}
    if any(not math.isfinite(value) or value < 0 for value in amounts.values()):
        raise ValueError("Industry service weights must be finite and nonnegative")
    result = {fuel: value for fuel, value in amounts.items() if fuel not in UNSUPPORTED_REGULAR}
    removed = {fuel: amounts.get(fuel, 0.) for fuel in sorted(UNSUPPORTED_REGULAR)}
    total = sum(removed.values())
    if not total:
        return result, []
    recipients = {f: v for f, v in result.items() if f in REGULAR_ENERGY_FUELS and v > 0}
    basis = "same_zone_industry_category_supported_service_mix"
    if not recipients:
        recipients = {f: float(v) for f, v in (fallback or {}).items()
                      if f in REGULAR_ENERGY_FUELS and math.isfinite(float(v)) and float(v) > 0}
        basis = "same_zone_industry_other_categories_supported_service_mix"
    if not recipients:
        recipients, basis = {"Gas": 1.}, "assumed_gas_no_supported_incumbent"
    denominator = sum(recipients.values())
    audit = []
    for fuel, weight in sorted(recipients.items()):
        fraction = weight / denominator
        added = total * fraction
        result[fuel] = result.get(fuel, 0.) + added
        audit.append(dict(method=REGULAR_FUEL_METHOD, recipient_fuel=fuel,
                          source_heat_weight=removed["heat"], source_waste_weight=removed["waste"],
                          recipient_fraction=fraction, added_service_weight=added, basis=basis))
    if not math.isclose(sum(result.values()), sum(amounts.values()), rel_tol=1e-12, abs_tol=1e-10):
        raise ValueError("Industry fuel redistribution did not conserve service")
    return result, audit


def regular_complex_aggregate(frame, reference):
    """Adapt the ordinary remainder only; detailed process observations stay intact.

    Process-derived aggregate MW already measures useful service / 8760, so
    recipient capacities and shares scale together. Its hourly service demand
    and observed historical electricity subtraction are unchanged.
    """
    import pandas as pd

    result, audit = [], []
    keys = ["System", "zone", "Industry", "category"]
    for key, block in frame.groupby(keys, sort=False, dropna=False):
        block = block.copy()
        block["cap_mw"] = block.cap_mw.astype(float)
        amounts = block.groupby("fuel_type").cap_mw.sum().to_dict()
        adjusted, notes = redistribute_service_mix(amounts)
        total = sum(amounts.values())
        kept = block.loc[~block.fuel_type.isin(UNSUPPORTED_REGULAR)].copy()
        for fuel, amount in adjusted.items():
            indexes = kept.index[kept.fuel_type.eq(fuel)]
            original = amounts.get(fuel, 0.)
            added = amount - original
            if added > 0 and original > 0:
                kept.loc[indexes, "cap_mw"] *= amount / original
            elif added > 0:
                usable = indexes[kept.loc[indexes, "efficiency"].gt(0)]
                if len(usable):
                    kept.loc[usable[0], "cap_mw"] = amount
                    continue
                candidates = reference.loc[reference.Industry.eq(key[2]) & reference.fuel_type.eq(fuel)]
                if candidates.empty:
                    candidates = reference.loc[reference.fuel_type.eq(fuel)]
                if candidates.empty:
                    raise ValueError(f"No non-eFuel equipment assumption for {fuel}/{key}")
                row = candidates.iloc[0].to_dict()
                row.update(dict(zip(keys, key)))
                row.update(cap_mw=amount, share_fuel_2020=0., include_in_the_model="Y")
                kept = pd.concat([kept.drop(index=indexes), pd.DataFrame([row])], ignore_index=True)
        kept["share_fuel_2020"] = kept.cap_mw / total if total else 0.
        kept["max_share_fuel"] = kept[["max_share_fuel", "share_fuel_2020"]].max(axis=1)
        if "max_cap" in kept:
            kept["max_cap"] = kept[["max_cap", "cap_mw"]].max(axis=1)
        active = kept.cap_mw.gt(0)
        kept.loc[active, "include_in_the_model"] = "Y"
        result.append(kept)
        audit.extend(dict(zip(keys, key), **note, service_weight_unit="useful_MW") for note in notes)
    return pd.concat(result, ignore_index=True) if result else frame.iloc[:0].copy(), audit
