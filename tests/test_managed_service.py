"""Public service paths must honor the managed state contract."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service

class ManagedServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(self.tmp.name)
        from ownership_test_support import assume_owned
        assume_owned(self,self.service,skip_transport_identity=False)
        machine_identity=patch('registry.linux_machine_identity', side_effect=lambda cfg, run: {'linux_machine_id_sha256': cfg.get('ssh_host', 'local-test-host')})
        machine_identity.start(); self.addCleanup(machine_identity.stop)

    def register(self, session='demo'):
        return self.service.register_compute('local', 'gpu', '/srv/rfd4',
            'http://127.0.0.1:18764', session_id=session)

    def test_default_does_not_connect_new_session(self):
        self.register(None)
        self.assertEqual(self.service.compute_status('new')['state'], 'unregistered')
        with self.assertRaisesRegex(ValueError, 'No compute selected'):
            self.service.config('new')

    def test_disconnect_and_reselect_invalidates_old_plan_even_same_machine(self):
        status = self.register()
        cfg = self.service.config('demo')
        self.service.disconnect_compute('demo', status['selection']['revision'])
        self.service.register_registry_compute(cfg['target_id'], session_id='demo', expected_revision=2)
        self.assertNotEqual(cfg, self.service.config('demo'))
        self.assertEqual(self.service.compute_status('demo')['state'], 'registered')

    def test_stale_disconnect_cannot_clear_new_selection(self):
        self.register()
        with self.assertRaisesRegex(ValueError, 'Selection changed'):
            self.service.disconnect_compute('demo', 0)
        self.assertEqual(self.service.compute_status('demo')['state'], 'registered')

    def test_restore_only_suggests_machine(self):
        self.register()
        with patch.object(self.service, 'studio', return_value={'revision': 3, 'cif': 'annotated'}):
            self.service.save_draft('demo', 'preserve me')
        with patch.object(self.service, 'import_cif', return_value={'session_id': 'restored'}):
            result = self.service.restore_draft('demo')
        selection = self.service.managed.selection('restored')
        self.assertIsNone(selection['machine_id'])
        self.assertEqual(selection['previous_machine_id'], self.service.config('demo')['target_id'])
        self.assertEqual(result['note'], 'preserve me')

    def test_expired_editor_does_not_overwrite_saved_draft(self):
        import httpx
        with patch.object(self.service, 'studio', return_value={'revision': 3, 'cif': 'preserved'}):
            self.service.save_draft('demo', 'original')
        before = {str(p): p.read_bytes() for p in (Path(self.tmp.name) / 'drafts').rglob('*') if p.is_file()}
        for code, text, expected in [(404, 'session not found or expired', ValueError), (404, 'other missing resource', httpx.HTTPStatusError), (500, 'server failure', httpx.HTTPStatusError)]:
            response = httpx.Response(code, text=text, request=httpx.Request('POST', 'http://localhost/export'))
            error = httpx.HTTPStatusError(text, request=response.request, response=response)
            with patch.object(self.service, 'studio', side_effect=error), self.assertRaises(expected) as raised:
                self.service.save_draft('demo', 'replacement')
            if expected is ValueError:
                self.assertIn('EDITOR_SESSION_EXPIRED:', str(raised.exception))
            self.assertEqual(before, {str(p): p.read_bytes() for p in (Path(self.tmp.name) / 'drafts').rglob('*') if p.is_file()})

    def test_legacy_draft_does_not_reapply_target(self):
        drafts = Path(self.tmp.name) / 'drafts'
        drafts.mkdir()
        (drafts / 'old.json').write_text(json.dumps({'cif': 'old', 'note': '', 'settings': {},
            'target': {'kind': 'local', 'instance': 'old'}}))
        with patch.object(self.service, 'import_cif', return_value={'session_id': 'restored'}):
            self.service.restore_draft('old')
        self.assertEqual(self.service.compute_status('restored')['state'], 'unregistered')

    def test_copy_rejects_overwritten_draft_before_import(self):
        with patch.object(self.service, 'studio', return_value={'revision': 3, 'cif': 'annotated'}):
            saved = self.service.save_draft('demo', 'original')
            self.service.save_draft('demo', 'newer notes at same structure revision')
        with patch.object(self.service, 'import_cif') as importer:
            with self.assertRaisesRegex(ValueError, 'saved draft changed'):
                self.service.restore_draft('demo', saved['snapshot_checksum'])
            importer.assert_not_called()

    def test_copy_imports_exact_saved_bytes(self):
        with patch.object(self.service, 'studio', return_value={'revision': 3, 'cif': 'exact annotated content'}):
            saved = self.service.save_draft('demo', 'original')
        with patch.object(self.service, 'import_cif', return_value={'session_id':'copy'}) as importer:
            result = self.service.restore_draft('demo', saved['snapshot_checksum'])
            importer.assert_called_once_with('exact annotated content')
        self.assertEqual(result['note'], 'original')

    def test_disconnecting_does_not_modify_jobs_or_other_session(self):
        self.register('one')
        self.register('two')
        path = self.service.state / 'job'
        path.mkdir()
        job = {'job_id': 'job', 'status': 'running', 'target': self.service.config('one')}
        (path / 'job.json').write_text(json.dumps(job))
        before = (path / 'job.json').read_bytes()
        self.service.disconnect_compute('one', 1)
        self.assertEqual((path / 'job.json').read_bytes(), before)
        self.assertEqual(self.service.compute_status('two')['active_jobs'], ['job'])

    def test_readiness_result_after_disconnect_is_not_applied(self):
        self.register()
        def probe(*args, **kwargs):
            if self.service.managed.selection('demo')['machine_id']:
                self.service.disconnect_compute('demo', 1)
            return 'GPU'
        with patch.object(self.service, 'target_exec', side_effect=probe):
            self.assertEqual(self.service.check_compute('demo')['state'], 'unregistered')

    def test_stale_registration_does_not_mutate_machine(self):
        self.register()
        before = self.service.managed.snapshot()
        with self.assertRaisesRegex(ValueError, 'Selection changed'):
            self.service.register_compute('local', 'changed', '/changed', 'http://127.0.0.1',
                session_id='demo', expected_revision=0)
        self.assertEqual(self.service.managed.snapshot(), before)

    def test_connect_completion_allows_later_manage_request(self):
        first = self.service.begin_setup('demo')
        self.register()
        self.assertEqual(self.service.managed.operation(first['id'])['state'], 'succeeded')
        second = self.service.begin_setup('demo')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['state'], 'requested')

    def test_legacy_run_uses_snapshot_identity_not_reused_name(self):
        root = Path(self.tmp.name)
        def cfg(host):
            return {'kind': 'ssh', 'instance': 'same-name', 'target_id': 'old-id',
                    'remote_root': '/srv/rfd4', 'studio_url': 'http://127.0.0.1',
                    'ssh_host': host, 'ssh_access': {'host': host, 'alias': host}}
        (root / 'config.json').write_text(json.dumps(cfg('replacement')))
        directory = self.service.state / 'oldrun'
        directory.mkdir()
        (directory / 'job.json').write_text(json.dumps({'job_id': 'oldrun', 'status': 'running',
                                                       'target': cfg('original')}))
        from upgrade_state import upgrade,inventory
        before=inventory(root)
        with self.assertRaisesRegex(ValueError,'requires offline upgrade'):self.service.available_compute()
        self.assertEqual(inventory(root),before)
        destination=tempfile.TemporaryDirectory();self.addCleanup(destination.cleanup)
        new=Path(destination.name)/'activated'
        with self.assertRaisesRegex(ValueError,'active or unresolved legacy run'):
            upgrade(root,new,old_installation_disabled=True,scan=lambda root:[])
        job=json.loads((directory/'job.json').read_text());job['status']='completed'
        (directory/'job.json').write_text(json.dumps(job))
        def writable():
            for path in [root,*root.rglob('*')]:path.chmod(0o700 if path.is_dir() else 0o600)
        self.addCleanup(writable)
        upgrade(root,new,old_installation_disabled=True,scan=lambda root:[])
        self.service=Service(new)
        state=self.service.managed
        machine_id = state.snapshot()['legacy_run_bindings']['oldrun']['machine_id']
        self.service.register_registry_compute(machine_id, session_id='demo')
        self.assertEqual(state.machine(machine_id)['config']['ssh_host'],'original')
        self.assertEqual((new/'state/oldrun/job.json').read_bytes(),(directory/'job.json').read_bytes())
        self.assertEqual(self.service.compute_status('demo')['active_jobs'], [])
        replacement = state.selection('workspace')['previous_machine_id']
        self.service.register_registry_compute(replacement, session_id='demo')
        self.assertEqual(self.service.compute_status('demo')['active_jobs'], [])

    def test_unknown_legacy_run_is_not_reported_idle(self):
        self.register()
        directory = self.service.state / 'oldrun'
        directory.mkdir()
        (directory / 'job.json').write_text(json.dumps({'job_id': 'oldrun', 'status': 'submission_unknown',
            'target': {'kind': 'brev', 'instance': 'old', 'instance_id': 'unknown-org'}}))
        self.assertEqual(self.service.compute_status('demo')['unresolved_active_jobs'], ['oldrun'])

    def test_two_ssh_aliases_share_stable_machine_and_reservation(self):
        with patch('registry.effective_access', side_effect=lambda alias, run: {'alias': alias}), patch('registry.linux_machine_identity', return_value={'linux_machine_id_sha256': 'same-physical-host'}):
            self.service.register_compute('ssh', 'first', '/srv/rfd4', 'http://127.0.0.1', ssh_host='alias1', session_id='one')
            first = self.service.config('one')['target_id']
            self.service.register_compute('ssh', 'second', '/srv/rfd4', 'http://127.0.0.1', ssh_host='alias2', session_id='two')
            self.assertEqual(first, self.service.config('two')['target_id'])
            self.service.managed.reserve(first, 'run1', 'run')
            with self.assertRaisesRegex(ValueError, 'reserved'):
                self.service.register_compute('ssh', 'third', '/srv/rfd4', 'http://127.0.0.1', ssh_host='alias3', session_id='three')

    def test_jobs_on_brev_alias_are_visible_through_ssh_record(self):
        self.register('demo')
        local=self.service.config('demo')['target_id']
        other=self.service.managed.register({'provider':'brev','instance_id':'id','organization_id':'org'},{'kind':'brev'})['id']
        self.service.managed.bind_physical_identity(other,{'linux_machine_id_sha256':'local-test-host'})
        path=self.service.state/'aliasjob';path.mkdir()
        (path/'job.json').write_text(json.dumps({'job_id':'aliasjob','machine_id':other,'status':'running'}))
        self.assertEqual(self.service.machine_jobs(local)['active_jobs'],['aliasjob'])

    def test_verify_target_rechecks_physical_host(self):
        self.register('demo')
        cfg=self.service.config('demo')
        with patch('registry.linux_machine_identity',return_value={'linux_machine_id_sha256':'replacement'}):
            with self.assertRaisesRegex(ValueError,'identity changed'):self.service.verify_target(cfg)
