"""Check release integrity and local runtime sources without downloading data."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def case_output_path(name):
    """Country runs and runtime caches are not part of the reusable generator."""
    parts=name.replace('\\','/').split('/')
    if len(parts)<2:
        return False
    top=parts[0].lower()
    return (top in {'examples','data','data_all','model_inputs'}
            or top.startswith(('outputs','sve_','data_')))


def check(root, dependencies=True):
    root=Path(root).resolve()
    sys.path.insert(0,str(root))
    manifest=json.loads((root/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,record in manifest['files'].items():
        if case_output_path(name):
            raise ValueError('Generated country outputs were included in the release: '+name)
        path=root/name
        if not path.resolve().is_relative_to(root) or not path.is_file() or digest(path)!=record['sha256']:
            raise ValueError('Missing or modified release file: '+name)
    for name in ['data_preparation_config.json','h2res_gui_config.json','.env','.cdsapirc']:
        if (root/name).exists():
            print('Local user settings found (not part of the released file inventory): '+name)
    reference=root/'model_reference_2_11_2026'
    ref=json.loads((reference/'manifest.json').read_text(encoding='utf-8'))
    assert len(ref['files'])==43
    for name,record in ref['files'].items():
        if digest(reference/'data'/name)!=record['sha256']:
            raise ValueError('Model reference file differs from the bundled reference: '+name)
    modules=['generate_all_sector_inputs','h2res_input_gui','model_input_bundle','model_variants',
             'refactored_input_export','refactored_case_loader',
             'power_input_links','native_input_checks','regional_network_inputs','policy_input_links',
             'industry.complex_regional_inputs',
             'industry.generate_complex_industry_inputs','industry.facility_sources',
             'industry.regional_allocation','heating.paper_calculator','heating.paper_weather',
             'transport.script.osm_infrastructure','transport.script.activity_units']
    for name in modules:
        module=importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise ValueError('Module loaded from outside this package: '+name)
    if dependencies:
        from preparation_dependencies import missing_dependencies,selected_dependencies
        missing=missing_dependencies(selected_dependencies(['power','industry','transport','heating']))
        if missing:
            raise ValueError('Missing preparation packages: '+', '.join(item['package'] for item in missing))
    return dict(ready=True,release_files=len(manifest['files']),reference_files=43,
                local_modules=len(modules),all_sector_dependencies_checked=dependencies,
                generated_country_outputs_included=False,model_executed=False,data_downloaded=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--skip-dependencies',action='store_true')
    args=parser.parse_args()
    print(json.dumps(check(args.root,not args.skip_dependencies),indent=2))
