"""Source ZIPs must not mistake Git LFS pointer text for NumPy data."""
from pathlib import Path
from contextlib import redirect_stdout
import hashlib
import io
import json
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
    def make_parts(self,root):
        path=root/'runoff_shapes_2020.npz'
        np.savez_compressed(path,plant_id=np.array(['A']),runoff_share=np.ones((1,2)),time=np.array([0,1]))
        payload=path.read_bytes()
        directory=path.with_name(path.name+'.parts');directory.mkdir()
        records=[]
        for i,chunk in enumerate([payload[:50],payload[50:]]):
            name=f'part-{i}.bin';(directory/name).write_bytes(chunk)
            records.append(dict(file=name,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
        manifest=dict(format_version=1,target=path.name,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),parts=records)
        (directory/'manifest.json').write_text(json.dumps(manifest))
        return path,directory,payload

    def test_source_zip_missing_asset_and_legacy_pointer_restore_from_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,_,payload=self.make_parts(Path(tmp))
            for placeholder in (None,POINTER):
                if placeholder is None:path.unlink()
                else:path.write_bytes(placeholder)
                with redirect_stdout(io.StringIO()):self.assertTrue(validate_hydro_profiles(path)['valid_npz'])
                self.assertEqual(path.read_bytes(),payload)
                self.assertEqual(list(Path(tmp).glob('.hydro_*.tmp')),[])

    def test_bad_or_missing_part_preserves_previous_pointer(self):
        for missing in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                path,parts,_=self.make_parts(Path(tmp));path.write_bytes(POINTER)
                if missing:(parts/'part-1.bin').unlink()
                else:(parts/'part-1.bin').write_bytes(b'damaged')
                with self.assertRaises(PreparationAssetError):validate_hydro_profiles(path)
                self.assertEqual(path.read_bytes(),POINTER)
                self.assertEqual(list(Path(tmp).glob('.hydro_*.tmp')),[])

    def test_wrong_combined_hash_and_unsafe_paths_are_rejected(self):
        for unsafe in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                path,parts,_=self.make_parts(Path(tmp));path.write_bytes(POINTER)
                manifest=parts/'manifest.json';record=json.loads(manifest.read_text())
                if unsafe:record['parts'][0]['file']='../outside.bin'
                else:record['sha256']='0'*64
                manifest.write_text(json.dumps(record))
                with self.assertRaises(PreparationAssetError):validate_hydro_profiles(path)
                self.assertEqual(path.read_bytes(),POINTER)

    def test_existing_complete_npz_does_not_require_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,parts,payload=self.make_parts(Path(tmp))
            (parts/'manifest.json').write_text('not valid JSON')
            self.assertTrue(validate_hydro_profiles(path)['valid_npz'])
            self.assertEqual(path.read_bytes(),payload)

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
