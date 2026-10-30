"""Preserve drafts and old compute data without activating a compute manager."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service

class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Service(self.temp.name)
        self.settings={'samples':1,'seed':42,'generation':{'thinking':'medium'}}

    def test_draft_save_restore_without_compute_or_state_migration(self):
        legacy=self.s.root/'config.json'
        content='{"kind":"ssh","instance":"old","ssh_host":"gpu","remote_root":"/srv/rfd4"}'
        legacy.write_text(content)
        with patch.object(self.s,'studio',return_value={'cif':'data_draft','revision':2}):
            saved=self.s.save_draft('draft',note='preserve',settings=self.settings)
        with patch.object(self.s,'import_cif',return_value={'session_id':'restored'}) as imported:
            value=self.s.restore_draft('draft',saved['snapshot_checksum'])
        imported.assert_called_once_with('data_draft')
        self.assertEqual(value['settings'],self.settings)
        self.assertEqual(value['note'],'preserve')
        self.assertEqual(legacy.read_text(),content)
        self.assertFalse((self.s.root/'state.json').exists())
        with patch.object(self.s,'run',side_effect=AssertionError('network')):
            suggestion=self.s.target_suggestions()['suggestions'][0]
        self.assertEqual(suggestion['target']['ssh_alias'],'gpu')
        self.assertFalse(suggestion['verified'])
        self.assertEqual(legacy.read_text(),content)

    def test_expired_session_does_not_overwrite_saved_draft(self):
        with patch.object(self.s,'studio',return_value={'cif':'original','revision':1}):
            self.s.save_draft('draft',settings=self.settings)
        path=self.s.root/'drafts/draft.json';before=path.read_bytes()
        response=httpx.Response(404,text='session not found or expired',request=httpx.Request('POST','http://localhost'))
        with patch.object(self.s,'studio',side_effect=httpx.HTTPStatusError('expired',request=response.request,response=response)):
            with self.assertRaisesRegex(ValueError,'EDITOR_SESSION_EXPIRED'):
                self.s.save_draft('draft',note='new')
        self.assertEqual(path.read_bytes(),before)

    def test_stale_draft_checksum_refuses_before_import(self):
        with patch.object(self.s,'studio',return_value={'cif':'original','revision':1}):
            saved=self.s.save_draft('draft',settings=self.settings)
            self.s.save_draft('draft',note='later',settings=self.settings)
        with patch.object(self.s,'import_cif') as imported:
            with self.assertRaisesRegex(ValueError,'changed'):
                self.s.restore_draft('draft',saved['snapshot_checksum'])
        imported.assert_not_called()

    def test_legacy_queue_is_readable_and_never_replayed(self):
        folder=self.s.state/'old';folder.mkdir()
        record={'job_id':'old','status':'queued','machine_id':'old-machine'}
        (folder/'job.json').write_text(json.dumps(record))
        with patch.object(self.s,'run',side_effect=AssertionError('remote launch')):
            result=self.s.status('old')
        self.assertEqual(result['status'],'queued')
        self.assertIn('never replays',result['detail'])
        self.assertEqual(json.loads((folder/'job.json').read_text()),record)

if __name__=='__main__':unittest.main()
