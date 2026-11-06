"""Complete native regional network inputs, retaining the merged header schema.

Supplied active links take priority. Missing internal connectivity is an explicit
zero-distance national exchange assumption using reference capacity ceilings,
not a claimed observation of transmission lines. External national budgets are
allocated once over active regions.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

BASE={'System','zone','zoneTo','To','km'}
QUANTITIES={'cap_mw','cap_TWh','max_cap','max_cap_TWh','max_cap_period','max_cap_period_TWh','import2020','export2020'}


def blocks(frame):
    if frame.empty:
        raise ValueError('Native transmission field-header row is missing')
    base,units={},{}
    current=None
    for column,field in zip(frame.columns,frame.iloc[0]):
        field=str(field).strip()
        if field in BASE:
            base[field]=column
            continue
        if not str(column).startswith('Unnamed:'):
            current=str(column)
        if current:
            units.setdefault(current,{})[field]=column
    if not {'System','zone'}.issubset(base) or not units:
        raise ValueError('Cannot identify native merged transmission headers')
    return base,units


def complete_blocks(frame,headers):
    frame=frame.copy()
    base,units=blocks(frame)
    fields=list(max(units.values(),key=len))
    additions={}
    notes=[]
    for unit,mapping in units.items():
        missing=set(fields)-set(mapping)
        if not missing:
            continue
        donor=units.get('petrol') if unit=='e_petrol' else max(units.values(),key=len)
        for field in fields:
            if field not in missing:
                continue
            if field not in donor:
                raise ValueError(f'No explicit transmission assumption for {unit}/{field}')
            column=f'Unnamed: {len(frame.columns)+len(additions)}'
            values=frame[donor[field]].copy()
            values.iloc[0]=field
            additions[column]=values
            headers.append(None)
        notes.append(dict(unit=unit,fields_filled=sorted(missing),basis='compatible reference carrier parameters; e-petrol uses petrol'))
    if additions:
        frame=pd.concat([frame,pd.DataFrame(additions,index=frame.index)],axis=1)
    frame.attrs['native_header_cells']=headers
    return frame,notes


def outside_regions(frame,targets,weights):
    if 'unit_name' in frame and {'System','zone'}.issubset(frame):
        from default_model_inputs import default_rows,quantity_columns
        result,notes=default_rows(frame,targets,weights=weights,quantities=quantity_columns(frame),weight_basis='prepared electricity demand')
        return result.loc[[tuple(x) in targets for x in result[['System','zone']].itertuples(index=False,name=None)]],notes
    base,units=blocks(frame)
    rows=[frame.iloc[0].copy()]
    notes=[]
    body=frame.iloc[1:]
    for system,zone in sorted(targets):
        exact=body.loc[body[base['System']].eq(system)&body[base['zone']].eq(zone)]
        if not exact.empty:
            if len(exact)!=1:
                raise ValueError(f'Duplicate external network defaults for {system}/{zone}')
            rows.append(exact.iloc[0].copy())
            continue
        donor=body.loc[body[base['System']].eq(system)&body[base['zone']].eq(system+'1')]
        if donor.empty:
            donor=body.loc[body[base['System']].eq('HR')&body[base['zone']].eq('HR1')]
        if donor.empty:
            donor=body.loc[body[base['System']].notna()].iloc[:1]
        if donor.empty or (system,zone) not in weights:
            raise ValueError(f'No national external transfer default or demand weight for {system}/{zone}')
        row=donor.iloc[0].copy()
        row[base['System']],row[base['zone']]=system,zone
        share=float(weights[system,zone])
        for mapping in units.values():
            for field,column in mapping.items():
                if field in QUANTITIES:
                    row[column]=float(row[column])*share
        rows.append(row)
        notes.append(dict(System=system,zone=zone,source_zone=str(donor.iloc[0][base['zone']]),allocation_weight=share,
                          basis='national external capacities/build envelopes allocated once with regional demand shares'))
    result=pd.DataFrame(rows,columns=frame.columns).reset_index(drop=True)
    result.attrs.update(frame.attrs)
    return result,notes


def _components(zones,edges):
    remaining=set(zones);parts=[]
    while remaining:
        group={min(remaining)};front=list(group)
        while front:
            node=front.pop()
            for other in edges.get(node,()):
                if other not in group:
                    group.add(other);front.append(other)
        remaining-=group;parts.append(group)
    return parts


def internal_regions(frame,targets,weights):
    if 'unit_name' in frame:
        selected=frame.loc[[((s,z) in targets and (t,w) in targets) for s,z,t,w in
                            frame[['System','zone','To','zoneTo']].itertuples(index=False,name=None)]].copy()
        additions,notes=[],[]
        for system in {s for s,_ in targets}:
            zones={z for s,z in targets if s==system};edges={z:set() for z in zones}
            for r in selected.itertuples(index=False):
                if r.System==system and r.To==system and r.unit_name in ('400kV_AC','HVDC') and float(r.cap_mw)>0:
                    edges[r.zone].add(r.zoneTo);edges[r.zoneTo].add(r.zone)
            groups=_components(zones,edges)
            if len(groups)<=1:continue
            hub=max(sorted(zones),key=lambda z:weights.get((system,z),0.))
            donor=frame.loc[frame.System.eq(system)&frame.zone.eq(system+'1')]
            if donor.empty:donor=frame.loc[frame.System.eq('HR')&frame.zone.eq('HR1')]
            if donor.empty:donor=frame
            templates=donor.loc[donor.unit_name.isin(['400kV_AC','HVDC'])].drop_duplicates('unit_name')
            if templates.empty:raise ValueError(f'No electric-network coefficients for {system}')
            for component in groups:
                if hub in component:continue
                destination=max(sorted(component),key=lambda z:weights.get((system,z),0.))
                for a,b in ((hub,destination),(destination,hub)):
                    for template in templates.to_dict('records'):
                        cap=max(float(template['max_cap']),float(template['cap_mw']))
                        template.update(System=system,zone=a,To=system,zoneTo=b,km=0.,cap_mw=cap,max_cap=cap,
                                        max_cap_period=0.,var_cost=0.,loss=0.,final_life_cap=1.)
                        additions.append(template)
                    notes.append(dict(System=system,zone=a,zoneTo=b,km=0.,observed_line=False,
                                      basis='assumed national exchange link; no supplied active regional connection',
                                      capacity_basis='reference carrier capacity ceiling'))
        return pd.concat([selected,pd.DataFrame(additions,columns=frame.columns)],ignore_index=True),notes
    base,units=blocks(frame)
    body=frame.iloc[1:]
    selected=body.loc[[((s,z) in targets and (t,w) in targets) for s,z,t,w in
                       body[[base['System'],base['zone'],base['To'],base['zoneTo']]].itertuples(index=False,name=None)]].copy()
    rows=[frame.iloc[0].copy(),*[r.copy() for _,r in selected.iterrows()]]
    notes=[]
    electricity=next((name for name in ('400kV_AC','HVDC') if name in units),None)
    if electricity is None:
        raise ValueError('No reference electric transmission unit is available')
    for system in sorted({s for s,_ in targets}):
        zones={z for s,z in targets if s==system}
        edges={z:set() for z in zones}
        for _,row in selected.iterrows():
            if row[base['System']]==system and row[base['To']]==system:
                if any(float(row[m['cap_mw']])>0 for name,m in units.items() if name in ('400kV_AC','HVDC')):
                    a,b=row[base['zone']],row[base['zoneTo']]
                    edges[a].add(b);edges[b].add(a)
        components=_components(zones,edges)
        if len(components)<=1:
            continue
        hub=max(sorted(zones),key=lambda z:weights.get((system,z),0.))
        donor=body.loc[body[base['System']].eq(system)&body[base['zone']].eq(system+'1')]
        if donor.empty:
            donor=body.loc[body[base['System']].eq('HR')&body[base['zone']].eq('HR1')]
        if donor.empty:
            donor=body.iloc[:1]
        if donor.empty:
            raise ValueError(f'No reference network coefficients for {system}')
        for component in components:
            if hub in component:
                continue
            destination=max(sorted(component),key=lambda z:weights.get((system,z),0.))
            for a,b in ((hub,destination),(destination,hub)):
                row=donor.iloc[0].copy()
                row[base['zone']],row[base['System']],row[base['zoneTo']],row[base['To']]=a,system,b,system
                row[base['km']]=0.
                for name,mapping in units.items():
                    ceiling=max(float(row[mapping['max_cap']]),float(row[mapping['cap_mw']]))
                    if not np.isfinite(ceiling) or ceiling<0:
                        raise ValueError(f'Invalid reference network capacity for {name}')
                    row[mapping['cap_mw']]=ceiling
                    for field,value in {'max_cap':ceiling,'max_cap_period':0.,'var_cost':0.,'loss':0.,'el_dem':0.,'final_life_cap':1.}.items():
                        if field in mapping:row[mapping[field]]=value
                rows.append(row)
                notes.append(dict(System=system,zone=a,zoneTo=b,basis='assumed national exchange link; no supplied active regional connection',
                                  km=0.,capacity_basis='reference carrier capacity ceiling',observed_line=False))
    result=pd.DataFrame(rows,columns=frame.columns).reset_index(drop=True)
    result.attrs.update(frame.attrs)
    return result,notes


def hydrogen_regions(frame,targets,notes):
    selected=frame.loc[[((s,z) in targets and (t,w) in targets) for s,z,t,w in frame[['System','zone','To','zoneTo']].itertuples(index=False,name=None)]].copy()
    rows=[]
    for link in notes:
        donor=frame.loc[frame.System.eq(link['System'])]
        if donor.empty:donor=frame.iloc[:1]
        if donor.empty:raise ValueError('No supplied hydrogen-network assumption')
        row=donor.iloc[0].to_dict()
        row.update(System=link['System'],zone=link['zone'],To=link['System'],zoneTo=link['zoneTo'],km=0.,var_cost=0.,loss=0.,import2020=0.,
                   cap_TWh=float(row['max_cap_TWh']),max_cap_period_TWh=0.,final_life_cap=1.,efficiency=1.)
        if not ((selected.System.eq(row['System'])&selected.zone.eq(row['zone'])&selected.To.eq(row['To'])&selected.zoneTo.eq(row['zoneTo'])).any()):
            rows.append(row)
    return pd.concat([selected,pd.DataFrame(rows,columns=frame.columns)],ignore_index=True)


def synchronize(data:Path,targets,names):
    from model_input_bundle import replace_sheets
    from default_model_inputs import allocation_weights
    weights=allocation_weights(data,targets)['electricity']
    reports=[]
    for name in names:
        path=data/name
        with pd.ExcelFile(path) as book:
            patches={};fixed=[]
            for sheet in ('transmission','transmission_outside'):
                frame=book.parse(sheet)
                repairs=[]
                if 'unit_name' not in frame:
                    headers=list(next(book.book[sheet].iter_rows(min_row=1,max_row=1,values_only=True)))[:len(frame.columns)]
                    frame,repairs=complete_blocks(frame,headers)
                fixed.extend(dict(sheet=sheet,**r) for r in repairs)
                if sheet=='transmission':
                    patches[sheet],internal=internal_regions(frame,targets,weights)
                else:
                    patches[sheet],external=outside_regions(frame,targets,weights)
            if 'transmission_H2' in book.sheet_names:
                patches['transmission_H2']=hydrogen_regions(book.parse('transmission_H2'),targets,internal)
        replace_sheets(path,patches)
        reports.append(dict(workbook=name,method='regional_reference_network_defaults_v1',internal_links=internal,external_allocations=external,
                            incomplete_carrier_blocks=fixed,limitation='Added internal links are explicit national exchange assumptions, not surveyed grid assets.'))
        print(f'Prepared regional network: {name}; {len(internal)} assumed directional internal links',flush=True)
    return reports


def checks(internal,outside,targets):
    errors=[]
    long='unit_name' in internal
    base,units=({c:c for c in BASE},{}) if long else blocks(internal)
    body=internal if long else internal.iloc[1:]
    edge_units=[m for name,m in units.items() if name in ('400kV_AC','HVDC')]
    for system in {s for s,_ in targets}:
        zones={z for s,z in targets if s==system}
        edges={z:set() for z in zones}
        for _,row in body.iterrows():
            a,b=row[base['zone']],row[base['zoneTo']]
            if row[base['System']]==system and row[base['To']]==system and a in zones and b in zones:
                positive=(row['unit_name'] in ('400kV_AC','HVDC') and float(row['cap_mw'])>0) if long else any(float(row[m['cap_mw']])>0 for m in edge_units)
                if positive:
                    edges[a].add(b);edges[b].add(a)
        if len(_components(zones,edges))>1:
            errors.append(f'Active regional electricity network is disconnected for {system}')
    if 'unit_name' in outside:
        pairs=set(outside[['System','zone']].itertuples(index=False,name=None))
    else:
        b,_=blocks(outside)
        pairs=set(outside.iloc[1:][[b['System'],b['zone']]].itertuples(index=False,name=None))
    if targets-pairs:
        errors.append(f'External transfer defaults lack active regions: {sorted(targets-pairs)}')
    return errors,dict(active_regions=len(targets),national_electric_network_connected=not errors,
                       external_transfer_regions_complete=not bool(targets-pairs))
