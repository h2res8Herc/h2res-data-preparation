"""Cross-sheet model contracts, beyond checking that Excel files can be opened."""
from __future__ import annotations

import numpy as np
import pandas as pd
import re


def outside_supply_checks(shares, curves):
    """The native outside-system curves are global, irrespective of System tags."""
    errors=[]
    for label,frame,key,columns in (
        ('outside_system_supply_shares.csv',shares,'year',['outside_wind_supply_share','outside_pv_supply_share']),
        ('outside_system_normalized_curves.csv',curves,'period',['outside_demand_normalized','outside_wind_cf','outside_pv_cf'])):
        if not {key,*columns}.issubset(frame):
            errors.append(f'{label} lacks the native outside-system fields')
            continue
        index=pd.to_numeric(frame[key],errors='coerce')
        if index.isna().any() or not np.isfinite(index).all() or index.duplicated().any() or not index.eq(index.round()).all():
            errors.append(f'{label} requires one row per integer {key}; regional copies are invalid')
        values=frame[columns].apply(pd.to_numeric,errors='coerce')
        if not np.isfinite(values).all().all() or not values.ge(0).all().all() or not values.le(1).all().all():
            errors.append(f'{label} has values outside [0, 1]')
        if key=='year' and values.sum(axis=1).gt(1+1e-9).any():
            errors.append('Outside-system wind and PV shares sum above one')
        if key=='period':
            if set(index)!=set(range(1,8761)):
                errors.append('Outside-system normalized curves lack the full 8760-hour calendar')
            if values.mean().le(0).any():
                errors.append('Outside-system curves require positive annual means')
    return errors


def industry_checks(industry, simple, profiles, mode):
    errors, checks = [], {}
    keys = ['System','zone','Industry'] + (['category'] if 'category' in industry else [])
    needed = {'System','zone','Industry','unit_name','fuel_type','include_in_the_model','cap_mw','share_fuel_2020','max_share_fuel','efficiency'}
    if not needed.issubset(industry):
        return [f'Industry_data lacks model fields {sorted(needed-set(industry))}'],checks
    if industry.duplicated(keys+['unit_name']).any():
        errors.append('Industry_data has duplicate physical service/equipment keys')
    flags = industry.include_in_the_model.astype(str).str.strip().str.upper().isin(['Y','YES','TRUE','1','1.0'])
    active = industry.loc[flags,keys].drop_duplicates()
    main = industry.loc[~industry.unit_name.str.startswith('HP_industry_',na=False)].copy()
    excluded = main.merge(active.assign(_active=True),on=keys,how='left',validate='many_to_one')
    excluded = excluded.loc[excluded._active.isna()]
    for label,table in [('Industry_data',industry),('simple_industry',simple)]:
        if table.empty:
            continue
        fields = ['cap_mw','share_fuel_2020','max_share_fuel','efficiency']
        if not set(fields).issubset(table):
            errors.append(f'{label} lacks required numeric model fields')
            continue
        values = table[fields].apply(pd.to_numeric,errors='coerce')
        if not np.isfinite(values).all().all() or values.lt(0).any().any():
            errors.append(f'{label} contains invalid baseline, share or efficiency values')
        if (values.max_share_fuel+1e-9 < values.share_fuel_2020).any():
            errors.append(f'{label} has share ceilings below its generated baseline')
        if (values.share_fuel_2020>1+1e-8).any() or (values.max_share_fuel>1+1e-8).any():
            errors.append(f'{label} contains a fuel share greater than one')
        if (values.efficiency.le(0)&values.cap_mw.gt(0)).any():
            errors.append(f'{label} has nonpositive efficiency for existing equipment')
    stock_keys = ['System','zone','unit_name','fuel_type']
    if not set(stock_keys+['cap_mw','share_fuel_2020']).issubset(simple):
        return errors+['simple_industry lacks the native pooling schema'],checks
    if simple.duplicated(stock_keys).any():
        errors.append('simple_industry has duplicate pooled equipment keys')
    source_cap = excluded.groupby(stock_keys,dropna=False).cap_mw.sum().astype(float)
    pooled_cap = simple.groupby(stock_keys,dropna=False).cap_mw.sum().astype(float)
    expected,actual = source_cap.align(pooled_cap,fill_value=0.)
    if not np.allclose(expected,actual,rtol=1e-8,atol=1e-6):
        errors.append('simple_industry capacity does not equal the fully excluded Industry_data equipment; stocks are missing or double-counted')
    additive=[c for c in excluded if c in {'max_cap','CC_cap','Reboiler_cap','Tank_stor_cap'}
              or re.fullmatch(r'(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?',str(c))]
    for column in additive:
        if excluded.empty and simple.empty:continue
        if column not in simple:
            errors.append(f'simple_industry lacks the source stock/build envelope {column}')
            continue
        expected=excluded.groupby(stock_keys,dropna=False)[column].agg(lambda s:pd.to_numeric(s,errors='raise').sum() if s.notna().all() else np.nan)
        actual=simple.groupby(stock_keys,dropna=False)[column].agg(lambda s:pd.to_numeric(s,errors='raise').sum() if s.notna().all() else np.nan)
        expected,actual=expected.align(actual,fill_value=0.)
        if not np.allclose(expected.astype(float),actual.astype(float),rtol=1e-8,atol=1e-6,equal_nan=True):
            errors.append(f'simple_industry does not conserve {column}, including unrestricted bounds')
    weights = {}
    category_mode = mode=='categories'
    for record in excluded[keys].drop_duplicates().to_dict('records'):
        column = record['Industry'] + ('['+str(record.get('category','all'))+']' if category_mode else '')
        local = profiles.loc[profiles.System.eq(record['System'])&profiles.zone.eq(record['zone'])]
        if column not in local:
            errors.append(f'Industry demand missing for pooled service {record}')
            continue
        weights[tuple(record[k] for k in keys)] = float(local[column].sum())
    total_by_zone = {}
    for key,amount in weights.items():
        total_by_zone[key[:2]]=total_by_zone.get(key[:2],0.)+amount
    share_amounts,final_amounts,carbon_amounts = {},{},{}
    for row in excluded.to_dict('records'):
        key=tuple(row[k] for k in keys)
        asset=tuple(row[k] for k in stock_keys)
        share_amounts[asset]=share_amounts.get(asset,0.)+float(row['share_fuel_2020'])*weights.get(key,0.)
        amount=float(row['share_fuel_2020'])*weights.get(key,0.)
        if amount>0 and float(row['efficiency'])>0:
            final=amount/float(row['efficiency'])
            final_amounts[asset]=final_amounts.get(asset,0.)+final
            if 'CO2Intensity' in row:
                carbon_amounts[asset]=carbon_amounts.get(asset,0.)+final*float(row['CO2Intensity'])
    shares = simple.set_index(stock_keys).share_fuel_2020.to_dict()
    for asset in set(share_amounts)|set(shares):
        total = total_by_zone.get(asset[:2],0.)
        target = share_amounts.get(asset,0.)/total if total else 0.
        if not np.isclose(float(shares.get(asset,0.)),target,rtol=1e-8,atol=1e-9):
            errors.append(f'simple_industry has an incorrect demand-weighted fuel share for {asset}')
            break
    pooled=simple.set_index(stock_keys)
    for asset,final in final_amounts.items():
        if asset not in pooled.index or final<=0:
            continue
        row=pooled.loc[asset]
        efficiency=share_amounts[asset]/final
        if not np.isclose(float(row.efficiency),efficiency,rtol=1e-8,atol=1e-9):
            errors.append(f'simple_industry does not conserve baseline fuel input for {asset}')
            break
        if asset in carbon_amounts and 'CO2Intensity' in row:
            if not np.isclose(float(row.CO2Intensity),carbon_amounts[asset]/final,rtol=1e-8,atol=1e-9):
                errors.append(f'simple_industry does not conserve baseline combustion coefficients for {asset}')
                break
    # A positive source service needs a complete baseline mix, whether detailed
    # or pooled. Zero-demand placeholders may legitimately have zero shares.
    baseline = main.groupby(keys).share_fuel_2020.sum()
    detailed = industry.loc[flags & ~industry.unit_name.str.startswith('HP_industry_',na=False)].groupby(keys).share_fuel_2020.sum()
    for key in active.itertuples(index=False,name=None):
        value = detailed.get(key,0.)
        if baseline.get(key,0.)>1e-9 and not np.isclose(value,1.,atol=1e-7):
            errors.append(f'Detailed industry baseline drops fuel service at {key}: shares sum to {value}')
            break
    checks.update(pooling='recomputed_from_fully_excluded_services',pooled_service_groups=len(weights),
                  pooled_annual_service_MWh=sum(weights.values()),pooled_capacity_MW=float(pooled_cap.sum()),
                  detailed_service_groups=len(active),empty_pool_is_valid=excluded.empty and simple.empty,
                  baseline_and_pool_conserved=not errors)
    return errors,checks


def generator_checks(generators, costs, limits, years, zones):
    errors=[]
    if not {'year'}.issubset(costs) or not {'year','zone'}.issubset(limits):
        return ['Power financial tables lack year/zone keys'],{}
    plants=generators.loc[generators.Zone.isin(zones)]
    names=set(plants.unit_name)
    if 'cap_mw' in plants:
        capacity=pd.to_numeric(plants.cap_mw,errors='coerce')
        invalid=~np.isfinite(capacity) | capacity.lt(0)
        if invalid.any():
            errors.append('Invalid electric generator capacities: '+str(plants.loc[invalid,'unit_name'].tolist()[:8]))
        from power_asset_inventory import partition_generator_assets
        _,excluded=partition_generator_assets(plants)
        storage=excluded.loc[excluded.exclusion_reason.eq('storage_inventory_not_an_electric_generator')]
        if not storage.empty:
            errors.append('Non-generator storage in electric generators: '+str(storage.unit_name.tolist()[:8]))
    for label,table in [('tech_cost_years',costs),('cap_inv_lim',limits)]:
        missing=names-set(table)
        if missing:
            errors.append(f'{label} lacks generator identifiers: {sorted(missing)[:8]}')
    cost_keys=['year']+(['System'] if 'System' in costs else [])
    if costs.duplicated(cost_keys).any():
        errors.append('tech_cost_years has duplicate year/system keys')
    if limits.duplicated(['zone','year']).any():
        errors.append('cap_inv_lim has duplicate zone/year keys')
    for plant in plants.itertuples(index=False):
        if plant.unit_name not in costs or plant.unit_name not in limits:
            continue
        cost=costs.loc[costs.year.isin(years)]
        if 'System' in cost:
            cost=cost.loc[cost.System.eq(plant.System)]
        limit=limits.loc[limits.zone.eq(plant.Zone)&limits.year.isin(years)]
        if set(cost.year.astype(int))!=set(years) or set(limit.year.astype(int))!=set(years):
            errors.append(f'Generator financial years or home zone missing for {plant.unit_name}/{plant.Zone}')
            continue
        for label,table in [('cost',cost),('investment',limit)]:
            values=pd.to_numeric(table[plant.unit_name],errors='coerce')
            if not np.isfinite(values).all() or values.lt(0).any():
                errors.append(f'Invalid {label} values for generator {plant.unit_name}')
    return errors,dict(generator_ids=len(names),annual_years=len(years),cost_and_investment_keys_complete=not errors)
