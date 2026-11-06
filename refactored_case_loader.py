"""Load a generated CSV case with the separate refactored model, without solving."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory


def load_case(case_dir,model_root):
    case,model=Path(case_dir).resolve(),Path(model_root).resolve()
    if not (model/'data_loaders/load_system.py').is_file():
        raise ValueError('Select the refactored model root containing data_loaders/load_system.py')
    loaded=sys.modules.get('data_loaders')
    if loaded is not None and getattr(loaded,'__file__',None) and not Path(loaded.__file__).resolve().is_relative_to(model):
        raise ValueError('A different model reader is already imported; run this check in a fresh Python process')
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(model))
    from data_loaders.load_system import load_system
    report=json.loads((case/'export_report.json').read_text(encoding='utf-8'))
    ep=dict(powerplants_path=case/'electricity/powerplants.csv',storage_path=case/'electricity/storage_units.csv',
        renewable_profiles_path=case/'electricity/res_profile.csv',inflow_path=case/'electricity/scaled_inflows.csv',
        electricity_demand_path=case/'electricity/electricity_demand.csv')
    hp=dict(powerplants_path=case/'heating/converters.csv',storage_path=case/'heating/storage_units.csv',
        heating_demand_path=case/'heating/heat_demand.csv',efficiency_ts_path=case/'heating/efficiency.csv')
    tp={k+'_path':case/'transport'/v for k,v in [('fleets','fleets.csv'),('pathway','pathway.csv'),('demand','demand.csv'),('connection','connection.csv')]}
    ef={k+'_path':case/'efuel'/v for k,v in [('converters','converters.csv'),('storage','storage_units.csv'),('external_trade','external_trade.csv'),('transport_links','transport_links.csv'),('demand','demand.csv')]}
    return load_system(sectors=report['sectors'],electricity_paths=ep,heating_paths=hp,transport_paths=tp,
        efuel_paths=ef if report['efuels'] else None,buses_path=case/'buses.csv',fuel_cost_path=case/'fuel_cost.csv',
        transmission_path=case/'transmission_lines.csv',policy_path=case/'policy.csv')


def check_case(case_dir,model_root,sample_hours=24,prepare=True):
    """Sample every planning year and all units/zones using the actual reader."""
    import pandas as pd
    case=Path(case_dir).resolve()
    if not 1<=sample_hours<=8760:raise ValueError('sample-hours must be in 1..8760')
    with TemporaryDirectory(prefix='h2r_check_') as tmp:
        sampled=Path(tmp)/'case';sampled.mkdir()
        for path in case.rglob('*'):
            if not path.is_file():continue
            target=sampled/path.relative_to(case);target.parent.mkdir(parents=True,exist_ok=True)
            if path.suffix=='.csv' and list(pd.read_csv(path,nrows=0))[:2]==['year','period']:
                first=True
                for chunk in pd.read_csv(path,chunksize=8760):
                    chunk=chunk.loc[chunk.period.le(sample_hours)]
                    chunk.to_csv(target,index=False,mode='w' if first else 'a',header=first)
                    first=False
            else:shutil.copy2(path,target)
        system=load_case(sampled,model_root)
        report=dict(actual_reader_passed=True,sample_hours=sample_hours,years=list(system.sets.years),
                    buses=len(system.bus.name),generators=len(system.generators.unit),
                    full_calendar_validated_by_exporter=True,optimization_solved=False)
        import hashlib
        contract=json.loads((case/'input_contract.json').read_text(encoding='utf-8'))
        changed=[name for name,digest in contract['reader_sha256'].items() if not (Path(model_root)/name).is_file()
            or hashlib.sha256((Path(model_root)/name).read_bytes()).hexdigest()!=digest]
        report['reader_contract_matches_snapshot']=not changed
        report['changed_reader_files']=changed
        if prepare:
            from optimization_model import PowerData,HeatData,EfuelData,TransportData,CapexPaths
            cost=CapexPaths.from_case_dir(sampled)
            common=dict(years=list(system.sets.years),periods=list(range(1,sample_hours+1)),dt=1.)
            PowerData.from_system(system,capex_paths=cost,**common)
            HeatData.from_system(system,capex_paths=cost,**common)
            EfuelData.from_system(system,capex_paths=cost,**common)
            TransportData.from_system(system,**common)
            report['sector_data_preparation_passed']=True
        return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--model-root',type=Path,required=True)
    parser.add_argument('--sample-hours',type=int,default=24)
    parser.add_argument('--reader-only',action='store_true',help='Skip optimization-layer data preparation (does not need gurobipy)')
    args=parser.parse_args(argv)
    result=check_case(args.case_dir,args.model_root,args.sample_hours,prepare=not args.reader_only)
    print(json.dumps(result,indent=2))
    (args.case_dir/'actual_reader_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())
