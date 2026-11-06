"""Check required local assets without loading pickle data or downloading files."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys
from zipfile import BadZipFile, ZipFile

ROOT=Path(__file__).resolve().parent
RELEASE_URL='https://github.com/h2res8Herc/h2res-data-preparation/releases'


class PreparationAssetError(ValueError):
    pass


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
