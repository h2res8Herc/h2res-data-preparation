"""Keep sea navigation coastal and retain landlocked inland-waterway activity.

The bundled domestic-navigation rows combine JRC's coastal shipping and inland
waterways. In a country without coastal regions, positive domestic navigation
is inland activity. Legacy H2RES shipping sector/unit names are retained.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

METHOD = "coastal_maritime_inland_ports_v1"
QUANTITIES = ("total_load", "number", "energy_MWh")


def navigation_kind(sector, unit, has_coast):
    text = (str(sector) + " " + str(unit)).lower()
    if not any(word in text for word in ("ship", "marine", "navig", "waterway")):
        return None
    if any(word in text for word in ("international", "_int", "_long", "maritime", "coastal")):
        return "maritime"
    if any(word in text for word in ("inland", "waterway", "river")):
        return "inland_navigation"
    if "domestic" in text or any(word in text for word in ("_dom", "_short", "_mid")):
        return "domestic_navigation" if has_coast else "inland_navigation"
    if has_coast:
        return "maritime"
    raise ValueError(f"Cannot classify landlocked navigation row: {sector}/{unit}")


def allocate_table(original, national, nuts_ids, weights, table_kind, coastal_types,
                   shipping, notes):
    """Override navigation only, avoiding the legacy allocator's uniform fallback."""
    coast = np.array([coastal_types.get(code) in (1, 2) for code in nuts_ids])
    has_coast = bool(coast.any())
    kinds = national.apply(lambda r: navigation_kind(r['sector'], r['unit_name'], has_coast), axis=1)
    ordinary = national.loc[kinds.isna()]
    frames = [original(ordinary, nuts_ids, weights, table_kind)] if not ordinary.empty else []
    for key, block in national.loc[kinds.notna()].groupby(['sector', 'unit_name', 'type'], sort=False, dropna=False):
        kind = navigation_kind(key[0], key[1], has_coast)
        inland = kind == 'inland_navigation'
        name = ('ship_inland_' if inland else 'ship_') + ('freight' if table_kind == 'freight' else 'passenger')
        values = pd.to_numeric(shipping[name], errors='raise').to_numpy(dtype=float)
        if len(values) != len(nuts_ids) or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Invalid {kind} infrastructure weights for {key}")
        if not inland:
            values = np.where(coast, values, 0.)
        totals = block[list(QUANTITIES)].apply(pd.to_numeric, errors='raise').sum()
        positive = totals.abs().gt(1e-12).any()
        basis = 'OSM_inland_ports_and_quays' if inland else 'OSM_coastal_ports_and_quays'
        if positive and values.sum() <= 0:
            if inland:
                raise ValueError(f"Inland navigation has positive activity but no OSM port/quay evidence for {key[0]}. "
                                 "Check the country PBF; uniform allocation across all regions is not allowed.")
            if not has_coast:
                raise ValueError(f"Sea shipping has positive activity in a country with no coastal regions: {key[0]}")
            values = coast.astype(float)
            basis = 'assumed_equal_coastal_regions_no_OSM_port_proxy'
            print(f"WARNING: {key[0]} has no coastal OSM port proxy; using eligible coastal regions only.", flush=True)
        selected = dict(weights)
        weight_key = 'ship_freight' if table_kind == 'freight' else 'ship_pass'
        selected[weight_key] = pd.Series(values)
        allocated = original(block, nuts_ids, selected, table_kind)
        allocated['weight_used'] = basis
        allocated['navigation_kind'] = kind
        eligible = [code for code, value in zip(nuts_ids, values) if value > 0]
        if positive:
            actual = allocated[list(QUANTITIES)].sum()
            if not np.allclose(actual, totals, rtol=1e-10, atol=1e-7):
                raise ValueError(f"Navigation allocation did not conserve national totals for {key}")
        notes.append(dict(table_kind=table_kind, sector=key[0], unit_name=key[1], type=key[2],
                          navigation_kind=kind, weights_basis=basis, eligible_regions=eligible,
                          national_totals=totals.to_dict()))
        frames.append(allocated)
    return pd.concat(frames, ignore_index=True) if frames else original(national, nuts_ids, weights, table_kind)
