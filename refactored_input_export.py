"""Export prepared native inputs as a bus-based H2RES-refactored CSV case.

This is an explicit model adaptation, not an assertion of equivalent equations.
The target installation and its illustrative case are never modified.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from model_input_bundle import selected_workbook
from refactored_input_checks import select_scope,unique_rows,common_fuel_price,year_value,preflight

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/'refactored_reference/contract.json'
SYNTHETIC={'h2','hydrogen','e_kerosene','saf','e_methane','bio_gas','methanol',
           'ethanol','e_diesel','bio_diesel','dme','ammonia','lignin','n2','e_petrol'}
ALIASES={'h2':'hydrogen','nh3':'ammonia','co2':'co2','n2':'nitrogen',
         'fuel_oil':'oil','non_energy_oil':'oil','non_energy_gas':'gas'}

def carrier(value):
    value=str(value).strip().lower()
    return ALIASES.get(value,value)

def number(row,key,default=0.):
    value=row.get(key,default)
    if pd.isna(value) or value=='':
        return float(default)
    value=float(value)
    if not np.isfinite(value):
        raise ValueError(f'Non-finite {key}: {value}')
    return value

def enabled(value):
    return str(value).strip().upper() in {'Y','YES','TRUE','1','1.0'}

def identifier(*parts):
    # Hash only service labels; physical generator names are preserved verbatim.
    raw='__'.join(str(p) for p in parts)
    clean=re.sub(r'[^A-Za-z0-9_.-]+','_',raw)
    return clean if clean==raw else clean+'_'+hashlib.sha256(raw.encode()).hexdigest()[:8]

def hourly(frame,label):
    frame=frame.copy()
    periods=pd.to_numeric(frame['period'],errors='raise')
    if periods.duplicated().any() or set(periods)!=set(range(1,8761)):
        raise ValueError(f'{label}: expected one complete non-leap model calendar (period 1..8760)')
    frame['period']=periods.astype(int)
    frame=frame.sort_values('period').set_index('period')
    values=frame.to_numpy(float)
    if not np.isfinite(values).all() or (values < -1e-8).any():
        raise ValueError(f'{label}: negative or missing hourly values')
    return frame.clip(lower=0)

def residual_electricity(total,baseline,countries):
    """Remove sector energy nationally while retaining sourced regional curves.

    The grid's regional allocation and the separately sourced sector allocation
    are different estimates, often using different years. Subtracting them at
    each region/hour and clipping destroys the grid allocation. Instead retain
    each country's annual residual budget and apply its common residual/gross
    factor to the original regional hourly series. Explicit sector loads enter
    through their own buses; this residual is not an observed local sector split.
    """
    if not total.index.equals(baseline.index) or set(total)!=set(baseline) or set(total)!=set(countries):
        raise ValueError('Grid demand, sector baseline and country map must cover the same regions and periods')
    baseline=baseline[total.columns]
    if any(not np.isfinite(frame.to_numpy(float)).all() or (frame.to_numpy(float)<0).any() for frame in (total,baseline)):
        raise ValueError('Grid demand and sector electricity must be finite and nonnegative')
    changes=int(((total-baseline)<-1e-8).sum().sum())
    residual=total.copy().astype(float)
    for country in sorted(set(countries.values())):
        cols=[z for z,c in countries.items() if c==country]
        gross=float(total[cols].sum().sum())
        annual=gross-float(baseline[cols].sum().sum())
        if annual < -1e-6:
            raise ValueError(f'{country}: annual historical sector electricity exceeds national grid demand; check base years')
        factor=max(0,annual)/gross if gross>0 else 0.
        residual.loc[:,cols]=total[cols]*factor
    return residual,changes

class CaseExporter:
    def __init__(self,bundle,destination,*,efuels=None,industry_mode=None,years=None,electricity_case=None):
        self.bundle=Path(bundle).resolve()
        self.data=self.bundle/'data'
        self.destination=Path(destination)
        self.metadata=json.loads((self.bundle/'bundle_manifest.json').read_text(encoding='utf-8'))
        self.scenario=json.loads((self.bundle/'scenario.json').read_text(encoding='utf-8')) if (self.bundle/'scenario.json').exists() else {}
        if self.scenario.get('preset')=='res100' and self.scenario.get('scope')=='all-energy':
            raise ValueError('The refactored export needs a reference/electricity scenario: its prescribed baseline fleet cannot enforce the legacy whole-energy RES preset')
        self.efuels=self.metadata['efuels'] if efuels is None else efuels
        self.mode=industry_mode or self.metadata['industry_mode']
        self.electricity_case=electricity_case or self.metadata.get('industry_electricity_case','conservative')
        self.years=years or self.scenario.get('years') or [2025,2030,2035,2040,2045,2050]
        if not self.years or self.years!=sorted(set(self.years)) or any(int(y)!=y or y<1900 for y in self.years):
            raise ValueError('Refactored export years must be unique increasing integer years')
        # Complex process equations have no counterpart. Use the generated category
        # energy services, and record the adaptation rather than dropping industry.
        self.service_mode='categories' if self.mode=='complex' else self.mode
        self.workbook=selected_workbook(self.efuels,self.service_mode,self.electricity_case)
        self.book=pd.ExcelFile(self.data/self.workbook)
        self.cache={}
        active=self.sheet('active_zones')
        active=active.loc[active.active.map(enabled)]
        self.pairs=set(active[['System','zone']].itertuples(index=False,name=None))
        self.countries={z:c for c,z in sorted(self.pairs)}
        if len(self.countries)!=len(self.pairs) or not self.pairs:
            raise ValueError('Active zone IDs must be nonempty and unique across countries')
        coverage_path=self.bundle/'validation.json'
        if not coverage_path.is_file():raise ValueError('Convert a completed native bundle with validation.json first')
        coverage=json.loads(coverage_path.read_text(encoding='utf-8'))
        if not coverage.get('ready') or set(coverage.get('active_zones',[]))!=set(self.countries):
            raise ValueError('Source workbook geography differs from the completed native bundle; regenerate all native variants before converting another representation')
        verified=[coverage,*coverage.get('variants',[])]
        if not any(v.get('ready') and v.get('technology_workbook')==self.workbook for v in verified):
            raise ValueError(f'{self.workbook} is not a validated generated variant; enable all native variants before converting this representation')
        self.buses={}
        self.plants=[]; self.heaters=[]; self.efuel=[]; self.stores=[]; self.hstores=[];self.fstores=[]
        self.costs=[];self.links=[];self.lines=[];self.trade=[];self.fleets=[];self.pathway=[]
        self.heat={};self.edemand={};self.mobility={};self.connection={};self.efficiencies={}
        self.profile={};self.inflows={}
        self.used_fuels=set();self.unit_links=[];self.source_files={}
        self.audit={'format':'H2RES-refactored','adaptation':'native energy services and exogenous transport pathway',
                    'years':self.years,'industry_requested':self.mode,'industry_services':self.service_mode,
                    'efuels':self.efuels,'source_workbook':self.workbook,'assumptions':[],
                    'differences':[
                        'Transport fleet numbers and activity shares are exogenous; baseline mix held constant unless pathway.csv is edited.',
                        'Industrial energy services use heat-carrier buses (including NON_HEAT process service proxies); no material/product/process constraints.',
                        'Annual build limits, fuel substitution/share limits, retrofit coupling, reserves, fixed OPEX and carbon-capture process constraints have no direct mapping.',
                        'Capacity ceilings are retained; max_cap below installed capacity means no expansion, never removal of existing stock.',
                        'Reference national demand and cost trajectories are applied; historical hourly weather/activity patterns repeat across milestone years.',
                        'External electricity trade is not represented: the target reader/model exposes only internal electricity corridors.',
                        'Legacy retirement ages are retained, but the refactored model uses its own retirement equations.',
                        'Policy is system-wide in the target; country caps are summed and differing country RES targets use their maximum.',
                    ]}
        self.cost_table=self.sheet('tech_cost_years')
        self.cost_curves={}
        self.industry_cost_rows=None
        self.fuel_prices=pd.read_csv(self.data/'fuel_prices.csv')
        self.product_prices=pd.read_excel(self.data/'policy_fuels.xlsx','import')
        self.policy_book=pd.ExcelFile(self.data/('policy_efuel.xlsx' if self.efuels else 'policy.xlsx'))

    def close(self):
        self.book.close();self.policy_book.close()

    def sheet(self,name):
        if name not in self.cache:
            self.cache[name]=pd.read_excel(self.book,name)
        return self.cache[name].copy()

    def local(self,frame):
        return frame.loc[[tuple(x) in self.pairs for x in frame[['System','zone']].itertuples(index=False,name=None)]].copy()

    def bus(self,zone,kind,service=None,loss=0):
        name=identifier(self.countries[zone],zone,kind,service) if service else identifier(self.countries[zone],zone,kind)
        row=dict(system=self.countries[zone],region=zone,bus=name,carrier=kind,
                 distribution_loss=loss,voll_heat=3000 if kind=='heat' else '')
        if name in self.buses and self.buses[name]!=row:
            raise ValueError(f'Conflicting bus metadata for {name}')
        self.buses[name]=row
        return name

    def trajectory(self,key,zone,*,industry=None,category=None):
        cache_key=(key,zone,industry,category)
        if cache_key in self.cost_curves:return self.cost_curves[cache_key].copy()
        table=self.cost_table
        if industry is not None and 'industry_inv_cost_categories' in self.book.sheet_names:
            if self.industry_cost_rows is None:
                t=self.local(self.sheet('industry_inv_cost_categories'))
                self.industry_cost_rows={}
                for row in t.to_dict('records'):
                    k=(row['boiler'],row['zone'],row['Industry'],row['category'])
                    if k in self.industry_cost_rows:
                        old=self.industry_cost_rows[k]
                        columns=[c for c in row if str(c).replace('.0','').isdigit()]
                        if any(not np.isclose(float(row[c]),float(old[c]),equal_nan=True) for c in columns):
                            raise ValueError(f'Conflicting industry cost key {k}')
                        continue
                    self.industry_cost_rows[k]=row
            row=self.industry_cost_rows.get(cache_key)
            if row is not None:
                result={}
                for y in self.years:
                    column=y if y in row else str(y)
                    if column not in row or pd.isna(row[column]):raise ValueError(f'Missing industry cost for {key}/{zone}/{y}')
                    value=number(row,column)
                    if value<0:raise ValueError(f'Invalid industry investment cost {key}/{zone}/{y}: negative value')
                    result[y]=value*1e6
                self.cost_curves[cache_key]=result
                return result
        # A year occurs once per country in native cost sheets. Country-wide
        # sheets may have no zone column at all; select System before testing
        # year uniqueness so foreign reference rows do not create ambiguity.
        table=select_scope(table,system=self.countries[zone] if 'System' in table else None,zone=zone)
        if key not in table:
            aliases={'fuel_oil_DH':'Oil_DH'}
            wanted=aliases.get(key,key)
            equivalent=[c for c in table if str(c).casefold()==str(wanted).casefold()]
            if len(equivalent)==1:
                donor=equivalent[0]
                self.audit.setdefault('cost_column_aliases',{})[key]=str(donor)
                key=donor
        if key not in table or table.empty:
            raise ValueError(f'Missing native investment cost trajectory for {key}/{zone}')
        if table.year.duplicated().any():
            raise ValueError(f'Ambiguous cost trajectory {key}/{zone}')
        lookup=table.set_index('year')[key]
        result={}
        for y in self.years:
            if y not in lookup or pd.isna(lookup.loc[y]):
                raise ValueError(f'Missing native investment cost {key}/{zone}/{y}')
            value=float(lookup.loc[y])
            if not np.isfinite(value) or value<0:raise ValueError(f'Invalid native investment cost {key}/{zone}/{y}: expected a finite nonnegative value')
            result[y]=value*1e6
        self.cost_curves[cache_key]=result
        return result

    def cost(self,unit,key,zone,field='capital_cost',**kwargs):
        values=self.trajectory(key,zone,**kwargs)
        self.costs.extend(dict(year=y,unit=unit,field=field,capital_cost=v) for y,v in values.items())
        return values[self.years[0]]

    def price(self,fuel,year):
        key=carrier(fuel)
        choices=[c for c in self.fuel_prices if carrier(c)==key]
        if not choices:
            table=self.product_prices
            rows=table.loc[table['product'].map(carrier).eq(key)&table.System.isin(set(self.countries.values()))]
            exact=rows.loc[rows.zone.isin(self.countries)]
            if not exact.empty:rows=exact
            column=year if year in rows else str(year)
            if rows.empty or column not in rows:raise ValueError(f'No native price for {fuel}/{year}')
            values=pd.to_numeric(rows[column],errors='raise')
            return common_fuel_price(values,f'policy_fuels/import/{fuel}/{year}')
        frame=self.fuel_prices
        if 'System' in frame:frame=frame.loc[frame.System.isin(set(self.countries.values()))]
        if year not in set(frame.year):
            raise ValueError(f'Missing fuel price year {year}')
        values=pd.to_numeric(frame.loc[frame.year.eq(year),choices[0]],errors='raise')
        return common_fuel_price(values,f'fuel_prices/{fuel}/{year}')

    def unit(self,row,name,tech,bus_out,*,fuel=None,efficiency=None,cost_key=None,industry=None,category=None):
        zone=str(row.get('zone',row.get('Zone')))
        fuel=carrier(fuel if fuel is not None else row.get('fuel_type','electricity'))
        self.used_fuels.add(fuel)
        eff=number(row,'efficiency',1) if efficiency is None else float(efficiency)
        if eff<=0:
            raise ValueError(f'Invalid efficiency for {name}')
        cap=number(row,'cap_mw')
        maximum=max(cap,number(row,'max_cap',cap))
        out=dict(system=self.countries[zone],region=zone,name=name,tech=tech,fuel=fuel,unit_type='supply',
            carrier_in='',bus_in='',carrier_out=self.buses[bus_out]['carrier'],bus_out=bus_out,
            p_nom=cap,p_nom_max=maximum,cap_factor=1,
            capital_cost=self.cost(name,cost_key or str(row['unit_name']),zone,industry=industry,category=category),
            lifetime=number(row,'life_time',25),decom_start_existing=number(row,'decom_start_existing_cap',20),
            decom_start_new=number(row,'decom_start_new',20),final_cap=number(row,'final_life_cap',0.1),
            efficiency=eff,co2_intensity=number(row,'CO2Intensity'),
            var_cost_no_fuel=number(row,'cost_no_fuel',number(row,'var_cost')),ramp_up_rate=number(row,'RampUpRate',1),
            ramp_down_rate=number(row,'RampDownRate',1),ramping_cost=number(row,'RampingCost'))
        self.unit_links.append(dict(name=name,source_sheet='Industry_data' if industry else 'native technology',source_unit=str(row['unit_name']),zone=zone,output_bus=bus_out))
        return out

    def series(self,filename):
        path=self.data/filename
        self.source_files[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
        return pd.read_csv(path)

    def long_profiles(self,filename):
        data=self.series(filename)
        return {z:hourly(block.drop(columns=['zone','System']),filename+'/'+z) for z,block in data.groupby('zone') if z in self.countries}

    def build_power(self):
        generators=self.series('generators.csv')
        renewable=hourly(self.series('renewable_availability.csv'),'renewable_availability')
        inflows=hourly(self.series('hydro_inflows.csv'),'hydro_inflows')
        for r in generators.to_dict('records'):
            zone=r['Zone'];r['zone']=zone
            if (r['System'],zone) not in self.pairs:continue
            name=r['unit_name'];tech=str(r['technology']);chp=str(r.get('CHPType','N')).lower()
            is_chp=chp not in {'n','nan','none',''}
            if is_chp:tech+='CHP'
            u=self.unit(r,name,tech,self.bus(zone,'electricity'))
            if is_chp:
                u.update(chp_type='extraction' if number(r,'CHPPowerLossFactor')>0 else 'backpressure',
                    chp_power_to_heat=number(r,'CHPPowerToHeat'),chp_power_loss_factor=number(r,'CHPPowerLossFactor'),
                    chp_max_heat=number(r,'CHPMaxHeat'),carrier_out_2='heat',bus_out_2=self.bus(zone,'heat','DH',loss=self.dh_loss))
            if tech in {'HDAM','HPHS'}:
                u.update(e_nom=number(r,'STOCapacityGWh')*1000,e_nom_max=number(r,'STOCapacityGWh')*1000,
                    e_nom_lower=0,e_min=0,capital_cost_energy=0,p_charge_nom=number(r,'STOMaxChargingPower'),
                    efficiency_charge=number(r,'STOChargingEfficiency',1),efficiency_discharge=1,
                    standby_loss=number(r,'STOSelfDischarge'),spillage_cost=0)
                if name not in inflows:raise ValueError(f'Missing reservoir inflow for {name}')
                self.inflows[name]=inflows[name]
            if tech=='HROR' or u['fuel'] in {'solar','wind'}:
                if name not in renewable:raise ValueError(f'Missing renewable profile for {name}')
                self.profile[name]=renewable[name]
            self.plants.append(u)

    def demand_multiplier(self,sheet,zone,year):
        cache_key='policy:'+sheet
        if cache_key not in self.cache:self.cache[cache_key]=pd.read_excel(self.policy_book,sheet)
        table=self.cache[cache_key]
        table=select_scope(table,system=self.countries[zone],zone=zone)
        if len(table)!=1:raise ValueError(f'Missing/ambiguous {sheet} for {zone}')
        row=table.iloc[0]
        return year_value(row,year,f'{sheet}/{self.countries[zone]}/{zone}')

    def efficiency_profile(self,key,zone):
        cache_key=('COP',zone,key)
        if cache_key not in self.cache:
            scope_key=('COP samples',zone)
            if scope_key not in self.cache:
                self.cache[scope_key]=select_scope(self.sheet('COP_HP'),system=self.countries[zone],zone=zone).copy()
            samples=self.cache[scope_key]
            if samples.empty or key not in samples:raise ValueError(f'Missing COP data {key}/{zone}')
            samples=unique_rows(samples,['period'],f'COP_HP/{self.countries[zone]}/{zone}/{key}',values=[key],allow_identical=True)
            profile=hourly(samples[['period',key]],f'COP {key}/{zone}')[key]
            if profile.le(0).any():raise ValueError(f'COP must be strictly positive: {key}/{zone}')
            self.cache[cache_key]=profile
        return self.cache[cache_key].copy()

    def build_heating(self):
        # Separate networks preserve district losses and prevent CHP supplying
        # individual boilers' demand without a physical heat network.
        for kind,filename,loss in [('INDV','heating_individual.csv',0),('DH','heating_district.csv',self.dh_loss)]:
            demands=hourly(self.series(filename),filename)
            for zone in self.countries:
                bus=self.bus(zone,'heat',kind,loss=loss)
                self.heat[bus]=(demands[zone],zone,'Heat_dem_change_DH' if kind=='DH' else 'Heat_dem_change')
            for sheet in (('thermal_tech_DH','flex_tech_DH') if kind=='DH' else ('thermal_tech','flex_tech_heat')):
                for r in self.local(self.sheet(sheet)).to_dict('records'):
                    zone=r['zone'];key=r['unit_name'];name=identifier(self.countries[zone],zone,kind,key)
                    electric=sheet.startswith('flex_tech')
                    fuel='electricity' if electric else r['fuel_type']
                    if electric:
                        eff=self.efficiency_profile(key,zone)
                    else:eff=None
                    u=self.unit(r,name,key,self.bus(zone,'heat',kind,loss=loss),fuel=fuel,efficiency=float(eff.mean()) if eff is not None else None)
                    if electric:
                        u.update(unit_type='conversion',carrier_in='electricity',bus_in=self.bus(zone,'electricity'))
                        self.efficiencies[name]=eff
                    else:u['co2_intensity']/=u['efficiency'] # native boiler intensity is per fuel input
                    self.heaters.append(u)
            for r in self.local(self.sheet('solar_DH' if kind=='DH' else 'solar_indv')).to_dict('records'):
                zone=r['zone'];name=identifier(self.countries[zone],zone,kind,'SolarThermal')
                # The heat equations ignore p_t; availability.csv is also power-
                # only. A solar heat converter would become unconstrained.
                # Keep its stock/cost in the audit, and prevent this unsupported
                # resource option from entering the equations.
                self.audit.setdefault('unmapped_solar_heat',[]).append(dict(zone=zone,network=kind,existing_MW=number(r,'cap_mw')))
        self.audit['differences'].append('Solar-thermal hourly availability has no binding input in the target heat equations; solar heat is listed as unmapped rather than given unlimited output.')

    def build_industry(self):
        profiles=self.long_profiles('industry_category_profiles.csv' if self.service_mode=='categories' else 'industry_heat.csv')
        main=self.local(self.sheet('Industry_data'))
        if 'category' not in main:main['category']='all'
        groups=['System','zone','Industry','category']
        selected=set(main.loc[main.include_in_the_model.map(enabled),groups].itertuples(index=False,name=None))
        sums=defaultdict(lambda:pd.Series(0.,index=range(1,8761)))
        source_total=0.;service_total=0.
        for keys,block in main.groupby(groups,sort=False):
            system,zone,industry,category=keys
            column=f'{industry}[{category}]' if self.service_mode=='categories' else industry
            demand=profiles[zone][column]
            source_total+=float(demand.sum())
            service=identifier('industry',industry,category) if keys in selected else 'industry_remainder'
            bus=self.bus(zone,'heat',service)
            sums[(bus,zone)]+=demand
            if keys not in selected:continue
            for r in block.loc[block.include_in_the_model.map(enabled)].to_dict('records'):
                self.industry_unit(r,bus,industry,category)
        simple=self.local(self.sheet('simple_industry'))
        for r in simple.to_dict('records'):
            bus=self.bus(r['zone'],'heat','industry_remainder')
            if (bus,r['zone']) in sums:self.industry_unit(r,bus,None,None)
        for (bus,zone),demand in sums.items():
            self.heat[bus]=(demand,zone,'Industry_dem_change')
            service_total+=float(demand.sum())
        if not np.isclose(source_total,service_total,rtol=1e-10,atol=1e-5):raise ValueError('Industrial service pooling lost or duplicated demand')
        self.audit['industry_service_MWh']=dict(source=source_total,exported=service_total)

    def industry_unit(self,r,bus,industry,category):
        zone=r['zone'];fuel=carrier(r['fuel_type']);share=number(r,'max_share_fuel',1)
        if share<=0 and number(r,'cap_mw')<=0:return
        # Feedstock alternatives are kept distinct from combustion and recorded
        # as service conversion proxies; there are no material equations here.
        name=identifier(bus,r['unit_name'])
        if fuel=='heat':
            # Purchased heat: explicit reference gas-backed steam assumption.
            fuel='gas';r=dict(r,efficiency=.9,CO2Intensity=.2)
        u=self.unit(r,name,r['unit_name'],bus,fuel=fuel,industry=industry,category=category)
        if fuel=='electricity' or (self.efuels and (str(r['fuel_type']).lower() in SYNTHETIC)):
            u.update(unit_type='conversion',carrier_in=fuel,bus_in=self.bus(zone,fuel))
            u['co2_intensity']=0
        else:u['co2_intensity']/=u['efficiency']
        u['source_max_share_fuel']=share
        u['source_service_category']=category or 'pooled'
        u['unit_note']='Industrial useful-service proxy; source fuel-share restrictions are not enforced by target.'
        if str(r['fuel_type']).startswith('non_energy_'):
            u['co2_intensity']=0
            u['unit_note']='Non-energy feedstock energy-service proxy; no combustion emissions or material/stoichiometric equations.'
        self.heaters.append(u)

    def build_transport(self):
        table=self.local(self.sheet('transport_all'))
        table=table.loc[table.include_in_the_model.map(enabled)]
        profiles=self.long_profiles('transport_demand.csv')
        connection=self.long_profiles('transport_profiles.csv')
        if 'transport_ICE_prim' in self.book.sheet_names:
            fuels=self.sheet('transport_ICE_prim')
        else:
            # The legacy non-eFuel workbook has no primary-fuel table. Use
            # the generated eFuel counterpart's observed baseline mixture
            # if it covers these regions, without enabling e-fuel synthesis.
            companion=self.data/selected_workbook(True,self.service_mode,self.electricity_case)
            fuels=pd.read_excel(companion,'transport_ICE_prim') if companion.is_file() else pd.DataFrame()
            self.audit['assumptions'].append('Non-eFuel transport reads baseline fuel mixtures from the generated eFuel counterpart when available; otherwise the native Oil fuel-price/row-emission proxy is explicit.')
            if companion.is_file():self.source_files[companion.name]=hashlib.sha256(companion.read_bytes()).hexdigest()
        for (system,zone,sector),block in table.groupby(['System','zone','sector'],sort=False):
            totals=pd.to_numeric(block.total_load,errors='raise')
            if not np.allclose(totals,totals.iloc[0]):raise ValueError(f'Conflicting activity totals for {zone}/{sector}')
            annual=float(totals.iloc[0])*1e6
            if annual<=0:continue
            mode=identifier(system,zone,sector)
            shape=profiles[zone][sector]
            if not np.isclose(shape.sum(),1,rtol=1e-5):raise ValueError(f'Unnormalised transport activity {zone}/{sector}')
            self.mobility[mode]=shape*annual
            existing=block.loc[pd.to_numeric(block.number,errors='raise').gt(0)].copy()
            # Shipping tables may have no vehicle counts. In that case a
            # conventional non-retrofit ICE fleet serves the observed service.
            no_counts=existing.empty
            if no_counts:
                existing=block.loc[block.type.eq('ICE')&~block.unit_name.str.startswith('RETROFIT')].head(1)
                if existing.empty:raise ValueError(f'No baseline fleet evidence or explicit ICE option for {zone}/{sector}')
            total_numbers=float(existing.number.sum())
            for r in existing.to_dict('records'):
                unit=r['unit_name'];name=identifier(system,zone,unit)
                eff=number(r,'efficiency_primary')*1000 # passenger/tonne-km per kWh -> activity/MWh
                if eff<=0:raise ValueError(f'Invalid transport efficiency {name}')
                typ=r['type'];is_el=typ in {'BAT','EL','PHEV'}
                is_h2=typ=='FCEV'
                primary=fuels.loc[fuels.zone.eq(zone)&fuels.sector_prim.eq(unit)] if {'zone','sector_prim'}.issubset(fuels) else pd.DataFrame()
                if primary.empty and not self.efuels and not is_el and not is_h2:
                    primary=pd.DataFrame([dict(fuel_prim='Oil',share2020prim=1.,CO2prim=number(r,'CO2'))])
                    self.audit.setdefault('transport_fuel_price_proxies',[]).append(dict(zone=zone,unit=unit,fuel='Oil',basis='native non-eFuel generic liquid-fuel price; emission intensity from technology row'))
                weights=pd.to_numeric(primary.get('share2020prim',pd.Series(dtype=float)),errors='raise')
                if not is_el and not is_h2 and (primary.empty or not np.isclose(weights.sum(),1,atol=1e-5)):
                    raise ValueError(f'Missing baseline fuel mix for transport {name}')
                fuel='electricity' if is_el else 'hydrogen' if is_h2 else 'baseline_blend'
                blend={str(row.fuel_prim):float(row.share2020prim) for row in primary.itertuples() if row.share2020prim>0}
                price=sum(w*self.price(f,self.years[0]) for f,w in blend.items()) if not is_el and not is_h2 else 0
                co2=sum(float(row.share2020prim)*float(row.CO2prim) for row in primary.itertuples()) if not is_el and not is_h2 else 0
                count=number(r,'number');share=count/total_numbers if total_numbers else 1.
                if is_h2 and not self.efuels:
                    fuel='hydrogen';price=self.price(fuel,self.years[0])
                coupled=is_el or (is_h2 and self.efuels)
                battery=number(r,'average_stor')/1000 if typ in {'BAT','PHEV'} else 0
                charging='v1g' if battery>0 else 'dumb' if is_el else 'none'
                self.fleets.append(dict(name=name,mode=mode,tech=unit,carrier_in=fuel if coupled else '',
                    bus_in=self.bus(zone,fuel) if coupled else '',fuel=fuel,efficiency=eff,
                    co2_per_activity=co2/eff,fuel_cost=price,var_cost=0,capital_cost=0,lifetime=number(r,'life_time',15),
                    charging_mode=charging,battery_energy=battery,charge_power=number(r,'average_ch_rate')/1000 if battery else 0,
                    discharge_power=0,eta_charge=number(r,'EV_grid_eff',1),eta_discharge=1,standby_loss=0,
                    soc_min=0,v2g_share=0,charge_cost=0,source_fuel_blend=json.dumps(blend),
                    source_units='passenger-km or tonne-km; baseline vehicle-count shares',system=system,region=zone))
                for year in self.years:self.pathway.append(dict(year=year,fleet=name,fleet_units=count,activity_share=share))
                if is_el:self.connection[name]=connection[zone][unit]
                if no_counts:self.audit.setdefault('shipping_without_vehicle_counts',[]).append(name)
        self.audit['transport_activity_by_mode']={k:float(v.sum()) for k,v in self.mobility.items()}
        self.audit['assumptions'].append('Transport baseline activity split follows vehicle counts within each local mode; where JRC shipping has no counts, the original ICE service is retained with zero vehicle stock. Costs are baseline blended fuel prices, fixed at the first exported year; no unsourced vehicle purchase or nonfuel operating cost is invented.')

    def build_electricity_demand(self):
        data=self.series('electricity_demand.csv')
        if data.duplicated(['period','Zone']).any():raise ValueError('Duplicate regional electricity demand')
        total=hourly(data.pivot(index='period',columns='Zone',values='Power').reset_index(),'electricity demand')
        total=total[list(self.countries)]
        baseline=pd.DataFrame(0.,index=total.index,columns=total.columns)
        # Grid demand already includes historical industry/heating electricity.
        # Their services are represented explicitly in the new coupled case.
        for file in ['industry_electricity.csv','heating_electricity.csv']:
            observed=hourly(self.series(file),file)
            baseline+=observed[baseline.columns]
        # Existing electric mobility also sits inside the grid observation.
        for f in self.fleets:
            if f['carrier_in']=='electricity':
                share=next(p['activity_share'] for p in self.pathway if p['fleet']==f['name'])
                baseline[f['region']]+=self.mobility[f['mode']]*share/f['efficiency']/f['eta_charge']
        residual,changes=residual_electricity(total,baseline,self.countries)
        self.electricity=residual.rename(columns={z:self.bus(z,'electricity') for z in self.countries})
        country_accounting={}
        for c in sorted(set(self.countries.values())):
            cols=[z for z,v in self.countries.items() if v==c]
            gross=float(total[cols].sum().sum());remaining=float(residual[cols].sum().sum())
            country_accounting[c]=dict(grid_MWh=gross,removed_sector_MWh=float(baseline[cols].sum().sum()),
                residual_MWh=remaining,residual_fraction=remaining/gross if gross else 0.)
        regional_accounting={}
        for z in self.countries:
            bus=self.bus(z,'electricity')
            per_year={y:float(residual[z].sum())*self.demand_multiplier('dem_change',z,y) for y in self.years}
            zero_hours={y:8760 if self.demand_multiplier('dem_change',z,y)==0 else int(residual[z].eq(0).sum()) for y in self.years}
            regional_accounting[bus]=dict(region=z,system=self.countries[z],grid_MWh=float(total[z].sum()),
                residual_base_MWh=float(residual[z].sum()),source_zero_hours=int(total[z].eq(0).sum()),
                exported_MWh_by_year=per_year,exported_zero_hours_by_year=zero_hours)
        self.audit['electricity_accounting_MWh']=dict(grid=float(total.sum().sum()),
            removed_historical_sector_electricity=float(baseline.sum().sum()),residual=float(residual.sum().sum()),
            method_id='national_sector_removal_preserve_regional_curves_v2',
            distribution_source='Existing native electricity_demand.csv: ENTSO-E national hourly curve allocated using normalized JRC EIGL regional electricity totals; custom zones retain their prepared aggregation.',
            regional_negative_hours_avoided=changes,
            method='Remove historical industry/heating and baseline electric mobility from each national annual grid budget; multiply all original regional hourly grid curves by the same national residual/gross factor. Preserve base regional shares, each normalized hourly profile, and true source zero hours. Apply declared zone/year demand multipliers afterward. This is an annual residual-demand allocation assumption, not an observed regional sector split or an exact gross hourly reconstruction.',
            countries=country_accounting,regions=regional_accounting,
            national_negative_hours_before_reconciliation={c:int(((total-baseline)[[z for z,v in self.countries.items() if v==c]].sum(axis=1)<0).sum()) for c in set(self.countries.values())})

    def build_network(self):
        from regional_network_inputs import blocks
        frame=self.sheet('transmission')
        if 'unit_name' in frame:
            base={k:k for k in ['zone','zoneTo','System','To','km'] if k in frame}
            records=[(r,{str(r['unit_name']):{c:c for c in frame if c not in base and c!='unit_name'}}) for r in frame.to_dict('records')]
        else:
            base,units=blocks(frame)
            records=[(r,units) for r in frame.iloc[1:].to_dict('records')]
        allowed={'400kV_AC','HVDC'}
        if 'imp_exp' in self.book.sheet_names:
            flags=self.sheet('imp_exp')
            allowed &= set(flags.loc[flags.use.map(enabled),'fuel'])
        seen={}
        for row,units in records:
            a=str(row[base['zone']]);b=str(row[base['zoneTo']])
            if a not in self.countries or b not in self.countries or a==b:continue
            for tech,fields in units.items():
                if tech not in allowed:continue
                key=(min(a,b),max(a,b),tech)
                values={field:number(row,col) for field,col in fields.items()}
                if values.get('cap_mw',0)<=0 and values.get('max_cap',0)<=0:continue
                loss=values.get('loss',0)*number(row,base.get('km',''),0)
                if not 0<=loss<1:raise ValueError(f'Invalid network loss {a}/{b}')
                if key in seen:
                    previous=seen[key]
                    cap=values.get('cap_mw',0)
                    if previous['p_nom']!=cap or previous['efficiency']!=1-loss:
                        self.audit.setdefault('asymmetric_corridor_adaptations',[]).append(dict(zones=[a,b],tech=tech,
                            method='use the smaller directional capacity and lower delivery efficiency on the shared bidirectional target corridor'))
                    previous['p_nom']=previous['p_nom_max']=min(previous['p_nom'],cap)
                    previous['efficiency']=min(previous['efficiency'],1-loss)
                    continue
                # Retain fixed native physical/virtual capacities. The target
                # corridor has one shared bidirectional expansion variable.
                self.lines.append(dict(line=identifier(a,b,tech),from_bus=self.bus(a,'electricity'),to_bus=self.bus(b,'electricity'),
                    p_nom=values.get('cap_mw',0),p_nom_max=values.get('cap_mw',0),capital_cost=0,
                    lifetime=values.get('life_time',40),efficiency=1-loss,unit_note='Native paired directions represented once; expansion frozen because directional investment constraints differ.'))
                seen[key]=self.lines[-1]

    def build_flex_and_efuel(self):
        flex=self.local(self.sheet('flex_tech'))
        for r in flex.to_dict('records'):
            zone=r['zone'];key=r['unit_name'];name=identifier(self.countries[zone],zone,key)
            if key=='Liion_storage':
                # Native stationary storage stock is MWh and stor_ratio is MW/MWh.
                ratio=number(r,'stor_ratio')
                if ratio<=0:raise ValueError(f'Invalid stationary-storage ratio {zone}/{key}')
                eff=number(r,'efficiency',1)
                energy=number(r,'cap_mw');maximum=max(energy,number(r,'max_cap',energy))
                bus=self.bus(zone,'electricity')
                self.stores.append(dict(system=self.countries[zone],region=zone,name=name,tech=key,
                    carrier_in='electricity',carrier_out='electricity',bus_in=bus,bus_out=bus,
                    e_nom=energy,e_nom_max=maximum,e_min=0,duration_charge=1/ratio,duration_discharge=1/ratio,
                    efficiency_charge=eff**.5,efficiency_discharge=eff**.5,standby_loss=0,
                    capital_cost_energy=self.cost(name,key,zone,field='capital_cost_energy'),
                    capital_cost_power_charge=0,capital_cost_power_discharge=0,lifetime=number(r,'life_time',15),spillage_cost=0,
                    decom_start_existing=number(r,'decom_start_existing_cap',5),decom_start_new=number(r,'decom_start_new',10),final_cap=number(r,'final_life_cap',.1)))
            if not self.efuels:continue
            if key not in {'PEM_elec','SOEC_elec','Alkaline_EC','DAC'}:continue
            # Native electrolysis is rated on input MW; target rating is output MW.
            eff=number(r,'efficiency',1)
            output='co2' if key=='DAC' else 'hydrogen'
            factor=1/eff if key=='DAC' else eff
            ratio=eff if key=='DAC' else 1/eff
            costs=self.trajectory(key,zone)
            self.efuel.append(dict(system=self.countries[zone],region=zone,name=name,tech=key,unit_type='conversion',
                carrier_out=output,bus_out=self.bus(zone,output),carrier_in_1='electricity',bus_in_1=self.bus(zone,'electricity'),
                rate_carrier_in_1=ratio,rate_carrier_out=1,p_nom=number(r,'cap_mw')*factor,
                p_nom_max=max(number(r,'cap_mw'),number(r,'max_cap'))*factor,cap_factor=1,
                capital_cost=costs[self.years[0]]/factor,lifetime=number(r,'life_time',20),
                decom_start_existing=number(r,'decom_start_existing_cap',10),decom_start_new=number(r,'decom_start_new',15),
                final_cap=number(r,'final_life_cap',.1),var_cost_no_fuel=number(r,'var_cost')/factor,co2_intensity=0,
                ramp_up_rate=1,ramp_down_rate=1))
            self.costs.extend(dict(year=y,unit=name,field='capital_cost',capital_cost=v/factor) for y,v in costs.items())
        self.audit['assumptions'].append('Stationary battery stock/cost uses native MWh stock and MW/MWh ratio; native round-trip efficiency is split symmetrically. Electrolyser input ratings and capex are converted to output ratings. DAC uses native electricity-per-tonne intensity; CO2 and nitrogen buses use tonnes/hour and tonne storage despite generic target MW/MWh field names.')
        if not self.efuels:return
        inputs=unique_rows(self.sheet('efuel_inputs'),['fuel'],'efuel_inputs').set_index('fuel')
        for r in self.local(self.sheet('efuel')).to_dict('records'):
            if not enabled(r.get('use','Y')):continue
            key=r['unit_name'];zone=r['zone'];name=identifier(self.countries[zone],zone,r['unit_name_gen'])
            if key not in inputs.index:raise ValueError(f'No native e-fuel recipe for {key}')
            recipe=inputs.loc[key]
            out=carrier(key)
            u=dict(system=self.countries[zone],region=zone,name=name,tech=r['unit_name_gen'],unit_type='conversion',
                carrier_out=out,bus_out=self.bus(zone,out),rate_carrier_out=1,p_nom=number(r,'cap_mw'),
                p_nom_max=max(number(r,'cap_mw'),number(r,'max_cap')),cap_factor=1,
                capital_cost=self.cost(name,r['unit_name_gen'],zone),lifetime=number(r,'life_time',20),
                decom_start_existing=number(r,'decom_start_existing_cap',15),decom_start_new=number(r,'decom_start_new',15),
                final_cap=number(r,'final_life_cap',.1),var_cost_no_fuel=0,co2_intensity=0,
                ramp_up_rate=number(r,'ramp_up',1),ramp_down_rate=number(r,'ramp_down',1))
            for i in range(1,4):
                ratio=number(recipe,f'dem_input{i}')
                if ratio<=0:continue
                input_carrier=carrier(recipe[f'input{i}'])
                u.update({f'carrier_in_{i}':input_carrier,f'bus_in_{i}':self.bus(zone,input_carrier),f'rate_carrier_in_{i}':ratio})
            self.efuel.append(u)
        for r in self.local(self.sheet('fuel_storage')).to_dict('records'):
            zone=r['zone'];c=carrier(r['unit_name'])
            # Only stores for carriers participating in the endogenous network.
            bus=identifier(self.countries[zone],zone,c)
            if bus not in self.buses:continue
            key=r['unit_name_stor'];name=identifier(self.countries[zone],zone,key)
            e=number(r,'stor_cap_TWh')*1e6;maximum=max(e,number(r,'max_cap')*1e6)
            # Native fuel-storage investment is already in MWh; its price
            # trajectory is MEUR/MWh, independently of the TWh stock column.
            donor=key if key in self.cost_table else {'N2_stor':'Gas_stor'}.get(key,key)
            if donor!=key:self.audit['assumptions'].append(f'{zone}/{key}: explicit Gas_stor storage-cost proxy, matching native model policy; dedicated price column missing.')
            costs=self.trajectory(donor,zone)
            self.fstores.append(dict(name=name,carrier=c,tech=key,bus=bus,e_nom=e,e_nom_max=maximum,
                p_charge_nom=maximum,p_discharge_nom=maximum,efficiency_charge=number(r,'efficiency',1),
                efficiency_discharge=1,standby_loss=0,capital_cost_energy=costs[self.years[0]],
                lifetime=number(r,'life_time',50),assumption_note='Native TWh stock -> MWh; no supplied power limit, one-hour maximum-energy turnover assumption.'))
            self.costs.extend(dict(year=y,unit=name,field='capital_cost_energy',capital_cost=v) for y,v in costs.items())
        # Biomass input to synthesis needs a priced physical source. A route's
        # annual capacity is capped by the native national biomass envelope,
        # shared across the zones using prepared electricity-demand shares.
        biomass=pd.read_excel(self.policy_book,'biomass_caps')
        grid=self.series('electricity_demand.csv').groupby('Zone').Power.sum()
        for country in set(self.countries.values()):
            zones=[z for z,c in self.countries.items() if c==country]
            rows=biomass.loc[biomass.System.eq(country)]
            col=next((c for c in ['Cap_TWh','Supply_cap_TWh','Max_supply_TWh','cap_TWh','Max_TWh'] if c in rows),None)
            # Versioned reference schema is captured in the report; missing
            # envelopes fail rather than give biofuels an unlimited free source.
            if col is None:raise ValueError('Cannot locate native biomass supply ceiling in biomass_caps')
            ceiling=float(pd.to_numeric(rows[col],errors='raise').min())
            for z in zones:
                bus=identifier(country,z,'biomass')
                if bus not in self.buses:continue
                limit=ceiling*float(grid[z]/grid[zones].sum())
                self.trade.append(dict(route=identifier(country,z,'biomass_supply'),bus=bus,carrier='biomass',mode='pipeline',active=1,
                    import_p_nom=limit,import_limit=limit,export_p_nom=0,export_limit=0,
                    import_cost=self.price('biomass',self.years[0]),export_price=0,trade_capital_cost=0,trade_lifetime=30,
                    pressure_uplift_max=0,hourly_capacity_factor=1,distance_km=0,loss_per_km=0,
                    cost_assumption='Priced exogenous solid-biomass supply; allocated national source envelope, no route expansion.'))
        self.audit['differences'].append('E-fuel conversion recipes are retained. Refineries, internal fuel pipelines, terminals and external fuel trade portfolios are not equivalent in this target; they are not copied as unconstrained zero-cost routes. Synthesis is local to each zone; only priced biomass supply routes are introduced.')

    def build_heat_storage(self):
        # Native stocks and coupling ratios are available, but no independent
        # thermal-store power specification is supplied. Freeze those stocks;
        # record a four-hour charge/discharge assumption rather than free power.
        stocks=[]
        for sheet,kind in [('flex_tech_heat','INDV'),('flex_tech_DH','DH')]:
            for r in self.local(self.sheet(sheet)).to_dict('records'):
                energy=number(r,'cap_mw')*number(r,'storage_capacity_relation')
                if energy>0:
                    stocks.append((r,self.bus(r['zone'],'heat',kind,loss=self.dh_loss if kind=='DH' else 0),energy,0.))
        industry_storage=self.local(self.sheet('industry_heat_stor')) if 'industry_heat_stor' in self.book.sheet_names else pd.DataFrame()
        for r in industry_storage.to_dict('records'):
            if not enabled(r.get('include_in_the_model','Y')):continue
            zone=r['zone'];category=r.get('category','all')
            service=identifier('industry',r['Industry'],category)
            bus=identifier(self.countries[zone],zone,'heat',service)
            if bus not in self.heat:bus=identifier(self.countries[zone],zone,'heat','industry_remainder')
            if bus not in self.heat:continue
            energy=number(r,'cap_mwh')
            if energy<=0:continue
            stocks.append((r,bus,energy,number(r,'CAPEX')*1e6))
        for i,(r,bus,energy,cost) in enumerate(stocks):
            zone=r['zone'];name=identifier(bus,'thermal_store',r.get('unit_name',r.get('Industry','industry')),r.get('category','all'),i)
            self.hstores.append(dict(system=self.countries[zone],region=zone,name=name,tech='ThermalStorage',
                carrier_in='heat',carrier_out='heat',bus_in=bus,bus_out=bus,e_nom=energy,e_nom_max=energy,e_min=0,
                duration_charge=4,duration_discharge=4,efficiency_charge=1,efficiency_discharge=1,
                standby_loss=number(r,'loss'),capital_cost_energy=cost,capital_cost_power_charge=0,capital_cost_power_discharge=0,
                lifetime=number(r,'life_time',20),spillage_cost=0,final_cap=number(r,'final_life_cap',.1),
                decom_start_existing=number(r,'decom_start_existing_cap',8),decom_start_new=number(r,'decom_start_new',10)))
            self.costs.extend(dict(year=y,unit=name,field='capital_cost_energy',capital_cost=cost) for y in self.years)
        self.audit['assumptions'].append('Thermal stores retain supplied existing MWh stocks and heat-pump tank ratios, with four-hour charge/discharge duration and no independent expansion. Equipment/storage investment coupling is not reproduced. Solar-specific storage is not exported because the corresponding solar-heat resource equation is unavailable.')

    def build_policy(self):
        if self.scenario.get('preset')=='res100' and self.scenario.get('scope')=='all-energy':
            raise ValueError('Refactored model has no equivalent whole-energy RES preset with an exogenous fleet mix. Export a reference/electricity scenario and specify pathway and policy constraints in that model.')
        countries=set(self.countries.values())
        def aggregate(sheet,year,how):
            frame=pd.read_excel(self.policy_book,sheet)
            frame=frame.loc[frame.System.isin(countries)] if 'System' in frame else frame
            col=year if year in frame else str(year)
            if col not in frame or frame.empty:return ''
            vals=pd.to_numeric(frame[col],errors='raise').dropna()
            if vals.empty:return ''
            return float(vals.sum() if how=='sum' else vals.max())
        rows=[]
        biomass=pd.read_excel(self.policy_book,'biomass_caps')
        for year in self.years:
            caps=biomass.loc[biomass.System.isin(countries)&biomass.Year.eq(year)]
            biomass_cap=float(caps.Cap_TWh.sum())*1e6 if not caps.empty else ''
            rows.append(dict(year=year,co2_price='',co2_cap=aggregate('CO2',year,'sum'),
                curtailment_price='',curtailment_cap='',res_target=aggregate('RPS',year,'max'),
                co2_seq_cost='',co2_seq_limit='',biomass_cap=biomass_cap))
        self.write_table('policy.csv',rows)
        self.audit['assumptions'].append('Policy CO2 caps retain native tonnes/year and sum selected country caps. RES uses the strictest selected country electricity target. Carbon prices and sequestration/curtailment caps are left blank because their scopes differ; blank is not a zero cap. Biomass caps sum native country TWh budgets converted to MWh. Synthesis biomass import capacity uses the minimum horizon ceiling, divided across zones, because route capacities are not time-indexed.')

    def write_fuels(self):
        # Target loader requires even a carrier-coupled heat converter's label
        # in this file, although its price is charged on the bus instead.
        coupled={carrier(c) for c in SYNTHETIC}|{'electricity','co2','nitrogen'} if self.efuels else {'electricity'}
        path=self.destination/'fuel_cost.csv'
        for i,year in enumerate(self.years):
            values={fuel:np.full(8760,0 if fuel in coupled else self.price(fuel,year)) for fuel in sorted(self.used_fuels)}
            frame=pd.DataFrame(values);frame.insert(0,'period',np.arange(1,8761));frame.insert(0,'year',year)
            frame.to_csv(path,index=False,mode='w' if i==0 else 'a',header=i==0,float_format='%.12g')

    def write_table(self,name,rows):
        headers=json.loads(CONTRACT.read_text(encoding='utf-8'))['headers'][name]
        frame=pd.DataFrame(rows)
        for c in headers:
            if c not in frame:frame[c]=''
        frame=frame[headers+[c for c in frame if c not in headers]]
        path=self.destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        frame.to_csv(path,index=False,float_format='%.12g')

    def write_hourly(self,name,frame,*,multipliers=None):
        frame=frame.copy();frame.index.name='period'
        if len(frame)!=8760 or list(frame.index)!=list(range(1,8761)):
            raise ValueError(f'Incomplete model calendar for {name}')
        if not np.isfinite(frame.to_numpy(float)).all() or (frame.to_numpy(float)<0).any():
            raise ValueError(f'Invalid output timeseries {name}')
        path=self.destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        for i,year in enumerate(self.years):
            current=frame.copy()
            if multipliers:
                for col,(zone,sheet) in multipliers.items():
                    current[col]*=self.demand_multiplier(sheet,zone,year)
            current=current.copy() # consolidate columns after per-bus scaling
            current.insert(0,'year',year)
            current.reset_index()[['year','period',*frame.columns]].to_csv(path,index=False,mode='w' if i==0 else 'a',header=i==0,float_format='%.12g')

    def build(self):
        self.destination.mkdir(parents=True,exist_ok=True)
        self.dh_loss=float(pd.read_excel(self.policy_book,'DH_loss').iloc[0,0])
        for zone in self.countries:self.bus(zone,'electricity')
        print('Refactored export: mapping generators and heating',flush=True)
        self.build_power();self.build_heating()
        print('Refactored export: mapping industrial services and fleet pathways',flush=True)
        self.build_industry();self.build_transport();self.build_electricity_demand();self.build_network()
        self.build_flex_and_efuel();self.build_heat_storage()
        self.build_policy()
        for path,rows in [('buses.csv',list(self.buses.values())),('electricity/powerplants.csv',self.plants),
            ('electricity/storage_units.csv',self.stores),('heating/converters.csv',self.heaters),('heating/storage_units.csv',self.hstores),
            ('efuel/converters.csv',self.efuel),('efuel/storage_units.csv',self.fstores),('efuel/external_trade.csv',self.trade),
            ('efuel/transport_links.csv',self.links),('transport/fleets.csv',self.fleets),('transport/pathway.csv',self.pathway),
            ('transmission_lines.csv',self.lines),('capital_cost_by_year.csv',self.costs),('learning_rates.csv',[])]:
            self.write_table(path,rows)
        empty=pd.DataFrame(index=range(1,8761))
        for path,mapping in [('electricity/res_profile.csv',self.profile),('electricity/scaled_inflows.csv',self.inflows),
                             ('transport/demand.csv',self.mobility),('transport/connection.csv',self.connection),('efuel/demand.csv',self.edemand)]:
            self.write_hourly(path,pd.DataFrame(mapping,index=range(1,8761)) if mapping else empty)
        self.write_hourly('electricity/electricity_demand.csv',self.electricity,
            multipliers={self.bus(z,'electricity'):(z,'dem_change') for z in self.countries})
        self.write_hourly('heating/heat_demand.csv',pd.DataFrame({b:v[0] for b,v in self.heat.items()}),
            multipliers={b:(v[1],v[2]) for b,v in self.heat.items()})
        self.write_hourly('heating/efficiency.csv',pd.DataFrame(self.efficiencies,index=range(1,8761)))
        self.write_fuels()
        self.audit['source_files_sha256']={**self.source_files,**{name:hashlib.sha256((self.data/name).read_bytes()).hexdigest()
            for name in [self.workbook,'fuel_prices.csv','policy_fuels.xlsx']}}
        self.audit['source_policy_sha256']=hashlib.sha256((self.data/('policy_efuel.xlsx' if self.efuels else 'policy.xlsx')).read_bytes()).hexdigest()
        self.audit['sectors']=['electricity','heating','transport']+(['efuel'] if self.efuels else [])
        self.audit['optimization_solved']=False
        (self.destination/'export_report.json').write_text(json.dumps(self.audit,indent=2),encoding='utf-8')
        (self.destination/'unit_mapping.csv').write_text(pd.DataFrame(self.unit_links).to_csv(index=False),encoding='utf-8')
        shutil.copy2(CONTRACT,self.destination/'input_contract.json')
        shutil.copy2(ROOT/'refactored_case_loader.py',self.destination/'load_prepared_case.py')
        (self.destination/'README.txt').write_text('H2RES-refactored CSV case\n\nPoint the refactored model case directory at this folder.\nSectors: '+', '.join(self.audit['sectors'])+'\nYears: '+', '.join(map(str,self.years))+'; periods: 1..8760; dt=1 hour.\nRead export_report.json for representation changes and defaults.\nHourly heat-pump COP: heating/efficiency.csv (pass efficiency_ts_path).\nTo check with your model environment: python load_prepared_case.py --model-root PATH\nNo optimization solve or feasibility certification is performed.\n',encoding='utf-8')
        return self.audit


def validate_case(case):
    """Check the complete CSVs before publication, independently of model setup."""
    case=Path(case)
    audit=json.loads((case/'export_report.json').read_text(encoding='utf-8'))
    contract=json.loads(CONTRACT.read_text(encoding='utf-8'))
    years=audit['years'];expected={(y,p) for y in years for p in range(1,8761)}
    tables={};series={}
    for path in sorted(case.rglob('*.csv')):
        name=path.relative_to(case).as_posix()
        with path.open(encoding='utf-8-sig',newline='') as handle:header=next(csv.reader(handle))
        if len(header)!=len(set(header)):raise ValueError(f'Duplicate CSV columns: {name}')
        missing=set(contract['headers'].get(name,[]))-set(header)
        if missing:raise ValueError(f'Missing contract columns in {name}: {sorted(missing)}')
        if header[:2]==['year','period']:
            keys=set();totals=defaultdict(float)
            yearly_totals=defaultdict(lambda:defaultdict(float))
            yearly_zeros=defaultdict(lambda:defaultdict(int))
            for chunk in pd.read_csv(path,chunksize=8760):
                for y,p in chunk[['year','period']].itertuples(index=False,name=None):
                    if int(y)!=y or int(p)!=p or (y,p) in keys:raise ValueError(f'Duplicate/noninteger time key in {name}')
                    keys.add((y,p))
                vals=chunk.iloc[:,2:].to_numpy(float)
                if not np.isfinite(vals).all() or (vals<0).any():raise ValueError(f'Invalid timeseries values in {name}')
                if name in {'electricity/res_profile.csv','transport/connection.csv'} and (vals>1+1e-8).any():raise ValueError(f'Fraction above 1 in {name}')
                for col in header[2:]:totals[col]+=float(chunk[col].sum())
                if name=='electricity/electricity_demand.csv':
                    for year,group in chunk.groupby('year'):
                        for col in header[2:]:
                            yearly_totals[int(year)][col]+=float(group[col].sum())
                            yearly_zeros[int(year)][col]+=int(group[col].eq(0).sum())
            if keys!=expected:raise ValueError(f'Incomplete year/hour coverage in {name}')
            series[name]=dict(columns=header[2:],totals=dict(totals),rows=len(keys))
            if name=='electricity/electricity_demand.csv':
                series[name].update(yearly_totals=dict(yearly_totals),yearly_zero_hours=dict(yearly_zeros))
        else:tables[name]=pd.read_csv(path)
    missing=set(contract['headers'])-(set(tables)|set(series))
    if missing:raise ValueError(f'Missing refactored input files: {sorted(missing)}')
    buses=tables['buses.csv']
    if buses.bus.duplicated().any():raise ValueError('Duplicate bus IDs')
    carriers=dict(zip(buses.bus,buses.carrier));units={};all_names=[]
    for file in ['electricity/powerplants.csv','heating/converters.csv','efuel/converters.csv']:
        table=tables[file]
        for r in table.to_dict('records'):
            name=r['name'];all_names.append(name);units[name]=r
            for suffix in ['_out','_in','_out_2','_in_1','_in_2','_in_3']:
                b=r.get('bus'+suffix);c=r.get('carrier'+suffix)
                if pd.notna(b) and str(b):
                    if b not in carriers or carriers[b]!=c:raise ValueError(f'Invalid bus/carrier reference for {name}: {b}/{c}')
            if r['p_nom']<0 or r['p_nom_max']<r['p_nom']:raise ValueError(f'Invalid installed/maximum capacity for {name}')
            for key in ['capital_cost','lifetime','cap_factor']:
                if not np.isfinite(r[key]) or r[key]<0:raise ValueError(f'Invalid {key} for {name}')
    for file in ['electricity/storage_units.csv','heating/storage_units.csv','efuel/storage_units.csv']:
        for r in tables[file].to_dict('records'):
            all_names.append(r['name']);units[r['name']]=r
            b=r.get('bus',r.get('bus_out'))
            if b not in carriers:raise ValueError(f'Unknown storage bus {b}')
            if r['e_nom']<0 or r['e_nom_max']<r['e_nom']:raise ValueError(f'Invalid storage size for {r["name"]}')
    if len(all_names)!=len(set(all_names)):raise ValueError('Asset IDs must be unique across sectors')
    for file,c in [('electricity/electricity_demand.csv','electricity'),('heating/heat_demand.csv','heat')]:
        for b in series[file]['columns']:
            if carriers.get(b)!=c:raise ValueError(f'Demand references wrong bus {b}')
    for b in series['efuel/demand.csv']['columns']:
        if b not in carriers:raise ValueError(f'Unknown e-fuel demand bus {b}')
    electricity_audit=audit.get('electricity_accounting_MWh',{})
    allocation_checked=False
    if electricity_audit.get('method_id')=='national_sector_removal_preserve_regional_curves_v2':
        exported=series['electricity/electricity_demand.csv']
        if set(electricity_audit['regions'])!=set(exported['columns']):
            raise ValueError('Electricity allocation audit does not cover every demand bus')
        for bus,region in electricity_audit['regions'].items():
            for year in years:
                expected=region['exported_MWh_by_year'][str(year)]
                if not np.isclose(exported['yearly_totals'][year][bus],expected,rtol=1e-9,atol=1e-6):
                    raise ValueError(f'Electricity regional energy changed during export: {bus}/{year}')
                if exported['yearly_zero_hours'][year][bus]!=region['exported_zero_hours_by_year'][str(year)]:
                    raise ValueError(f'Unexpected zero electricity demand hours: {bus}/{year}')
        allocation_checked=True
    for name in series['electricity/res_profile.csv']['columns']+series['electricity/scaled_inflows.csv']['columns']+series['heating/efficiency.csv']['columns']:
        if name not in units:raise ValueError(f'Time series references unknown unit {name}')
    renewable=[r['name'] for r in tables['electricity/powerplants.csv'].to_dict('records') if r['fuel'] in {'solar','wind'} or r['tech']=='HROR']
    if set(renewable)-set(series['electricity/res_profile.csv']['columns']):raise ValueError('Profiled generator missing resource series')
    for r in tables['transmission_lines.csv'].to_dict('records'):
        if any(carriers.get(r[c])!='electricity' for c in ['from_bus','to_bus']):raise ValueError('Unknown transmission bus')
    for file,column in [('efuel/external_trade.csv','bus'),('efuel/transport_links.csv','from_bus'),('efuel/transport_links.csv','to_bus')]:
        for r in tables[file].to_dict('records'):
            if carriers.get(r[column])!=r['carrier']:raise ValueError(f'Invalid e-fuel route bus in {file}')
    costs=tables['capital_cost_by_year.csv']
    if costs.duplicated(['year','unit','field']).any():raise ValueError('Duplicate investment-cost keys')
    if set(costs.unit)-set(units):raise ValueError('Investment costs reference unknown units')
    for (name,field),block in costs.groupby(['unit','field']):
        if set(block.year)!=set(years):raise ValueError(f'Missing investment-cost year for {name}/{field}')
    cost_pairs=set(zip(costs.unit,costs.field))
    for name,r in units.items():
        required='capital_cost' if 'p_nom' in r else 'capital_cost_energy'
        if (name,required) not in cost_pairs:raise ValueError(f'Missing investment cost trajectory for {name}')
        if 'p_nom' in r and r.get('carrier_out') in {'electricity','heat'} and r['fuel'] not in series['fuel_cost.csv']['columns']:
            raise ValueError(f'Missing fuel-price column for {name}/{r["fuel"]}')
    fleet=tables['transport/fleets.csv'];pathway=tables['transport/pathway.csv']
    if fleet.name.duplicated().any() or pathway.duplicated(['year','fleet']).any():raise ValueError('Duplicate fleet/pathway keys')
    if set(pathway.fleet)!=set(fleet.name) or len(pathway)!=len(fleet)*len(years):raise ValueError('Incomplete fleet pathway')
    if set(fleet['mode'])!=set(series['transport/demand.csv']['columns']):raise ValueError('Transport demand modes do not match fleets')
    joined=pathway.merge(fleet[['name','mode']],left_on='fleet',right_on='name',validate='many_to_one')
    if not np.allclose(joined.groupby(['year','mode']).activity_share.sum(),1):raise ValueError('Fleet shares must sum to one by mode and year')
    for r in fleet.to_dict('records'):
        if r['efficiency']<=0 or not np.isfinite(r['efficiency']):raise ValueError('Invalid transport efficiency')
        if pd.notna(r['carrier_in']) and carriers.get(r['bus_in'])!=r['carrier_in']:raise ValueError('Invalid fleet carrier bus')
        if r['charging_mode']!='none' and r['name'] not in series['transport/connection.csv']['columns']:raise ValueError('Missing plugged-in curve')
    result=dict(ready=True,format='H2RES-refactored',years=years,hours_per_year=8760,
        buses=len(buses),assets=len(units),fleets=len(fleet),tables=len(tables),hourly_files=len(series),
        full_calendar_checked=True,asset_and_bus_references_complete=True,investment_cost_keys_complete=True,
        actual_reader_passed=False,optimization_solved=False,
        regional_electricity_energy_and_zero_hours_checked=allocation_checked)
    warnings=[]
    policy=tables['policy.csv'].set_index('year')
    fleet_rows=fleet.set_index('name')
    for year,group in pathway.groupby('year'):
        baseline=sum(series['transport/demand.csv']['totals'][fleet_rows.loc[r.fleet,'mode']]/len(years)
            *float(r.activity_share)*float(fleet_rows.loc[r.fleet,'co2_per_activity']) for r in group.itertuples())
        cap=policy.loc[year,'co2_cap']
        if pd.notna(cap) and baseline>float(cap)+1e-6:
            warnings.append(dict(year=int(year),baseline_transport_CO2_t=baseline,system_CO2_cap_t=float(cap),
                message='Prescribed baseline transport alone exceeds the carbon cap. Change the future fleet pathway/policy or supply sufficient modeled carbon removal; reader acceptance is not scenario feasibility.'))
    result['scenario_consistency_warnings']=warnings
    (case/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def export_refactored_bundle(bundle,out_root,*,model_root=None,preflight_only=False,**kwargs):
    """Stage/validate/archive, then publish atomically with rollback."""
    from native_data_delivery import publish_outputs
    from filesystem_publish import failure_details
    out_root=Path(out_root).resolve();out_root.mkdir(parents=True,exist_ok=True)
    phase='preflight'
    preflight_report=None
    preflight_path=out_root/'refactored_preflight.json'
    try:
        with TemporaryDirectory(dir=out_root,prefix='_rf_') as tmp:
            stage=Path(tmp);case=stage/'data_refactored'
            exporter=CaseExporter(bundle,case,**kwargs)
            try:
                print('Refactored export: checking source schemas, country/zone keys and year coverage',flush=True)
                preflight_report=preflight(exporter,model_root)
                preflight_path.write_text(json.dumps(preflight_report,indent=2),encoding='utf-8')
                if not preflight_report['ready']:
                    messages=[f"{r['source']}: {r['error']}" for r in preflight_report['errors'][:5]]
                    raise ValueError('Refactored input preflight failed: '+'; '.join(messages)+f'; see {preflight_path}')
                print(f"Refactored source checks passed: {preflight_report['checks']}",flush=True)
                if preflight_only:return preflight_report
                exporter.audit['preflight']=dict(ready=True,checks=preflight_report['checks'],report='preflight.json')
                phase='conversion'
                exporter.build()
                shutil.copy2(preflight_path,case/'preflight.json')
            finally:exporter.close()
            phase='CSV validation';report=validate_case(case)
            report['preflight_passed']=True
            (case/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            if model_root:
                phase='actual refactored reader validation'
                from refactored_case_loader import check_case
                actual=check_case(case,model_root)
                (case/'actual_reader_validation.json').write_text(json.dumps(actual,indent=2),encoding='utf-8')
                report.update(actual)
                (case/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            phase='archive'
            inventory={p.relative_to(case).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in case.rglob('*') if p.is_file()}
            (case/'FILES.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
            archive=stage/'H2RES_refactored_inputs.zip'
            with ZipFile(archive,'w',ZIP_DEFLATED) as z:
                for path in sorted(case.rglob('*')):
                    if path.is_file():z.write(path,'data/'+path.relative_to(case).as_posix())
            with ZipFile(archive) as z:
                if z.testzip() is not None:raise ValueError('Refactored ZIP integrity check failed')
                for name,digest in inventory.items():
                    if hashlib.sha256(z.read('data/'+name)).hexdigest()!=digest:raise ValueError('Refactored ZIP checksum mismatch')
            phase='publication'
            publish_outputs([(case,out_root/'data_refactored'),(archive,out_root/archive.name)],out_root,uuid4().hex[:10])
        failure=out_root/'refactored_export_failure.json'
        if failure.exists():failure.unlink()
        print(f'Refactored H2RES case: {out_root / "data_refactored"}\nRefactored input ZIP: {out_root / "H2RES_refactored_inputs.zip"}',flush=True)
        return report
    except Exception as error:
        if phase=='preflight' and preflight_report is None:
            preflight_path.write_text(json.dumps(dict(ready=False,phase='refactored input preflight',checks=0,
                errors=[dict(source=str(bundle),error=str(error))]),indent=2),encoding='utf-8')
        details=failure_details(error,phase);details['previous_refactored_case_retained']=True
        (out_root/'refactored_export_failure.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True,help='Existing model_inputs folder with data and bundle_manifest.json')
    parser.add_argument('--out-root',type=Path,required=True)
    parser.add_argument('--model-root',type=Path,help='Optional separate refactored installation for actual-reader validation')
    parser.add_argument('--years',help='Comma-separated years; default is the native scenario horizon')
    parser.add_argument('--industry-mode',choices=['regular','categories','complex'])
    parser.add_argument('--efuels',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--preflight-only',action='store_true',help='Check prepared source files, keys and reference coverage without generating or replacing the CSV case')
    args=parser.parse_args(argv)
    try:
        export_refactored_bundle(args.bundle,args.out_root,model_root=args.model_root,
            preflight_only=args.preflight_only,
            industry_mode=args.industry_mode,efuels=args.efuels,years=[int(y) for y in args.years.split(',')] if args.years else None)
        return 0
    except (OSError,ValueError,KeyError,ImportError) as error:
        print(f'ERROR: {error}',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
