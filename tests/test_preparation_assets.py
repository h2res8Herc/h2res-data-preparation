"""Source ZIPs must not mistake Git LFS pointer text for NumPy data."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preparation_assets import PreparationAssetError,validate_hydro_profiles,validate_assets_for_args

POINTER=b'version https://git-lfs.github.com/spec/v1\noid sha256:'+b'0'*64+b'\nsize 107182326\n'

class AssetChecks(unittest.TestCase):
    def test_lfs_pointer_has_a_specific_recovery_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'runoff_shapes_2020.npz';path.write_bytes(POINTER)
            with self.assertRaisesRegex(PreparationAssetError,'Git LFS pointer.*107,182,326') as caught:
                validate_hydro_profiles(path)
            self.assertIn('git lfs pull',str(caught.exception))
            self.assertIn('portable ZIP',str(caught.exception))

    def test_npz_arrays_are_checked_without_enabling_pickle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'hydro.npz'
            np.savez_compressed(path,plant_id=np.array(['A']),runoff_share=np.ones((1,2)),time=np.array([0,1]))
            self.assertTrue(validate_hydro_profiles(path)['valid_npz'])
            np.savez_compressed(path,unrelated=np.ones(2))
            with self.assertRaisesRegex(PreparationAssetError,'lacks required arrays'):validate_hydro_profiles(path)

    def test_incomplete_or_wrong_files_have_no_pickle_recovery_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'hydro.npz';path.write_bytes(b'PK\x03\x04truncated')
            with self.assertRaisesRegex(PreparationAssetError,'not a valid NPZ'):validate_hydro_profiles(path)

    def test_unselected_hydro_and_export_only_do_not_require_a_package(self):
        args=SimpleNamespace(export_only=True,import_model_inputs=False,sectors=['power'],skip_hydro_profiles=False)
        validate_assets_for_args(args)
        args.export_only=False;args.sectors=['industry'];validate_assets_for_args(args)
        args.sectors=['power'];args.skip_hydro_profiles=True;validate_assets_for_args(args)

    def test_standalone_hydro_rejects_pointer_before_other_inputs_or_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'hydro.npz';path.write_bytes(POINTER)
            command=[sys.executable,str(ROOT/'power/hydro/generate_hydro_inputs_standalone.py'),
                '--year','2020','--countries','HR','--profiles',str(path),'--outdir',str(root/'output')]
            for flag in ['--detailed-genco','--aggregated-genco','--aggregation-schema','--hydro-units','--plants']:
                command.extend([flag,str(root/'missing.csv')])
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn('Git LFS pointer',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
            self.assertNotIn('allow_pickle=',result.stderr)
            self.assertFalse((root/'output').exists())

if __name__=='__main__':unittest.main()
