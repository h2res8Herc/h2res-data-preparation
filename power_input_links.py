"""Bind generated physical generator IDs to the native financial input tables.

Registry assets retain their names. Missing financial observations inherit
explicit reference assumptions; a source annual budget is shared among its
recipient plants, never copied in full to every plant or region.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "physical_generator_financial_links_v1"


def _normal(value):
    return re.sub('[^a-z0-9]', '', str(value).lower())


def _candidates(plant, reference, columns, system):
    possible = reference.loc[reference.unit_name.isin(columns)].copy()
    if possible.empty:
        return possible
    # Prefer the right machinery/fuel; a CHP or machinery mismatch is recorded
    # as a scenario proxy, not presented as an observed cost of the plant.
    score = (possible.technology.map(_normal).ne(_normal(plant.technology)).astype(int) * 16
             + possible.fuel_type.map(_normal).ne(_normal(plant.fuel_type)).astype(int) * 8
             + possible.CHPType.map(_normal).ne(_normal(plant.CHPType)).astype(int) * 4)
    possible = possible.loc[score.eq(score.min())]
    local = possible.loc[possible.System.eq(system) & possible.Zone.eq(system + '1')]
    if local.empty:
        local = possible.loc[possible.System.eq(system)]
    return (local if not local.empty else possible).drop_duplicates('unit_name')


def _curve(table, column, *, system=None, zone=None):
    block = table
    if zone is not None and 'zone' in block:
        block = block.loc[block.zone.eq(zone)]
    if 'System' in block:
        donor = system if block.System.eq(system).any() else 'HR' if block.System.eq('HR').any() else block.System.dropna().iloc[0]
        block = block.loc[block.System.eq(donor)]
    if block.empty:
        raise ValueError(f'No source trajectory for {column}/{system}/{zone}')
    if block.year.duplicated().any():
        raise ValueError(f'Ambiguous source years for {column}/{system}/{zone}')
    values = pd.to_numeric(block[column], errors='raise')
    if not np.isfinite(values).all() or values.lt(0).any():
        raise ValueError(f'Invalid source financial trajectory for {column}/{system}/{zone}')
    return pd.Series(values.to_numpy(float), index=block.year.astype(int))


def link_tables(generators, reference_generators, costs, limits, current_costs, current_limits, targets, zone_weights,
                heating_weights=None, heating_units=()):
    """Return complete cost/limit tables plus an auditable donor for every asset."""
    generated = generators.loc[[tuple(p) in targets for p in generators[['System','Zone']].itertuples(index=False,name=None)]].copy()
    if generated.unit_name.duplicated().any():
        raise ValueError('Generated power plant names must be unique before linking costs')
    if not {'year','zone'}.issubset(limits):
        raise ValueError('The native investment table requires year and zone columns')
    records, trajectories, pools = [], {}, {}
    original_zones = set(limits.zone.dropna())
    new_limits = current_limits.copy()
    additions = []
    for system, zone in sorted(targets):
        if new_limits.zone.eq(zone).any():
            continue
        donor_zone = system + '1' if system + '1' in original_zones else 'HR1' if 'HR1' in original_zones else str(limits.zone.dropna().iloc[0])
        block = limits.loc[limits.zone.eq(donor_zone)].copy()
        block['zone'] = zone
        share = zone_weights.get((system,zone))
        if share is None:
            raise ValueError(f'No regional demand share for investment-limit defaults in {zone}')
        for column in block:
            if column not in {'year','zone','System'}:
                local_share = (heating_weights or {}).get((system,zone),share) if column in heating_units else share
                block[column] = pd.to_numeric(block[column],errors='raise') * local_share
        if 'System' in block:
            block['System'] = system
        additions.append(block)
    if additions:
        new_limits = pd.concat([new_limits,*additions],ignore_index=True)
    # Only modeled zones enter the reader. Donor rows stay in the reference and
    # are identified in the accompanying report.
    new_limits = new_limits.loc[new_limits.zone.isin({z for _,z in targets})].copy().reset_index(drop=True)
    if new_limits.duplicated(['zone','year']).any():
        raise ValueError('Duplicate zone/year investment-limit rows')
    for plant in generated.itertuples(index=False):
        system, name = str(plant.System), str(plant.unit_name)
        cost_donors = _candidates(plant,reference_generators,set(costs),system)
        if name in costs:
            donor, basis = name, 'exact_reference_identifier'
        elif _normal(plant.fuel_type) == 'geothermal' and 'Geothermal.1' in costs:
            donor, basis = 'Geothermal.1', 'legacy_reference_geothermal_power_assumption_3_4_MEUR_per_MW'
        elif not cost_donors.empty:
            donor = str(cost_donors.sort_values('unit_name').iloc[0].unit_name)
            basis = 'reference_equipment_proxy'
        else:
            raise ValueError(f'No explicit reference cost assumption for {name}/{plant.technology}/{plant.fuel_type}')
        trajectories[name] = _curve(costs,donor,system=system)
        budget_zone = system + '1' if system + '1' in original_zones else 'HR1' if 'HR1' in original_zones else str(limits.zone.dropna().iloc[0])
        budget_system = budget_zone[:-1] if budget_zone.endswith('1') else 'HR'
        budget_donors = _candidates(plant,reference_generators,set(limits),budget_system)
        # An unmatched geothermal resource has existing stock, but no invented
        # future build allowance. It remains editable as a scenario assumption.
        if _normal(plant.fuel_type) == 'geothermal' and not reference_generators.fuel_type.map(_normal).eq('geothermal').any():
            budget_columns = ()
        else:
            budget_columns = tuple(sorted(set(budget_donors.unit_name)))
        direct = name in limits and plant.Zone in original_zones
        if direct:
            budget_columns, budget_zone = (name,), plant.Zone
        pool = (system,str(budget_zone),budget_columns)
        pools.setdefault(pool,[]).append(name)
        matched = cost_donors.loc[cost_donors.unit_name.eq(donor)]
        descriptor = matched.iloc[0].to_dict() if not matched.empty else {}
        records.append(dict(unit_name=name,System=system,zone=str(plant.Zone),technology=str(plant.technology),fuel_type=str(plant.fuel_type),
                            CHPType=str(plant.CHPType),cost_donor=donor,cost_basis=basis,
                            donor_technology=descriptor.get('technology'),donor_fuel_type=descriptor.get('fuel_type'),donor_CHPType=descriptor.get('CHPType'),
                            investment_donor_zone=str(budget_zone),investment_donor_columns=list(budget_columns),
                            investment_basis='exact_reference_allowance' if direct else 'national_reference_budget_shared_by_existing_capacity' if budget_columns else 'explicit_existing_only_zero_build_default'))
    limit_columns = {}
    capacity = pd.to_numeric(generated.set_index('unit_name').cap_mw,errors='raise').clip(lower=0)
    by_name = {r['unit_name']:r for r in records}
    for (system,zone,columns), names in pools.items():
        amounts = capacity.reindex(names)
        shares = amounts / amounts.sum() if amounts.sum() > 0 else pd.Series(1. / len(names),index=names)
        budget = sum((_curve(limits,c,zone=zone) for c in columns), start=pd.Series(0.,index=sorted(limits.year.astype(int).unique())))
        for name in names:
            row = by_name[name]
            row['investment_budget_share'] = float(shares[name])
            row['investment_national_budget_MW_by_year'] = {int(y):float(v) for y,v in budget.items()}
            values = new_limits.year.astype(int).map(budget) * float(shares[name])
            values = values.where(new_limits.zone.eq(row['zone']),0.)
            if values.isna().any():
                raise ValueError(f'Missing annual investment trajectory for {name}')
            limit_columns[name] = values
        allocated = sum(float(shares[n]) for n in names)
        if not np.isclose(allocated,1.):
            raise ValueError(f'Plant investment allocation does not conserve {system}/{zone}/{columns}')
    new_cost_columns = {name: current_costs.year.astype(int).map(values) for name,values in trajectories.items()}
    if any(v.isna().any() for v in new_cost_columns.values()):
        raise ValueError('A generator cost trajectory lacks required years')
    new_costs = pd.concat([current_costs.drop(columns=list(new_cost_columns),errors='ignore'),pd.DataFrame(new_cost_columns,index=current_costs.index)],axis=1)
    new_limits = pd.concat([new_limits.drop(columns=list(limit_columns),errors='ignore'),pd.DataFrame(limit_columns,index=new_limits.index)],axis=1)
    return new_costs,new_limits,records


def synchronize(data: Path, reference: Path, targets, workbook_names):
    from default_model_inputs import allocation_weights
    from model_input_bundle import replace_sheets, sha256
    generators = pd.read_csv(data/'generators.csv')
    original = pd.read_csv(reference/'data/generators.csv')
    weights = allocation_weights(data,targets)
    maintenance = pd.read_csv(data/'literature_fixed_opex.csv')
    published = {(str(r.workbook),str(r.technology),int(r.year)):r._asdict() for r in maintenance.itertuples(index=False)}
    extra, results = [], []
    for name in dict.fromkeys(workbook_names):
        path = data/name
        with pd.ExcelFile(path) as book,pd.ExcelFile(reference/'data'/name) as source:
            heating_units=set()
            for sheet in ('flex_tech_heat','flex_tech_DH','thermal_tech','thermal_tech_DH','solar_indv','solar_DH'):
                if sheet in source.sheet_names:
                    table=source.parse(sheet)
                    if 'unit_name' in table:
                        heating_units.update(table.unit_name.dropna())
            costs,limits,records = link_tables(generators,original,source.parse('tech_cost_years'),source.parse('cap_inv_lim'),
                                               book.parse('tech_cost_years'),book.parse('cap_inv_lim'),targets,weights['electricity'],weights['heating'],heating_units)
        for record in records:
            plant, donor = record['unit_name'],record['cost_donor']
            for year, block in costs.groupby('year',sort=False):
                key = (path.name,plant,int(year))
                if key in published:
                    continue
                source = published.get((path.name,donor,int(year)))
                row = dict(source) if source else dict.fromkeys(maintenance.columns)
                row.update(workbook=path.name,technology=plant,year=int(year))
                if not source:
                    row.update(value_MEUR_per_capacity_year=float(block[plant].iloc[0])*.01,capacity_unit='MEUR/MW_electric',
                               conversion='Explicit native H2RES fallback: annual fixed OPEX = 1 percent of CAPEX',source_id='NATIVE_REFERENCE_ASSUMPTION',
                               source_url='model_reference_2_11_2026/data/'+name,source_sheets='tech_cost_years',source_cells=donor)
                published[key]=row
                extra.append(row)
        replace_sheets(path,{'tech_cost_years':costs,'cap_inv_lim':limits})
        results.append(dict(workbook=name,method=VERSION,reference_sha256=sha256(reference/'data'/name),
                            assumptions='Financial defaults are inherited scenario assumptions, not observed plant costs. National build budgets are shared among matching generated assets.',
                            generators=records))
        print(f'Linked {len(records)} generator IDs to costs and zonal investment limits: {name}',flush=True)
    if extra:
        pd.concat([maintenance,pd.DataFrame(extra,columns=maintenance.columns)],ignore_index=True).to_csv(data/'literature_fixed_opex.csv',index=False)
    return results
