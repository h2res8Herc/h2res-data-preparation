"""A final Windows publication lock must not force expensive regeneration."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_data_delivery import retry_prepared_publication
from sector_method_provenance import file_hash


class RecoveryPublicationTests(unittest.TestCase):
    def prepared(self,root):
        recovery = root/'_unpublished_model_inputs_test'
        for name in ['data','h2res_inputs/data']:
            (recovery/name).mkdir(parents=True)
            (recovery/name/'input.csv').write_text('new validated data')
        (recovery/'validation.json').write_text(json.dumps({'ready':True,'variants':[{'ready':True}]}))
        (recovery/'bundle_manifest.json').write_text(json.dumps({'reference_files':{'input.csv':{}}}))
        with (recovery/'h2res_inputs/FILES.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['file','sha256'])
            writer.writeheader()
            writer.writerow({'file':'data/input.csv','sha256':file_hash(recovery/'data/input.csv')})
        (root/'data').mkdir()
        (root/'data/input.csv').write_text('previous data')
        return recovery

    def test_retry_publishes_only_the_finished_bundle_and_native_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            recovery=self.prepared(root)
            retry_prepared_publication(recovery,root)
            self.assertEqual((root/'data/input.csv').read_text(),'new validated data')
            self.assertEqual((root/'model_inputs/data/input.csv').read_text(),'new validated data')
            self.assertTrue(json.loads((root/'H2RES_DATA_manifest.json').read_text())['ready'])

    def test_changed_input_is_rejected_before_any_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            recovery=self.prepared(root)
            (recovery/'data/input.csv').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'changed after validation'):
                retry_prepared_publication(recovery,root)
            self.assertEqual((root/'data/input.csv').read_text(),'previous data')
            self.assertTrue(recovery.is_dir())

    def test_failed_retry_keeps_the_completed_recovery_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            recovery=self.prepared(root)
            with patch('native_data_delivery.publish_outputs',side_effect=PermissionError('still locked')):
                with self.assertRaises(PermissionError):
                    retry_prepared_publication(recovery,root)
            self.assertEqual((recovery/'data/input.csv').read_text(),'new validated data')
            self.assertEqual((root/'data/input.csv').read_text(),'previous data')


if __name__ == '__main__':
    unittest.main()
