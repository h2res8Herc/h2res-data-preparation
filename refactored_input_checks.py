"""Namespace-aware checks used before and during refactored conversion."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd


def select_scope(frame, *, system=None, zone=None):
    """Select country first; global sheets without metadata remain global."""
    if system is not None and 'System' in frame:
        frame=frame.loc[frame.System.eq(system)]
    if zone is not None and 'zone' in frame:
        frame=frame.loc[frame.zone.eq(zone)]
    return frame


def unique_rows(frame, keys, label, *, values=None, allow_identical=False):
    missing=set(keys)-set(frame)
    if missing:raise ValueError(f'{label}: missing key columns {sorted(missing)}')
    if frame[keys].isna().any().any():raise ValueError(f'{label}: blank key values in {keys}')
    duplicates=frame.duplicated(keys,keep=False)
    if duplicates.any():
        if allow_identical and values:
            repeated=frame.loc[duplicates]
            conflict=repeated.groupby(keys,dropna=False)[values].nunique(dropna=False).gt(1).any(axis=1)
            if not conflict.any():return frame.drop_duplicates(keys)
        examples=frame.loc[duplicates,keys].drop_duplicates().head(3).to_dict('records')
        raise ValueError(f'{label}: conflicting or duplicate keys {keys}: {examples}')
    return frame


def common_fuel_price(values, label):
    """The target's global fuel table cannot encode different country prices."""
    values=pd.to_numeric(values,errors='raise')
    if values.empty or not np.isfinite(values).all() or values.lt(0).any():
        raise ValueError(f'{label}: missing, negative or non-finite fuel prices')
    if not np.allclose(values,values.iloc[0],rtol=1e-10,atol=1e-10):
        raise ValueError(f'{label}: different country/hour prices cannot be averaged silently into a global price; provide a common scenario price')
    return float(values.iloc[0])


def year_value(row,year,label):
    candidates=[c for c in row.index if str(c) in {str(year),str(float(year))}]
    if len(candidates)!=1 or pd.isna(row[candidates[0]]):
        raise ValueError(f'{label}: missing or ambiguous value for year {year}')
    value=float(row[candidates[0]])
    if not np.isfinite(value) or value<0:raise ValueError(f'{label}: negative/non-finite value for year {year}')
    return value


def preflight(exporter,model_root=None):
    """Collect structural/reference errors before mapping or writing CSV data.

    Full numerical calendars and conservation checks still run during mapping
    and output validation. This early pass checks selected namespaces, lookup
    coverage, required files/sheets and parameters used to scale output.
    """
    e=exporter
    errors=[];checks=0
    def check(source,operation):
        nonlocal checks
        checks+=1
        try:operation()
        except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
            errors.append(dict(source=str(source),error=str(error)))
    def require(condition,message):
        if not condition:raise ValueError(message)
    required=['generators.csv','fuel_prices.csv','policy_fuels.xlsx','electricity_demand.csv',
        'renewable_availability.csv','hydro_inflows.csv','heating_individual.csv','heating_district.csv',
        'industry_electricity.csv','heating_electricity.csv','transport_demand.csv','transport_profiles.csv',
        'industry_category_profiles.csv' if e.service_mode=='categories' else 'industry_heat.csv']
    schemas={'generators.csv':{'unit_name','System','Zone','fuel_type','technology'},
        'electricity_demand.csv':{'period','Power','System','Zone'},
        'renewable_availability.csv':{'period'},'hydro_inflows.csv':{'period'},
        'transport_demand.csv':{'period','System','zone'},'transport_profiles.csv':{'period','System','zone'},
        required[-1]:{'period','System','zone'}}
    for name in required:
        path=e.data/name
        def validate_file(path=path,name=name):
            require(path.is_file(),'Required source file is missing')
            if name.endswith('.csv'):
                columns=set(pd.read_csv(path,nrows=0))
                needed=schemas.get(name,{'period',*e.countries})
                if name=='fuel_prices.csv':needed={'year','period'}
                require(needed.issubset(columns),f'Missing columns: {sorted(needed-columns)}')
        check(path,validate_file)
    required_sheets={'flex_tech','tech_cost_years','thermal_tech','thermal_tech_DH','flex_tech_heat','flex_tech_DH',
        'COP_HP','solar_indv','solar_DH','Industry_data','simple_industry','transmission','transport_all'}
    if e.efuels:required_sheets|={'efuel','fuel_storage','efuel_inputs'}
    for name in sorted(required_sheets):
        check(f'{e.workbook}/{name}',lambda name=name:require(name in e.book.sheet_names,'Required worksheet is missing'))
    policies=['dem_change','Heat_dem_change','Heat_dem_change_DH','Industry_dem_change']
    for name in ['DH_loss','CO2','RPS','biomass_caps',*policies]:
        check('policy/'+name,lambda name=name:require(name in e.policy_book.sheet_names,'Required policy worksheet is missing'))

    for zone,system in sorted(e.countries.items()):
        def costs(zone=zone,system=system):
            block=select_scope(e.cost_table,system=system,zone=zone)
            require(not block.empty,f'No cost rows for System={system}, zone={zone}')
            unique_rows(block,['year'],f'tech_cost_years/System={system}/zone={zone}')
            values=pd.to_numeric(block.year,errors='raise')
            require(np.isfinite(values).all() and np.equal(values,np.floor(values)).all(),'Cost year keys must be integers')
            require(set(e.years).issubset(set(values)),f'Missing cost years: {sorted(set(e.years)-set(values))}')
        check(f'{e.workbook}/tech_cost_years/{system}/{zone}',costs)
        for name in policies:
            if name not in e.policy_book.sheet_names:continue
            check(f'policy/{name}/{system}/{zone}',lambda name=name,zone=zone:[e.demand_multiplier(name,zone,y) for y in e.years])
        for name in ['flex_tech_heat','flex_tech_DH']:
            if name not in e.book.sheet_names or 'COP_HP' not in e.book.sheet_names:continue
            def heating(name=name,zone=zone,system=system):
                rows=select_scope(e.sheet(name),system=system,zone=zone)
                require(not rows.empty,'No heating equipment rows in the selected country/zone')
                for unit in rows.unit_name:
                    e.trajectory(str(unit),zone)
                    e.efficiency_profile(str(unit),zone)
            check(f'{e.workbook}/{name}/{system}/{zone}',heating)

    if (e.data/'generators.csv').is_file():
        def generators():
            table=pd.read_csv(e.data/'generators.csv')
            table=table.loc[[tuple(x) in e.pairs for x in table[['System','Zone']].itertuples(index=False,name=None)]]
            unique_rows(table,['unit_name'],'generators.csv')
            failures=[]
            for row in table.itertuples(index=False):
                try:e.trajectory(row.unit_name,row.Zone)
                except (ValueError,KeyError) as error:failures.append(f'{row.unit_name}: {error}')
            if failures:raise ValueError('; '.join(failures[:8]))
        check('generators.csv/cost references',generators)
    def prices():
        block=e.fuel_prices
        if 'System' in block:block=block.loc[block.System.isin(set(e.countries.values()))]
        keys=['year','period']+(['System'] if 'System' in block else [])
        unique_rows(block,keys,'fuel_prices.csv')
        require(set(e.years).issubset(set(block.year)),f'Missing fuel-price years: {sorted(set(e.years)-set(block.year))}')
        columns=[c for c in block if c not in {'year','period','System','zone'} and not str(c).startswith('Unnamed:')]
        for year,group in block.loc[block.year.isin(e.years)].groupby('year'):
            for column in columns:common_fuel_price(group[column],f'fuel_prices.csv/{column}/{year}')
    check('fuel_prices.csv/selected country-years',prices)
    if e.efuels and 'efuel_inputs' in e.book.sheet_names:
        check(f'{e.workbook}/efuel_inputs',lambda:unique_rows(e.sheet('efuel_inputs'),['fuel'],'efuel_inputs'))
    if 'industry_inv_cost_categories' in e.book.sheet_names:
        def industry_costs():
            table=e.local(e.sheet('industry_inv_cost_categories'))
            if table.empty:return # Native generic per-technology fallback remains available.
            columns=[]
            for year in e.years:
                matches=[c for c in table if str(c) in {str(year),str(float(year))}]
                require(len(matches)==1,f'Missing/ambiguous industry cost year {year}')
                column=matches[0];columns.append(column)
                values=pd.to_numeric(table[column],errors='raise')
                require(np.isfinite(values).all() and values.ge(0).all(),f'Missing/invalid industry cost for {year}')
            unique_rows(table,['System','zone','Industry','category','boiler'],
                'industry_inv_cost_categories',values=columns,allow_identical=True)
        check(f'{e.workbook}/industry_inv_cost_categories',industry_costs)
    if 'DH_loss' in e.policy_book.sheet_names:
        def dh_loss():
            table=pd.read_excel(e.policy_book,'DH_loss')
            require(len(table)==1 and len(table.columns)==1,'DH_loss requires one explicit global scalar')
            value=float(table.iloc[0,0])
            require(np.isfinite(value) and 0<=value<1,'DH_loss must be a fraction from 0 up to (but not including) 1')
        check('policy/DH_loss',dh_loss)
    if model_root:
        model=Path(model_root)
        check(model,lambda:require((model/'data_loaders/load_system.py').is_file(),'Not a refactored model directory'))
        for name in ['pydantic','gurobipy']:
            check('actual-reader dependency/'+name,lambda name=name:require(importlib.util.find_spec(name) is not None,'Install this optional model-reader dependency or omit --model-root'))
    return dict(ready=not errors,phase='refactored input preflight',source_workbook=e.workbook,
        selected_countries=sorted(set(e.countries.values())),zones=sorted(e.countries),years=e.years,
        checks=checks,errors=errors,source_downloads=False,full_calendar_validation='during mapping and final CSV validation')
