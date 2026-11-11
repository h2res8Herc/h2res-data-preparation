"""Check required local assets without loading pickle data or downloading files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZipFile

ROOT=Path(__file__).resolve().parent
RELEASE_URL='https://github.com/h2res8Herc/h2res-data-preparation/releases'


class PreparationAssetError(ValueError):
    pass


def restore_hydro_profiles(path):
    """Rebuild a missing source-checkout asset from verified ordinary Git files."""
    path=Path(path)
    if path.is_file():
        with path.open('rb') as source:header=source.read(1024)
        if not header.startswith(b'version https://git-lfs.github.com/spec/v1'):
            return False
    directory=path.with_name(path.name+'.parts')
    manifest=directory/'manifest.json'
    if not manifest.is_file():return False
    try:
        details=json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(details,dict) or details.get('format_version')!=1 or details['target']!=path.name or not details['parts']:
            raise ValueError('invalid part manifest')
        if not isinstance(details['bytes'],int) or details['bytes']<=0 or not re.fullmatch('[0-9a-f]{64}',details['sha256']):
            raise ValueError('invalid archive size or checksum')
        parts=[]
        for record in details['parts']:
            name=record['file']
            if not isinstance(record['bytes'],int) or record['bytes']<=0 or not re.fullmatch('[0-9a-f]{64}',record['sha256']):
                raise ValueError('invalid part size or checksum')
            if not isinstance(name,str) or Path(name).name!=name or '\\' in name or '/' in name:
                raise ValueError('part path is not a filename')
            part=directory/name
            if not part.resolve().is_relative_to(directory.resolve()) or not part.is_file():
                raise ValueError('part is missing or outside its directory: '+name)
            parts.append((part,record))
        if len({p.name for p,_ in parts})!=len(parts):raise ValueError('duplicate part filenames')
    except (ValueError,KeyError,TypeError) as error:
        raise PreparationAssetError(f'Cannot restore hydro data from {manifest}: {error}') from error
    temporary=None
    try:
        digest=hashlib.sha256();total=0
        with NamedTemporaryFile(dir=path.parent,prefix='.hydro_',suffix='.tmp',delete=False) as target:
            temporary=Path(target.name)
            for part,record in parts:
                part_hash=hashlib.sha256();size=0
                with part.open('rb') as source:
                    for chunk in iter(lambda:source.read(1024*1024),b''):
                        target.write(chunk);part_hash.update(chunk);digest.update(chunk)
                        size+=len(chunk);total+=len(chunk)
                if size!=record['bytes'] or part_hash.hexdigest()!=record['sha256']:
                    raise PreparationAssetError(f'Hydro source part is incomplete or changed: {part}; extract the complete current source ZIP again.')
        if total!=details['bytes'] or digest.hexdigest()!=details['sha256']:
            raise PreparationAssetError(f'Reconstructed hydro data checksum differs from {manifest}; original file retained.')
        temporary.replace(path)
        print(f'Restored complete hydro data from local source parts: {path} ({total:,} bytes)',flush=True)
        return True
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def check_lfs_pointer(path):
    path=Path(path)
    if not path.is_file():raise PreparationAssetError(f'Required local data file is missing: {path}')
    with path.open('rb') as source:header=source.read(1024)
    if header.startswith(b'version https://git-lfs.github.com/spec/v1'):
        match=re.search(rb'\nsize (\d+)',header)
        expected=f"; expected {int(match.group(1)):,} bytes" if match else ''
        raise PreparationAssetError(
            f'{path} is a Git LFS pointer ({path.stat().st_size} bytes{expected}), not the actual data file. '
            'This can happen with GitHub Code > Download ZIP. '
            f'Download and extract the attached portable ZIP from {RELEASE_URL}, '
            'then copy power/hydro/precomputed/runoff_shapes_2020.npz into the same location in this installation. '
            'For a Git clone, run git lfs install followed by git lfs pull in the repository. '
            'Previously downloaded source data can be reused after restoring the real file.')
    return header


def validate_hydro_profiles(path):
    path=Path(path)
    restore_hydro_profiles(path)
    check_lfs_pointer(path)
    try:
        with ZipFile(path) as archive:
            required={'plant_id.npy','runoff_share.npy','time.npy'}
            missing=required-set(archive.namelist())
            if missing:raise PreparationAssetError(f'Hydro data archive {path} lacks required arrays: {sorted(missing)}')
    except BadZipFile as error:
        raise PreparationAssetError(f'Hydro data file {path} is not a valid NPZ archive; restore the complete file from the portable ZIP.') from error
    return dict(path=str(path),bytes=path.stat().st_size,valid_npz=True)


def validate_assets_for_args(args):
    if (args.export_only or args.import_model_inputs or 'power' not in args.sectors
            or args.skip_hydro_profiles):return
    validate_hydro_profiles(args.hydro_profiles)
    for path in (args.hydro_units,args.hydro_plants):check_lfs_pointer(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-hydro',action='store_true')
    parser.add_argument('--profiles',type=Path,default=ROOT/'power/hydro/precomputed/runoff_shapes_2020.npz')
    args=parser.parse_args()
    try:
        result=validate_hydro_profiles(args.profiles)
        print(f"Required hydro data verified: {result['bytes']:,} bytes")
        return 0
    except (OSError,PreparationAssetError) as error:
        print(f'ERROR: {error}',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
