"""Publish the native data folder together with its validation bundle."""
from pathlib import Path
import shutil
from filesystem_publish import replace_with_retry


def publish_outputs(pairs, root: Path, tag: str):
    root = root.resolve()
    operations = []
    for source, destination in pairs:
        if destination.is_symlink() or destination.resolve().parent != root:
            raise ValueError(f"Refusing to publish outside the output directory: {destination}")
        backup = root / f"_previous_{destination.name}_{tag}"
        operations.append((source, destination, backup, destination.exists()))
    published = []
    try:
        for _, destination, backup, existed in operations:
            if existed:
                replace_with_retry(destination, backup, attempts=20)
        for source, destination, _, _ in operations:
            replace_with_retry(source, destination, attempts=20)
            published.append(destination)
    except OSError as error:
        recovery_errors = []
        for source, destination, backup, existed in reversed(operations):
            try:
                if destination in published and destination.exists():
                    destination.replace(source)
                if existed and backup.exists():
                    backup.replace(destination)
            except OSError as recovery:
                recovery_errors.append(f"{backup}: {recovery}")
        if recovery_errors:
            raise OSError("Publication and rollback failed; previous inputs remain in backup paths: "
                          + "; ".join(recovery_errors)) from error
        raise PermissionError("Cannot publish model inputs; the previous bundle was retained. "
                              f"Filesystem error: {error}") from error
    for _, _, backup, existed in operations:
        if existed:
            try:
                if backup.is_dir():
                    shutil.rmtree(backup)
                else:
                    backup.unlink()
            except OSError:
                print(f"Export completed; an open-file lock prevented removing backup {backup}", flush=True)


def retry_prepared_publication(recovery: Path, root: Path):
    """Publish preserved, coverage-checked inputs without regenerating them.

    Run this in a fresh process after a Windows file lock. All native files must
    match the completed package's checksum inventory before anything is moved.
    On failure the original recovery bundle remains available for another retry.
    """
    import csv
    import json
    from tempfile import TemporaryDirectory
    from sector_method_provenance import file_hash

    root, recovery = root.resolve(), recovery.resolve()
    if recovery.parent != root or not recovery.name.startswith('_unpublished_model_inputs_'):
        raise ValueError('Recovery bundle must be a preserved unpublished export directly inside the output directory')
    report = json.loads((recovery / 'validation.json').read_text(encoding='utf-8'))
    if not report.get('ready') or any(not item.get('ready') for item in report.get('variants',[])):
        raise ValueError('Recovery input coverage has not passed; regenerate the incomplete inputs')
    metadata = json.loads((recovery / 'bundle_manifest.json').read_text(encoding='utf-8'))
    actual = {p.relative_to(recovery/'data').as_posix() for p in (recovery/'data').rglob('*') if p.is_file()}
    if actual != set(metadata['reference_files']):
        raise ValueError('Recovery data layout differs from the model reference')
    inventory_path=recovery/'h2res_inputs/FILES.csv'
    if not inventory_path.is_file():
        # A packaging error can follow successful validation. Recheck saved
        # inputs before making their first checksum inventory; never download
        # sources or regenerate sectors during recovery.
        from model_input_bundle import validate_bundle
        from model_ready_package import build_package
        print('Rechecking saved native inputs and rebuilding the missing package; no source downloads.',flush=True)
        configurations=[dict(technology_workbook=report['technology_workbook'],efuels=report['efuels'],
                             industry_mode=report['industry_mode'],industry_electricity_case=report.get('industry_electricity_case','conservative')),
                        *report.get('variants',[])]
        checked={}
        for entry in configurations:
            key=(entry['technology_workbook'],entry['efuels'],entry['industry_mode'],entry.get('industry_electricity_case','conservative'))
            if key in checked:continue
            print(f'Recovery validation: {key[0]} ({key[3]})',flush=True)
            current=validate_bundle(recovery,*key)
            if not current.get('ready'):
                raise ValueError('Preserved native inputs failed revalidation: '+'; '.join(current['errors'][:8]))
            checked[key]=current
        report.update(checked[next(iter(checked))])
        report['variants']=[checked[(r['technology_workbook'],r['efuels'],r['industry_mode'],r.get('industry_electricity_case','conservative'))]
                            for r in report.get('variants',[])]
        (recovery/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        report['model_input_package']=build_package(recovery,report)
        (recovery/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with inventory_path.open(encoding='utf-8-sig',newline='') as stream:
        inventory = list(csv.DictReader(stream))
    if {item['file'] for item in inventory} != {'data/'+name for name in actual}:
        raise ValueError('Recovery package checksum inventory is incomplete')
    for item in inventory:
        for folder in (recovery,recovery/'h2res_inputs'):
            path = folder/item['file']
            if not path.resolve().is_relative_to(folder.resolve()) or file_hash(path) != item['sha256']:
                raise ValueError('Recovery input changed after validation: '+item['file'])
    with TemporaryDirectory(dir=root,prefix='_native_publication_') as temporary:
        folder = Path(temporary)
        native = folder/'data'
        shutil.copytree(recovery/'data',native)
        summary = folder/'H2RES_DATA_manifest.json'
        summary.write_text(json.dumps(dict(data_folder='data',ready=True,
                           selected_configuration=metadata,validation=report),indent=2),encoding='utf-8')
        publish_outputs([(recovery,root/'model_inputs'),(native,root/'data'),
                         (summary,root/summary.name)],root,folder.name.removeprefix('_native_publication_'))
    (root/'model_export_failure.json').unlink(missing_ok=True)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Retry publication of a completed H2RES input export without regenerating it')
    parser.add_argument('--recovery-bundle',type=Path,required=True)
    parser.add_argument('--out-root',type=Path,required=True)
    args = parser.parse_args()
    retry_prepared_publication(args.recovery_bundle,args.out_root)
    print('Ready-to-use H2RES data folder: '+str(args.out_root.resolve()/'data'))
