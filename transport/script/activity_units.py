"""Units in the bundled JRC-derived national transport activity tables."""
import numpy as np
import pandas as pd


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
        efficiency = pd.to_numeric(output.efficiency_primary, errors='raise')
        if ((activity > 0) & ((efficiency <= 0) | ~np.isfinite(efficiency))).any():
            raise ValueError(f'{name}: positive transport activity has no valid primary efficiency')
        energy = (activity * 1000. / efficiency.replace(0., np.nan)).fillna(0.)
    if not np.isfinite(energy).all() or energy.lt(0).any():
        raise ValueError(f'{name}: invalid diagnostic transport energy')
    output['energy_MWh'] = energy
    return output
