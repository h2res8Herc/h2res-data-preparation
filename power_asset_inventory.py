"""Keep carrier storage and records without usable MW out of generator stock.

Excluded source records remain in a separate, explicit inventory. They are not
silently converted into electric generators or native storage capacities.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd


NON_GENERATOR_STORAGE = {'battery', 'batterystorage', 'hydrogenstorage',
                         'heatstorage', 'thermalstorage', 'mechanicalstorage'}


def partition_generator_assets(frame, *, fuel='fuel_type', technology='technology', capacity='cap_mw'):
    def normalized(column):
        values=frame[column] if column in frame else pd.Series('',index=frame.index)
        return values.fillna('').astype(str).str.lower().str.replace(r'[^a-z0-9]', '', regex=True)
    storage=normalized(fuel).isin(NON_GENERATOR_STORAGE) | normalized(technology).isin(NON_GENERATOR_STORAGE)
    mw=pd.to_numeric(frame[capacity],errors='coerce')
    invalid=~np.isfinite(mw) | mw.lt(0)
    reason=pd.Series('',index=frame.index,dtype=object)
    reason.loc[invalid]='missing_or_invalid_electric_power_capacity_MW'
    reason.loc[storage]='storage_inventory_not_an_electric_generator'
    excluded=frame.loc[reason.ne('')].copy()
    excluded['exclusion_reason']=reason.loc[excluded.index]
    return frame.loc[reason.eq('')].copy(),excluded


def write_asset_inventory(excluded, path, generator_count):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    excluded.to_csv(path,index=False)
    report=dict(method='explicit_generator_asset_selection_v1',generators_retained=int(generator_count),
                excluded_records=len(excluded),excluded_inventory=path.name,
                reasons={str(k):int(v) for k,v in excluded.exclusion_reason.value_counts().items()},
                interpretation='Excluded records are retained as source inventory. Carrier storage is not an electric generator; '
                  'missing electric MW is not inferred from storage MWh. Excluded records are not automatically '
                  'transferred into native storage stocks; those retain their documented scenario defaults.')
    path.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
