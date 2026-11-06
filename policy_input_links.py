"""Keep supplied national calibration totals national after regional export."""
from pathlib import Path
import pandas as pd

ANNUAL_SHEETS=('generation_targets','hydro_caps','biomass_caps','outside_trade')


def national_table(reference,targets,generators,sheet):
    if reference.empty:return reference.copy(),[]
    if not {'System','Zone'}.issubset(reference):
        raise ValueError(f'{sheet} lacks explicit native System/Zone policy scope')
    rows=[];notes=[]
    for system in sorted({s for s,_ in targets}):
        zones={z for s,z in targets if s==system}
        source=reference.loc[reference.System.eq(system)]
        if source.empty:source=reference.loc[reference.System.eq('HR')]
        if source.empty:source=reference.loc[reference.System.eq(reference.System.iloc[0])]
        donor=str(source.System.iloc[0])
        for original in source.to_dict('records'):
            row=original.copy();row['System']=system
            if row['Zone']==donor+'1':
                row['Zone']=next(iter(zones)) if len(zones)==1 else '*'
            elif row['Zone']!='*' and row['Zone'] not in zones:
                continue
            if sheet=='generation_targets' and float(row['Target_TWh'])>0:
                local=generators.loc[generators.System.eq(system)&generators.Zone.isin(zones)]
                if row['Zone']!='*':local=local.loc[local.Zone.eq(row['Zone'])]
                fuel=str(row['Fuel'])
                aliases={'Coal','Lignite'} if fuel=='Coal' else {fuel}
                local=local.loc[local.fuel_type.isin(aliases)]
                if local.empty:
                    notes.append(dict(sheet=sheet,System=system,Zone=row['Zone'],Fuel=fuel,Year=str(row['Year']),
                                      supplied_target_TWh=float(row['Target_TWh']),applied=False,
                                      basis='supplied calibration target cannot be enforced without corresponding active sourced generators; no artificial stock added'))
                    continue
            rows.append(row)
            notes.append(dict(sheet=sheet,System=system,Zone=row['Zone'],donor_system=donor,donor_zone=str(original['Zone']),applied=True,
                              basis='supplied national scenario total kept as a system aggregate; not regional observations'))
    return pd.DataFrame(rows,columns=reference.columns),notes


def synchronize(data:Path,reference:Path,targets):
    from model_input_bundle import replace_sheets
    generators=pd.read_csv(data/'generators.csv')
    reports=[]
    for name in ('policy.xlsx','policy_efuel.xlsx'):
        patches={}
        with pd.ExcelFile(reference/'data'/name) as book:
            for sheet in ANNUAL_SHEETS:
                if sheet not in book.sheet_names:continue
                updated,notes=national_table(book.parse(sheet),targets,generators,sheet)
                patches[sheet]=updated
                reports.extend(dict(workbook=name,**r) for r in notes)
        if patches:replace_sheets(data/name,patches)
    return reports


def generation_checks(table,generators,targets):
    errors=[]
    active=generators.loc[[tuple(r) in targets for r in generators[['System','Zone']].itertuples(index=False,name=None)]]
    for row in table.to_dict('records'):
        if not any(s==row['System'] and (row['Zone']=='*' or z==row['Zone']) for s,z in targets):continue
        if float(row['Target_TWh'])<=0:continue
        local=active.loc[active.System.eq(row['System'])]
        if row['Zone']!='*':local=local.loc[local.Zone.eq(row['Zone'])]
        aliases={'Coal','Lignite'} if row['Fuel']=='Coal' else {row['Fuel']}
        if local.loc[local.fuel_type.isin(aliases)].empty:
            errors.append(f"generation_targets: no active {row['Fuel']} generators for {row['System']}/{row['Zone']}")
    return errors
