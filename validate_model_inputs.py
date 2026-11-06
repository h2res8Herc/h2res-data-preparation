"""Validate a portable input bundle, optionally through the supplied model reader."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import sys
from contextlib import ExitStack

from model_input_bundle import ROOT, selected_workbook, validate_bundle


def read_with_model(model_root: Path, bundle: Path, *, industry_mode="categories", efuels=True,
                    electricity_case="conservative", complex_sectors=None, sample_hours=None) -> dict:
    """Run configuration and input loading only; never build or solve a model."""
    import gurobipy as gp
    import pandas as pd
    from run_model_scenario import configure, prepare_source, prepare_reader_source
    model_root = model_root.resolve()
    bundle = bundle.resolve()
    bundle_data = (bundle / "data").resolve()
    source = (model_root / "main.py").read_text(encoding="utf-8-sig")
    flags = {"model_efuel": efuels, "model_industry_categories": industry_mode == "categories",
             "model_complex_industry": industry_mode == "complex", "model_complex_non_metallic_minerals": industry_mode == "complex",
             "industry_storage": industry_mode == "categories",
             "industry_category_electricity_case": electricity_case, "industry_complex_electricity_case": electricity_case}
    settings = dict(technology_workbook=selected_workbook(efuels, industry_mode, electricity_case),
                    efuels=efuels, industry_electricity_case=electricity_case, preset="reference", scope="all-energy",
                    complex_workbook=None)
    if industry_mode == "complex":
        from model_input_bundle import selected_complex_workbook
        settings["complex_workbook"] = selected_complex_workbook(efuels, electricity_case)
        inventory=bundle/'variant_inventory.json'
        if not inventory.exists():
            inventory=bundle/'model_inputs/variant_inventory.json'
        if complex_sectors is None and inventory.is_file():
            entry=next((r for r in json.loads(inventory.read_text(encoding='utf-8')) if r['technology_workbook']==settings['technology_workbook']),{})
            complex_sectors=entry.get('complex_industry_sectors')
    namespace = {"__file__": str(model_root / "main.py"), "__name__": "input_reader_validation", "gp": gp}
    def configure_reader(ns):
        configure(ns, settings, bundle.resolve(), "input_reader_validation")
        if sample_hours is not None:
            ns.update(representative_capacity_mode=True,fixed_capacity_mode=False,
                      lightweight_representative_weeks_mode=False,representative_week_hours=int(sample_hours),
                      representative_weeks_count=1,representative_week_start_hours=(1,))
        if complex_sectors is not None:
            ns["complex_industry_sectors"] = list(complex_sectors)
    namespace["_scenario_configure"] = configure_reader
    previous = Path.cwd()
    old_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(model_root))
    try:
        # Model policies are read from their own directory. All live data paths
        # are redirected to the bundle after configuration has been evaluated.
        exec(compile(prepare_source(source, flags, prefix_only=True), str(model_root / "main.py"), "exec"), namespace)
        for name, value in list(namespace.items()):
            if isinstance(value, str) and value.startswith("./data/"):
                namespace[name] = str(bundle_data / Path(value).relative_to("data"))
        reader = model_root / "scripts" / "read_process_data.py"
        with ExitStack() as readers:
            if sample_hours is not None:
                from unittest.mock import patch
                if int(sample_hours)!=sample_hours or not 1<=sample_hours<=8760:
                    raise ValueError('Reader sample-hours must be an integer from 1 to 8760')
                csv_reader,excel_reader=pd.read_csv,pd.read_excel
                hourly={'industry_heat.csv','industry_category_profiles.csv','industry_electricity.csv',
                        'transport_profiles.csv','transport_demand.csv','heating_individual.csv','heating_district.csv',
                        'heating_electricity.csv','electricity_demand.csv','renewable_availability.csv','hydro_inflows.csv',
                        'cooling_individual.csv','cooling_district.csv','solar_thermal_availability.csv'}
                def selected(frame):
                    return frame.loc[pd.to_numeric(frame.period,errors='coerce').between(1,int(sample_hours))].copy() if isinstance(frame,pd.DataFrame) and 'period' in frame else frame
                def csv_sample(path,*args,**kwargs):
                    frame=csv_reader(path,*args,**kwargs)
                    return selected(frame) if isinstance(path,(str,Path)) and Path(path).name in hourly else frame
                def excel_sample(*args,**kwargs):
                    frame=excel_reader(*args,**kwargs)
                    return selected(frame)
                readers.enter_context(patch.object(pd,'read_csv',csv_sample))
                readers.enter_context(patch.object(pd,'read_excel',excel_sample))
            reader_source,repairs=prepare_reader_source(reader.read_text(encoding='utf-8-sig'))
            if repairs:print(f'[INPUT COMPATIBILITY] corrected {repairs} legacy regional industry aggregation loops')
            exec(compile(reader_source, str(reader), "exec"), namespace)
        # These exact dictionaries are indexed by the builder and objective.
        missing=[]
        costs=namespace.get('techology_cap_costs_years',{})
        limits=namespace.get('cap_inv_lim_long_lim',{})
        for plant in namespace.get('units',[]):
            for year in namespace.get('years',[]):
                if (plant,int(year)) not in costs:
                    missing.append(('generator_cost',plant,int(year)))
                for zone,plants in namespace.get('unit_zone_check',{}).items():
                    if plant in plants and (plant,int(year),zone) not in limits:
                        missing.append(('generator_investment',plant,int(year),zone))
        heat=namespace.get('heat_demand_industry',{})
        services={tuple(k[1:]) for k in namespace.get('active_industry_boilers',[])}
        for service in services:
            for period in namespace.get('periods',[]):
                if len(service)==4:
                    category,industry,zone,system=service
                    key=(industry,category,period,zone,system)
                else:
                    industry,zone,system=service
                    key=(industry,period,zone,system)
                if key not in heat:
                    missing.append(('industry_demand',key))
                    break
        if missing:
            raise ValueError('Native reader produced missing model lookup keys: '+repr(missing[:12]))
        industry_totals={}
        if industry_mode!='complex':
            import numpy as np
            file='industry_category_profiles.csv' if industry_mode=='categories' else 'industry_heat.csv'
            observed=pd.read_csv(bundle_data/file)
            observed=observed.loc[observed.period.isin(namespace['periods'])]
            for system,zone in observed[['System','zone']].drop_duplicates().itertuples(index=False,name=None):
                source=float(observed.loc[observed.System.eq(system)&observed.zone.eq(zone),'all'].sum())
                keys=set()
                for service in services:
                    if service[-2:]!=(zone,system):continue
                    for period in namespace['periods']:
                        if industry_mode=='categories':
                            category,industry,_,_=service
                            keys.add((industry,category,period,zone,system))
                        else:
                            industry,_,_=service
                            keys.add((industry,period,zone,system))
                actual=sum(float(heat.get(key,0.)) for key in keys)
                if not np.isclose(source,actual,rtol=1e-7,atol=1e-6):
                    raise ValueError(f'Native reader changed industry service in {system}/{zone}: source={source}, model={actual}')
                industry_totals[f'{system}/{zone}']=dict(source_MWh=source,model_MWh=actual)
        return {"reader_completed": True, "systems": namespace.get("Systems", []),
                "zones": namespace.get("zones", []), "technology_workbook": namespace.get("flex_tech_dat"),
                "years": [int(y) for y in namespace.get("years", [])],
                "modeled_periods": len(namespace.get("periods", [])),
                "full_year_periods": len(namespace.get("full_year_periods", [])),
                "hourly_sample_used":sample_hours is not None,"generator_objective_and_investment_keys_complete":True,
                "native_reader_remainder_loop_repairs":repairs,
                "industry_demand_keys_complete":True,"industry_services_checked":len(services),
                "industry_regional_service_conservation":industry_totals,
                "empty_generator_zones": [str(zone) for zone, units in namespace.get("unit_zone_check", {}).items() if not units],
                "complex_industry_sectors": namespace.get("complex_industry_sectors") if industry_mode == "complex" else None,
                "complex_component_years": len(namespace.get("complex_industry_inputs", {}).get("annual_useful_energy", {}))}
    finally:
        os.chdir(previous)
        sys.path.pop(0)
        sys.dont_write_bytecode = old_bytecode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "outputs_all" / "model_inputs")
    parser.add_argument("--industry-mode", choices=("regular", "categories", "complex"), default="categories")
    parser.add_argument("--efuels", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--industry-electricity-case", choices=("conservative", "technical_2050"), default="conservative")
    parser.add_argument("--read-with-model", type=Path, help="Use this model directory's current configuration and input reader as an additional check.")
    parser.add_argument('--sample-hours',type=int,help='Optional short native-reader check; full-file calendar validation still runs separately')
    args = parser.parse_args()
    filename = selected_workbook(args.efuels, args.industry_mode, args.industry_electricity_case)
    report = validate_bundle(args.bundle, filename, args.efuels, args.industry_mode, args.industry_electricity_case)
    if args.read_with_model:
        if (args.bundle / "scenario.json").exists() and args.sample_hours is None:
            from run_model_scenario import run
            namespace = run(args.read_with_model, args.bundle)
            report["model_reader"] = {"reader_completed": True, "systems": namespace.get("Systems", []),
                                      "zones": namespace.get("zones", []), "scenario_flags_applied": True,
                                      "years": [int(y) for y in namespace.get("years", [])]}
        else:
            report["model_reader"] = read_with_model(args.read_with_model, args.bundle, industry_mode=args.industry_mode,
                                                     efuels=args.efuels, electricity_case=args.industry_electricity_case,
                                                     sample_hours=args.sample_hours)
    output = args.bundle / "validation.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
