"""Build exhaustive option coverage and equation provenance without model execution."""
import csv
import hashlib
import json
from pathlib import Path
import re
from option_explanations import mappings

D=Path(__file__).resolve().parent


def main():
    config=list(csv.DictReader((D/'inventory/model_configuration.csv').open(encoding='utf-8-sig')))
    explanations=mappings()
    missing=sorted({(r['file'],r['name']) for r in config}-explanations.keys())
    if missing: raise ValueError('Settings need editorial explanations: '+repr(missing))
    lines=['# Complete configuration option reference','',
           '**Scope:** every assignment in the inspected top-level `main.py` and its three policy modules. This reference covers all 381 recorded assignments, including repeated/derived declarations and internal cache objects; the coverage report is generated from the actual configuration inventory. Function-local solver implementation variables are not additional user switches.','',
           'Each row gives the entered expression, its source line and its operational meaning. The entered default is not always the effective value: normalization, parent modules, workbook eligibility and execution-stage overrides still apply. Consult the [configuration guide](MAIN_CONFIGURATION_GUIDE.md) for dependencies and complete workflows, and the [equation chapter](MATHEMATICAL_FORMULATION.md) for physical/economic interpretation.','',
           'Boolean controls accept Python `True` or `False`. Dictionary keys, exact unit labels, native units and supported string values matter. An empty mapping supplies no extra overrides for that mapping; it does not necessarily disable other model constraints. A setting marked diagnostic, internal, incomplete or test-only is not a supported physical scenario selector.','']
    for file in dict.fromkeys(r['file'] for r in config):
        lines += ['## '+file,'','| Setting and source | Entered value / expression | Meaning and effect |','|---|---|---|']
        for row in config:
            if row['file']!=file: continue
            clean=lambda x:x.replace('|','&#124;').replace('\n',' ')
            lines.append('| `'+row['name']+'` (`'+file+':'+row['line']+'`) | `'+clean(row['value'])+'` | '+clean(explanations[file,row['name']])+' |')
        lines += ['']
    lines += ['## Conditional input paths and table-level selections','',
              'The top-level assignment catalogue is supplemented by conditional paths such as `policy_dat_fuels` (e-fuel carrier price workbook), `demand_co2` (external CO2 demand in the non-e-fuel branch) and the selected ammonia-demand path. These are derived from module choices. They are not additional independent physical options.','',
              'Workbook controls are equally important: `setup` years/hours, `active_zones`, detailed-industry `include_in_model`/native inclusion fields, `CC_active`, technology/capacity/cost rows, terminal activation and allowed import/export directions, RPS/CO2 paths, transport targets, market mandatory flags and supplier/route eligibility. Exact capitalization and placement are file-specific; follow the reader and [data reference](DATA_REFERENCE.md).','',
              'Individual flags do not guarantee investment or dispatch. They make a technology, equation or policy available; the optimizer still chooses within costs, demand, build rates, resource limits and all other active constraints. Likewise, removing one policy can leave another policy binding.']
    (D/'MODEL_OPTION_REFERENCE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    model=Path(json.loads((D/'inventory/documented_version.json').read_text())['model_root'])
    chapter=(D/'MATHEMATICAL_FORMULATION.md').read_text(encoding='utf-8')
    equations=[]
    pattern=r'```equation (E\d+)\n(.*?)\n```\n\nSource: `([^`]+)`; anchor: `([^`]+)`; Representation: ([^\n]+)'
    for m in re.finditer(pattern,chapter,re.S):
        eq,latex,source,anchor,kind=m.groups()
        path=model/source; payload=path.read_text(encoding='utf-8-sig')
        matches=[i for i,line in enumerate(payload.splitlines(),1) if anchor in line]
        if not matches: raise ValueError('Equation source anchor not found: '+eq+' '+source+' '+anchor)
        equations.append(dict(id=eq,latex=latex.strip(),source=source,source_anchor=anchor,
                              first_line=matches[0],matching_lines=matches,representation=kind,
                              source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    declared=re.findall(r'```equation (E\d+)',chapter)
    assert len(equations)==len(declared) and len(set(declared))==len(declared), 'Every equation needs one unique ID and source annotation'
    (D/'inventory/equation_sources.json').write_text(json.dumps(equations,indent=2),encoding='utf-8')
    coverage=dict(configuration_assignments=len(config),unique_settings=len({(r['file'],r['name']) for r in config}),
                  explained_assignments=len(config),missing_explanations=[],equations=len(equations),
                  equation_sources_resolved=True,model_executed=False)
    (D/'inventory/expanded_manual_coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
    print(json.dumps(coverage,indent=2))


if __name__=='__main__': main()
