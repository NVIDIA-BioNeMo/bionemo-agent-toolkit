import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from upgrade_state import upgrade,inventory,content,require_completed_activation


class OfflineUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.addCleanup(self.writable)
        self.old=self.base/'legacy';self.old.mkdir()
        self.new=self.base/'managed'
        self.cfg={'kind':'local','instance':'previous','remote_root':'/srv/rfd4','studio_url':'http://127.0.0.1'}
        (self.old/'config.json').write_text(json.dumps(self.cfg))
        (self.old/'drafts').mkdir();(self.old/'drafts/demo.json').write_text('{"note":"preserve"}')
        self.job=self.old/'state/job/job.json';self.job.parent.mkdir(parents=True)
        self.job.write_text(json.dumps({'job_id':'job','status':'completed','target':self.cfg}))

    def writable(self):
        for path in [self.base,*self.base.rglob('*')]:
            if not path.is_symlink():path.chmod(0o700 if path.is_dir() else 0o600)

    def run_upgrade(self,**kwargs):
        return upgrade(self.old,self.new,old_installation_disabled=True,scan=lambda root:[],**kwargs)

    def test_explicit_disabled_installation_required_before_changes(self):
        before=inventory(self.old)
        with self.assertRaisesRegex(ValueError,'Disable the old installation'):
            upgrade(self.old,self.new)
        self.assertEqual(inventory(self.old),before);self.assertFalse(self.new.exists())

    def test_quarantine_sync_failure_prevents_publication_and_can_resume(self):
        from upgrade_state import flush_tree
        with patch('upgrade_state.flush_tree',side_effect=OSError('sync failed')) as sync:
            with self.assertRaisesRegex(OSError,'sync failed'):self.run_upgrade()
        sync.assert_called_once_with(self.old)
        self.assertFalse(self.new.exists())
        journal=json.loads((self.base/'.managed.upgrade.json').read_text())
        self.assertEqual(journal['phase'],'snapshotted')
        self.assertFalse(any(item['mode']&0o222 for item in inventory(self.old).values()))
        with patch('upgrade_state.flush_tree',wraps=flush_tree) as sync:
            self.run_upgrade()
        self.assertEqual(sync.call_args_list[0].args,(self.old,))
        self.assertTrue(self.new.is_dir())

    def test_publication_marker_does_not_allow_opening_before_journal_completion(self):
        def crash(phase):
            if phase=='after_activation':raise SystemExit('power loss')
        with self.assertRaises(SystemExit):self.run_upgrade(checkpoint=crash)
        before=inventory(self.new)
        with self.assertRaisesRegex(ValueError,'activation is incomplete'):
            require_completed_activation(self.new)
        self.assertEqual(inventory(self.new),before)
        self.run_upgrade()
        marker=require_completed_activation(self.new)
        self.assertEqual(marker['new_root'],str(self.new))

    def test_real_backend_refuses_legacy_before_directory_creation_or_external_calls(self):
        from service import Service
        before=inventory(self.old)
        with self.assertRaisesRegex(ValueError,'requires offline upgrade'):
            Service(self.old,runner=lambda *a,**k:self.fail('external command'))
        self.assertEqual(inventory(self.old),before)

    def test_real_backend_refuses_incomplete_publication_then_opens_completed_upgrade(self):
        from service import Service
        def crash(phase):
            if phase=='after_activation':raise SystemExit()
        with self.assertRaises(SystemExit):self.run_upgrade(checkpoint=crash)
        before=inventory(self.new)
        with self.assertRaisesRegex(ValueError,'activation is incomplete'):
            Service(self.new,runner=lambda *a,**k:self.fail('external command'))
        self.assertEqual(inventory(self.new),before)
        self.run_upgrade()
        service=Service(self.new,runner=lambda *a,**k:self.fail('external command'))
        self.assertIsNone(service.managed.selection('new')['machine_id'])

    def test_backend_cannot_create_destination_during_unpublished_upgrade(self):
        from service import Service
        def crash(phase):
            if phase=='imported':raise SystemExit()
        with self.assertRaises(SystemExit):self.run_upgrade(checkpoint=crash)
        self.assertFalse(self.new.exists())
        with self.assertRaisesRegex(ValueError,'activation is incomplete'):Service(self.new)
        self.assertFalse(self.new.exists())
        self.run_upgrade()
        require_completed_activation(self.new)

    def test_upgraded_backend_rejects_newer_protocol_without_writes(self):
        from service import Service
        self.run_upgrade()
        path=self.new/'managed-v2/state.json'
        data=json.loads(path.read_text());data['minimum_backend_protocol']=9999
        path.write_text(json.dumps(data));before=inventory(self.new)
        with self.assertRaisesRegex(ValueError,'protocol is unsupported'):Service(self.new)
        self.assertEqual(inventory(self.new),before)

    def test_setup_only_legacy_root_blocks_backend_and_editor_without_writes(self):
        from service import Service
        from editor_runtime import ensure_editor
        from types import SimpleNamespace
        root=self.base/'setup-only';(root/'setup').mkdir(parents=True)
        (root/'setup/request.json').write_text('{"stage":"installing"}')
        before=inventory(root)
        with self.assertRaisesRegex(ValueError,'requires offline upgrade'):Service(root)
        with self.assertRaisesRegex(ValueError,'requires offline upgrade'):
            ensure_editor(SimpleNamespace(root=root))
        self.assertEqual(inventory(root),before)

    def test_cpu_only_drafts_are_compatible_without_importing_compute(self):
        from service import Service
        root=self.base/'cpu-only';(root/'drafts').mkdir(parents=True)
        draft=root/'drafts/demo.json';draft.write_text('{"note":"preserve"}')
        before=draft.read_bytes()
        service=Service(root)
        self.assertIsNone(service.managed.selection('new')['machine_id'])
        self.assertEqual(draft.read_bytes(),before)
        self.assertFalse((root/'activation.json').exists())

    def test_active_job_refuses_without_quarantining_then_terminal_completion_imports(self):
        self.job.write_text(json.dumps({'job_id':'job','status':'running','target':self.cfg}))
        before=inventory(self.old)
        with self.assertRaisesRegex(ValueError,'active or unresolved legacy run'):self.run_upgrade()
        self.assertEqual(inventory(self.old),before)
        self.job.write_text(json.dumps({'job_id':'job','status':'completed','target':self.cfg,'exit_code':0}))
        raw=self.job.read_bytes()
        self.run_upgrade()
        self.assertEqual((self.new/'state/job/job.json').read_bytes(),raw)

    def test_active_or_unresolved_setup_blocks_even_without_a_local_process(self):
        (self.old/'setup').mkdir();path=self.old/'setup/session.json'
        for stage in ('requested','connecting','installing','downloading','checking','action_needed','unknown'):
            path.write_text(json.dumps({'stage':stage}))
            before=inventory(self.old)
            with self.assertRaisesRegex(ValueError,'legacy setup'):self.run_upgrade()
            self.assertEqual(inventory(self.old),before)
        path.write_text(json.dumps({'stage':'complete'}));self.run_upgrade()

    def test_writer_blocks_before_permissions_change(self):
        before=inventory(self.old)
        with self.assertRaisesRegex(ValueError,'controllers/workers'):
            upgrade(self.old,self.new,old_installation_disabled=True,scan=lambda root:[123])
        self.assertEqual(inventory(self.old),before)

    def test_quarantine_preserves_bytes_but_blocks_ordinary_atomic_writes(self):
        before=inventory(self.old)
        self.run_upgrade()
        self.assertEqual(content(inventory(self.old)),content(before))
        self.assertTrue(all(not item['mode']&0o222 for item in inventory(self.old).values()))
        with self.assertRaises(PermissionError):(self.old/'new.tmp').write_text('stale')
        with self.assertRaises(PermissionError):self.job.write_text('stale')
        self.assertEqual((self.new/'drafts/demo.json').read_text(),'{"note":"preserve"}')
        self.assertEqual((self.new/'managed-v2/legacy-backup/state/job/job.json').read_bytes(),self.job.read_bytes())
        metadata=json.loads((self.new/'managed-v2/state.json').read_text())
        self.assertIsNone(metadata['sessions']['workspace']['machine_id'])
        self.assertIsNotNone(metadata['legacy_run_bindings']['job']['machine_id'])

    def test_interruptions_resume_without_duplicate_import_or_unfreezing(self):
        for phase in ('snapshotted','quarantine_entry','quarantined','imported','before_activation','after_activation'):
            with self.subTest(phase=phase):
                # Each phase uses its own source and destination.
                source=self.base/('old-'+phase);source.mkdir()
                (source/'config.json').write_text(json.dumps(self.cfg))
                target=self.base/('new-'+phase)
                def crash(current):
                    if current==phase:raise SystemExit('injected controller loss')
                with self.assertRaises(SystemExit):
                    upgrade(source,target,old_installation_disabled=True,scan=lambda root:[],checkpoint=crash)
                result=upgrade(source,target,old_installation_disabled=True,scan=lambda root:[])
                self.assertEqual(result['state'],'activated')
                before=inventory(target)
                self.assertEqual(upgrade(source,target,old_installation_disabled=True,scan=lambda root:[]),result)
                self.assertEqual(inventory(target),before)
                self.assertTrue(all(not item['mode']&0o222 for item in inventory(source).values()))

    def test_normalized_overlapping_paths_and_parent_aliases_refused(self):
        alias=self.base/'alias';alias.symlink_to(self.base,target_is_directory=True)
        for target in (self.old/'../legacy/child',alias/'legacy/child'):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError,'nonoverlapping'):
                    upgrade(self.old,target,old_installation_disabled=True,scan=lambda root:[])

    def test_changed_imported_inventory_is_not_discarded_or_activated(self):
        def crash(phase):
            if phase=='imported':raise SystemExit()
        with self.assertRaises(SystemExit):self.run_upgrade(checkpoint=crash)
        journal=json.loads((self.base/'.managed.upgrade.json').read_text())
        staging=self.base/('.managed.upgrade-'+journal['id'])
        (staging/'drafts/demo.json').write_text('newer work')
        with self.assertRaisesRegex(ValueError,'Imported upgrade changed'):self.run_upgrade()
        self.assertEqual((staging/'drafts/demo.json').read_text(),'newer work')
        self.assertFalse(self.new.exists())

    def test_activation_replay_checks_marker_binding_and_quarantine(self):
        self.run_upgrade()
        path=self.new/'activation.json';marker=json.loads(path.read_text());marker['new_root']='another'
        path.write_text(json.dumps(marker))
        with self.assertRaisesRegex(ValueError,'not this upgrade'):self.run_upgrade()
