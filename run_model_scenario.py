"""Load or solve a generated scenario using an unchanged H2RES model copy."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from scenario_runtime import add_renewable_constraints


def native_variant_files(efuels, mode, case):
    """Keep the copied model launcher independent of the preparation package."""
    name='flex_tech'+('_efuel' if efuels else '')+{'regular':'','categories':'_categories','complex':'_complex_industry'}[mode]+'.xlsx'
    if efuels and mode=='categories' and case=='technical_2050':
        name='variants/technical_2050/'+name
    companion='industry_complex'+('_efuel' if efuels else '')+('_electricity_technical_2050' if case=='technical_2050' else '')+'.xlsx'
    return name,companion if mode=='complex' else None


def configure(ns, scenario: dict, bundle: Path, name: str):
    for key, value in list(ns.items()):
        if isinstance(value, str) and value.startswith("./data/"):
            ns[key] = str(bundle / "data" / Path(value).relative_to("data"))
    ns.update(scen=name, flex_tech_dat=str(bundle / "data" / scenario["technology_workbook"]),
              industry_category_electricity_case=scenario["industry_electricity_case"],
              industry_complex_electricity_case=scenario["industry_electricity_case"])
    ns["policy_dat"] = str(bundle / "data" / ("policy_efuel.xlsx" if scenario["efuels"] else "policy.xlsx"))
    if scenario.get("complex_workbook"):
        ns["complex_industry_dat"] = str(bundle / "data" / scenario["complex_workbook"])
        generation = bundle / "complex_generation.json"
        if not generation.exists():
            generation = bundle / 'model_inputs' / 'complex_generation.json'
        if generation.exists():
            ns["complex_industry_sectors"] = json.loads(generation.read_text(encoding="utf-8"))["selected_industries"]
        inventory=bundle/'variant_inventory.json'
        if not inventory.exists():
            inventory=bundle/'model_inputs/variant_inventory.json'
        if inventory.is_file():
            entry=next((r for r in json.loads(inventory.read_text(encoding='utf-8')) if r['technology_workbook']==scenario['technology_workbook']),{})
            if entry.get('complex_industry_sectors'):
                ns['complex_industry_sectors']=entry['complex_industry_sectors']
    links = bundle / 'generator_input_links.json'
    if not links.exists():
        links = bundle / 'model_inputs' / 'generator_input_links.json'
    if links.is_file():
        records = json.loads(links.read_text(encoding='utf-8'))
        selected = next((r for r in records if r['workbook']==scenario['technology_workbook']),None)
        multipliers = dict(ns.get('generation_annual_build_limit_multipliers',{}))
        applied = {}
        if selected:
            for plant in selected['generators']:
                name_key = plant['unit_name']
                if name_key in multipliers:
                    continue
                donor_keys = plant['investment_donor_columns']
                values = {float(multipliers.get(key,1.)) for key in donor_keys}
                if len(values)>1:
                    raise ValueError(f'Mixed legacy investment multipliers for {name_key}; set an explicit multiplier using its generated name')
                if values:
                    multipliers[name_key]=next(iter(values))
                    applied[name_key]=multipliers[name_key]
        ns['generation_annual_build_limit_multipliers']=multipliers
        ns['generated_investment_policy_aliases']=applied
    if scenario["preset"] == "res100":
        ns["rps_inv"] = True
    if scenario["preset"] == "res100" and scenario["scope"] == "all-energy" and ns.get("two_stage_auto_mode"):
        raise ValueError("Whole-energy scenario launcher currently supports standard perfect foresight/myopic runs; disable two-stage mode")
    # Data fallbacks and result exports use this bundle, not the model folder.
    os.chdir(bundle)


def prepare_source(source: str, flags: dict, *, prefix_only=False):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in flags:
                node.value = ast.Constant(flags[name])
    boundary = next((i for i, node in enumerate(tree.body) if isinstance(node, ast.FunctionDef) and node.name == "exec_script"), None)
    if boundary is None:
        raise ValueError("Cannot find the supported model's exec_script boundary")
    hook = ast.parse("_scenario_configure(globals())").body[0]
    if prefix_only:
        tree.body = tree.body[:boundary] + [hook]
    else:
        function = tree.body[boundary]
        function.body = ast.parse("return _scenario_execute(path, globals())").body
        tree.body.insert(boundary, hook)
    return ast.fix_missing_locations(tree)


def prepare_reader_source(source: str):
    """Correct the legacy regional remainder loop without editing model files.

    Only move the accumulated concat after its excluded-sector loop. Running
    it inside the loop deletes other regions' source rows before they are read.
    Already corrected model readers pass through unchanged.
    """
    tree=ast.parse(source)
    repaired=0
    for parent in ast.walk(tree):
        for field,body in ast.iter_fields(parent):
            if not isinstance(body,list):continue
            rewritten=[]
            for node in body:
                rewritten.append(node)
                if not isinstance(node,ast.For) or not node.body:continue
                iterator=node.iter
                if not (isinstance(iterator,ast.Call) and isinstance(iterator.func,ast.Attribute)
                        and iterator.func.attr=='items' and isinstance(iterator.func.value,ast.Name)
                        and iterator.func.value.id in {'excluded_sector_map','excluded_sector_cat_map'}):continue
                candidates=[n for n in ast.walk(node) if isinstance(n,ast.If) and isinstance(n.test,ast.Name)
                            and n.test.id=='remainder_rows' and any(isinstance(v,ast.Name) and v.id=='Industry_demand_long_df' for v in ast.walk(n))]
                if len(candidates)!=1:continue
                last=candidates[0]
                for owner in ast.walk(node):
                    for _,statements in ast.iter_fields(owner):
                        if isinstance(statements,list) and last in statements:
                            statements.remove(last)
                            rewritten.append(last)
                            repaired+=1
            setattr(parent,field,rewritten)
    return ast.fix_missing_locations(tree),repaired


def run(model_root: Path, bundle: Path, *, solve=False, name=None, industry_mode=None, efuels=None, electricity_case=None):
    import gurobipy as gp
    model_root, bundle = model_root.resolve(), bundle.resolve()
    scenario_path = bundle/'scenario.json'
    if not scenario_path.exists():
        scenario_path = bundle/'model_inputs/scenario.json'
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if industry_mode is not None or efuels is not None or electricity_case is not None:
        scenario['industry_mode']=industry_mode or scenario['industry_mode']
        scenario['efuels']=scenario['efuels'] if efuels is None else efuels
        scenario['industry_electricity_case']=electricity_case or scenario['industry_electricity_case']
        scenario['technology_workbook'],scenario['complex_workbook']=native_variant_files(scenario['efuels'],scenario['industry_mode'],scenario['industry_electricity_case'])
    manifest_path = bundle / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    native_manifest=bundle/'H2RES_DATA_manifest.json'
    if not manifest and native_manifest.is_file():
        native=json.loads(native_manifest.read_text(encoding='utf-8'))
        if not native.get('ready'):
            raise ValueError('The published native data folder has not passed generation checks')
        manifest=native['selected_configuration']
    if manifest.get("missing_generated_inputs"):
        raise ValueError("Scenario bundle has missing generated inputs; complete its validation first")
    validation = bundle / "validation.json"
    if not validation.exists():
        validation = bundle / "model_inputs" / "validation.json"
    if solve and (not validation.exists() or not json.loads(validation.read_text(encoding="utf-8")).get("ready")):
        raise ValueError("A solve requires a bundle with passing input coverage validation")
    name = name or f"{scenario['preset']}_{scenario['target_year']}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Scenario name may contain letters, numbers, underscores and hyphens")
    if solve and (bundle / "results" / name).exists():
        raise ValueError("Results already exist for this scenario name; choose a new name")
    flags = {"model_efuel": scenario["efuels"], "model_industry_categories": scenario["industry_mode"] == "categories",
             "model_complex_industry": scenario["industry_mode"] == "complex",
             "model_complex_non_metallic_minerals": scenario["industry_mode"] == "complex",
             "industry_storage": scenario["industry_mode"] == "categories",
             "industry_category_electricity_case": scenario["industry_electricity_case"],
             "industry_complex_electricity_case": scenario["industry_electricity_case"]}
    if scenario["preset"] == "res100" and scenario["scope"] == "all-energy":
        flags.update(model_heating=True, model_transport_and_industry=True)
    namespace = {"__file__": str(model_root / "main.py"), "__name__": "__main__", "gp": gp}
    namespace["_scenario_configure"] = lambda ns: configure(ns, scenario, bundle, name)

    def execute(path, ns):
        script = Path(path)
        script = script if script.is_absolute() else model_root / script
        if script.name.startswith("CAPEX_OPEX") and scenario["preset"] == "res100" and ns.get("_renewable_scenario_model") is not ns.get("ucp"):
            raise ValueError("Renewable constraints were not attached to this model; refusing to solve")
        script_source=script.read_text(encoding="utf-8-sig")
        if script.name=='read_process_data.py':
            script_source,repairs=prepare_reader_source(script_source)
            ns['native_reader_remainder_loop_repairs']=repairs
            if repairs:print(f'[INPUT COMPATIBILITY] corrected {repairs} legacy regional industry aggregation loops')
        exec(compile(script_source, str(script), "exec"), ns)
        if script.name == "Build_model_dual_industry_categories_named_debug.py":
            add_renewable_constraints(ns, scenario)
    namespace["_scenario_execute"] = execute
    source = (model_root / "main.py").read_text(encoding="utf-8-sig")
    previous = Path.cwd()
    old_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(model_root))
    try:
        tree = prepare_source(source, flags, prefix_only=not solve)
        exec(compile(tree, str(model_root / "main.py"), "exec"), namespace)
        if not solve:
            execute("scripts/read_process_data.py", namespace)
            result = {"input_reader_completed": True, "years": [int(y) for y in namespace["years"]],
                      "preset": scenario["preset"], "scope": scenario["scope"], "target_year": scenario["target_year"],
                      "industry_mode": scenario["industry_mode"],
                      "complex_industry_sectors": namespace.get("complex_industry_sectors") if scenario["industry_mode"] == "complex" else None,
                      "complex_annual_component_years": len(namespace.get("complex_industry_inputs", {}).get("annual_useful_energy", {})),
                      "optimization_solved": False, "constraints_built": False}
            (bundle / "scenario_reader_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
        return namespace
    finally:
        os.chdir(previous)
        sys.path.pop(0)
        sys.dont_write_bytecode = old_bytecode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--solve", action="store_true", help="Build and solve; default only checks the actual input reader")
    parser.add_argument("--scenario-name")
    parser.add_argument('--industry-mode',choices=('regular','categories','complex'))
    parser.add_argument('--efuels',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--industry-electricity-case',choices=('conservative','technical_2050'))
    args = parser.parse_args()
    run(args.model_root, args.bundle, solve=args.solve, name=args.scenario_name,
        industry_mode=args.industry_mode,efuels=args.efuels,electricity_case=args.industry_electricity_case)


if __name__ == "__main__":
    main()
