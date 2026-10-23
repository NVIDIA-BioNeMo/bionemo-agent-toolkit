"""Named-host execution never invokes lifecycle operations or a local worker."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service
from chat_execution import target, ssh_options
import ssh_job

HOST = {'ssh_alias': 'gpu-test', 'runtime_root': '/home/ubuntu/rfd4', 'output_root': '/home/ubuntu/runs'}

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.service = Service(self.temp.name)
        with patch.object(self.service, 'studio', return_value={'cif': 'data_test\n', 'revision': 1, 'issues': []}):
            self.request = self.service.prepare_design_request('session', note='saved annotation notes')
        self.id = self.request['request_id']
        self.machine = 'a' * 32
        self.readiness = patch.object(self.service, 'check_named_target', return_value={'ready': True,
             'machine_identity': hashlib.sha256(self.machine.encode()).hexdigest()})
        self.readiness.start(); self.addCleanup(self.readiness.stop)

    def test_submit_acknowledged_in_call_without_local_worker(self):
        uploaded = {}
        def copy(args, timeout=60):
            uploaded.update(json.loads(Path(args[-2]).read_text()))
            return ''
        def execute(host, command, timeout=60):
            args = shlex.split(command)
            if args[0] == 'mkdir': return ''
            bundle = uploaded
            self.assertEqual(bundle['manifest']['request_checksum'], self.request['request_checksum'])
            self.assertEqual(base64.b64decode(bundle['input']), b'data_test\n')
            return json.dumps({'state': 'running', 'launch_checksum': bundle['launch_checksum']})
        with patch.object(self.service, 'run', side_effect=copy), patch.object(self.service, 'named_exec', side_effect=execute), patch('subprocess.Popen', side_effect=AssertionError('local worker')):
            job = self.service.submit_design_request(self.id, HOST)
        self.assertEqual(job['status'], 'running')
        self.assertEqual(self.service.saved_run_metadata(job)['note'], 'saved annotation notes')

    def test_repeated_submission_reconciles_original_job(self):
        with patch.object(self.service, 'run', return_value=''), patch.object(self.service, 'named_exec', side_effect=['', TimeoutError('TLS failure')]):
            job = self.service.submit_design_request(self.id, HOST)
        self.assertEqual(job['status'], 'submission_unknown')
        with patch.object(self.service, 'check_chat_job', return_value=job) as check, patch.object(self.service, 'named_exec', side_effect=AssertionError('duplicate launch')):
            self.assertEqual(self.service.submit_design_request(self.id, HOST), job)
            check.assert_called_once_with(self.id)
        with self.assertRaisesRegex(ValueError, 'another run or target'):
            self.service.submit_design_request(self.id, dict(HOST, ssh_alias='other-host'))

    def test_readiness_failure_can_retry_same_request_before_launch(self):
        with patch.object(self.service, 'check_named_target', return_value={'ready':False,'checks':{'cuda':False}}):
            with self.assertRaisesRegex(ValueError, 'cuda'):
                self.service.submit_design_request(self.id, HOST)
        self.assertFalse(self.service.read(self.id, 'job.json')['remote_dispatch_started'])

    def test_changed_machine_rejected(self):
        with patch.object(self.service, 'run', return_value=''), patch.object(self.service, 'named_exec', side_effect=['', TimeoutError('interrupted')]):
            self.service.submit_design_request(self.id, HOST)
        with patch.object(self.service, 'named_exec', return_value='b' * 32):
            with self.assertRaisesRegex(ValueError, 'target changed'):
                self.service.check_chat_job(self.id)

    def test_target_validation_and_strict_ssh(self):
        for values in (dict(HOST, ssh_alias='-oProxyCommand=bad'), dict(HOST, runtime_root='/a/../b'), dict(HOST, provision=True)):
            with self.assertRaises(ValueError): target(values)
        self.assertIn('StrictHostKeyChecking=yes', ssh_options())
        self.assertNotIn('StrictHostKeyChecking=no', ssh_options())

    def terminal_job(self):
        record = dict(job_id=self.id, snapshot_id=self.id, runtime_protocol=4,
            target=HOST, status='failed', remote_dispatch_started=True,
            remote_dir='/home/ubuntu/runs/'+self.id, launch_checksum='d'*64,
            machine_identity=hashlib.sha256(self.machine.encode()).hexdigest())
        self.service.save_job(record)
        return record

    def test_collection_rejects_wrong_host_without_publishing(self):
        self.terminal_job()
        with patch.object(self.service, 'named_exec', return_value='b'*32):
            with self.assertRaisesRegex(ValueError, 'target changed'):
                self.service.collect_chat_job(self.id)
        self.assertFalse((self.service.state/self.id/'collection.json').exists())

    def test_failed_collection_preserves_job_for_retry(self):
        record = self.terminal_job()
        with patch.object(self.service, 'named_exec', side_effect=[self.machine, TimeoutError('unreachable SSH')]):
            with self.assertRaises(TimeoutError): self.service.collect_chat_job(self.id)
        self.assertEqual(self.service.read(self.id, 'job.json'), record)
        self.assertFalse((self.service.state/self.id/'collection.json').exists())

    def test_failure_logs_collected_then_available_offline(self):
        record = self.terminal_job()
        logs = {'receipt.json': base64.b64encode(json.dumps({'state':'failed', 'launch_checksum':record['launch_checksum']}).encode()).decode(),
                'run.log': base64.b64encode(b'controlled model failure').decode()}
        with patch.object(self.service, 'named_exec', side_effect=[self.machine, json.dumps(logs)]):
            result = self.service.collect_chat_job(self.id)
        self.assertEqual(result['collection'], 'complete')
        self.assertEqual(len(result['logs']), 2)
        with patch.object(self.service, 'named_exec', side_effect=AssertionError('stopped')):
            self.assertEqual(self.service.collect_chat_job(self.id), result)

    def test_wrong_terminal_receipt_cannot_authorize_cleanup(self):
        self.terminal_job()
        logs = {'receipt.json':base64.b64encode(b'{"state":"failed","launch_checksum":"other"}').decode()}
        with patch.object(self.service, 'named_exec', side_effect=[self.machine,json.dumps(logs)]):
            with self.assertRaisesRegex(ValueError, 'receipt does not match'):
                self.service.collect_chat_job(self.id)
        self.assertFalse((self.service.state/self.id/'collection.json').exists())


class RemoteReceiptTests(unittest.TestCase):
    def test_duplicate_and_ambiguous_launch_never_spawn_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'run'
            helper=Path(ssh_job.__file__).read_text()
            manifest={'input_sha256':hashlib.sha256(b'input').hexdigest(),
                      'helper_sha256':hashlib.sha256(helper.encode()).hexdigest(), 'cwd':tmp, 'argv':['true']}
            digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            bundle={'manifest':manifest,'launch_checksum':digest,'helper':helper,'input':base64.b64encode(b'input').decode()}
            with patch.object(ssh_job.subprocess,'Popen') as spawn, patch.object(ssh_job.time,'sleep'):
                first=ssh_job.launch(directory,bundle)
                second=ssh_job.launch(directory,bundle)
            self.assertEqual(first,second)
            self.assertEqual(first['state'],'submission_unknown')
            spawn.assert_called_once()
            self.assertTrue((directory/'receipt.json').exists())
            manifest['argv']=['false']
            with self.assertRaisesRegex(ValueError,'checksum'):
                ssh_job.launch(directory,bundle)

if __name__ == '__main__': unittest.main()
