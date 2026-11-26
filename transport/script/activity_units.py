"""Units in the bundled JRC-derived national transport activity tables."""
import numpy as np
import pandas as pd


# Croatian detailed transport_all inputs in H2RES_19.11.2026. Values are
# service/kWh. Only use the reference ICE level when local evidence is absent.
REFERENCE_ICE = {
    "ICE_car": 1.3914348782, "ICE_BUS": 15.3425207282, "ICE_truck": 1.7901018079,
    "ICE_RAIL": 2.0778166653, "ICE_RAIL_CARGO": 15.4328853379,
    # HR 2020 IDEES passenger-only aviation and single-counted navigation balances.
    "ICE_AVIO_SHORT": .9895181951, "ICE_AVIO_LONG": 1.7469899626,
    "ICE_MARINE_SHORT": 33.225 / (1.8911655499489841 * 11.63),
    "ICE_MARINE_MID": 903. / (39.117260933284044 * 11.63), "ICE_MARINE_LONG": 169.1244525864,
}
# Explicit Excel formulas in the detailed workbook, including positive but
# historically unrepresentative EV_truck entries in the source tables.
FORMULA_FACTORS = {
    "EV_truck": 3., "HYBRID_truck": 1.5, "HYBRID_BUS": 1.5,
    "FCEV_car": 2., "FCEV_BUS": 2., "FCEV_truck": 2.,
    "EV_AVIO_SHORT": 3., "FCEV_AVIO_SHORT": 2., "FCEV_AVIO_LONG": 2.,
    "EV_MARINE_SHORT": 3., "EV_MARINE_MID": 3.,
}
# Keep usable source coefficients for these modes. Passenger rail differs
# within the model itself: regional observations, a 3x ICE formula in HR1.
FALLBACK_FACTORS = {
    "EV_car": 5.8736372785 / REFERENCE_ICE["ICE_car"],
    "HYBRID_car": 2.3117489828 / REFERENCE_ICE["ICE_car"],
    "EV_BUS": 42.3297565782 / REFERENCE_ICE["ICE_BUS"],
    "EL_RAIL": 3.,
    "EL_RAIL_CARGO": 21.259595671 / REFERENCE_ICE["ICE_RAIL_CARGO"],
}


def transport_efficiencies(frame, *, historical=False):
    """Apply same-mode ICE coefficients within each system, zone and sector.

    Historical energy reconstruction keeps all usable source efficiencies.
    Model inputs additionally apply explicit scenario formulas at any stock.
    """
    out = frame.copy()
    eff = pd.to_numeric(out["efficiency_primary"], errors="coerce").astype(float)
    eff = eff.where(np.isfinite(eff) & eff.gt(0))
    unit = out["unit_name"].replace({"EV_RAIL": "EL_RAIL", "EV_RAIL_CARGO": "EL_RAIL_CARGO",
                                     "ICE_MARINE_DOM": "ICE_MARINE_SHORT", "ICE_MARINE_INT": "ICE_MARINE_LONG"})
    geo = [c for c in ("System", "country", "zone", "sector") if c in out]
    lookup = out[geo].assign(unit=unit, efficiency=eff)
    ice = lookup.loc[unit.isin(REFERENCE_ICE) & eff.notna()].groupby(geo + ["unit"]).efficiency
    if ice.nunique().gt(1).any():
        raise ValueError("Conflicting ICE efficiencies for the same transport mode and geography")
    parents = "ICE_" + unit.str.partition("_")[2]
    keys = pd.MultiIndex.from_frame(out[geo].assign(unit=parents))
    donor = pd.Series(ice.first().reindex(keys).to_numpy(), index=out.index)
    if not historical:
        donor = donor.fillna(parents.map(REFERENCE_ICE))
        eff = eff.fillna(unit.map(REFERENCE_ICE))
    factors = unit.map({**FALLBACK_FACTORS, **FORMULA_FACTORS})
    apply = eff.isna()
    if not historical:
        apply |= unit.isin(FORMULA_FACTORS)
    eff = eff.mask(apply & donor.notna() & factors.notna(), donor * factors)
    if not historical and (~np.isfinite(eff) | eff.le(0)).any():
        invalid = out.loc[~np.isfinite(eff) | eff.le(0), geo + ["unit_name"]]
        raise ValueError(f"No usable transport efficiency or matching reference for {invalid.iloc[0].to_dict()}")
    out["efficiency_primary"] = eff
    return out


def ensure_energy_column(frame, name):
    """Activity is in millions of pkm/tkm; efficiency is activity per kWh.

    H2RES retains the million-activity convention in total_load. Only this
    diagnostic energy column is converted to MWh: million / 1000 = 1000.
    An explicitly supplied nonzero energy_MWh column retains its own values.
    """
    output = frame.copy()
    energy = pd.to_numeric(output.get('energy_MWh', pd.Series(0., index=output.index)), errors='coerce').fillna(0.)
    if energy.abs().sum() == 0:
        activity = pd.to_numeric(output.total_load, errors='raise')
        if {"unit_name", "sector"}.issubset(output):
            output = transport_efficiencies(output, historical=True)
        efficiency = pd.to_numeric(output.efficiency_primary, errors='raise')
        if ((activity > 0) & ((efficiency <= 0) | ~np.isfinite(efficiency))).any():
            raise ValueError(f'{name}: positive transport activity has no valid primary efficiency')
        energy = (activity * 1000. / efficiency.replace(0., np.nan)).fillna(0.)
    if not np.isfinite(energy).all() or energy.lt(0).any():
        raise ValueError(f'{name}: invalid diagnostic transport energy')
    output['energy_MWh'] = energy
    return output
