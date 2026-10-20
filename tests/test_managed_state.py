"""Managed compute persistence invariants, including multiprocess races."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from managed_state import State


def contender(args):
    root, machine, owner, purpose = args
    try:
        State(root).reserve(machine, owner, purpose)
        return owner
    except ValueError:
        return None


class ManagedStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = State(self.temp.name)
        self.machine = self.state.register({'ssh': 'verified-host'}, {'name': 'test'})['id']

    def test_disconnect_is_explicit_persistent_and_session_scoped(self):
        self.state.select('one', self.machine, 0)
        self.state.select('two', self.machine, 0)
        self.state.select('one', None, 1)
        reopened = State(self.temp.name)
        self.assertIsNone(reopened.selection('one')['machine_id'])
        self.assertEqual(reopened.selection('one')['previous_machine_id'], self.machine)
        self.assertEqual(reopened.selection('two')['machine_id'], self.machine)
        self.assertEqual(reopened.selection('new')['revision'], 0)

    def test_names_are_not_machine_identity(self):
        second = self.state.register({'ssh': 'other-host'}, {'name': 'test'})
        self.assertNotEqual(second['id'], self.machine)
        original = self.state.register({'ssh': 'verified-host'}, {'name': 'renamed'})
        self.assertEqual(original['id'], self.machine)
        self.assertEqual(original['revision'], 2)

    def test_duplicate_requests_and_stale_handoff(self):
        a = self.state.request('one', 'start', self.machine, 0)
        b = self.state.request('one', 'start', self.machine, 0)
        self.assertEqual(a['id'], b['id'])
        self.state.select('one', None, 0)
        with self.assertRaisesRegex(ValueError, 'Invalid operation transition'):
            self.state.transition(a['id'], 'authorized', evidence='user asked')

    def test_unknown_effect_remains_reserved_after_cancel_and_restart(self):
        op = self.state.request('one', 'stop', self.machine, 0)
        self.state.transition(op['id'], 'authorized', evidence='explicit user action')
        self.state.reserve(self.machine, op['id'], 'stop')
        self.state.transition(op['id'], 'dispatched')
        self.state.cancel(op['id'])
        reopened = State(self.temp.name)
        with self.assertRaises(ValueError):
            reopened.reserve(self.machine, 'new_run', 'run')
        with self.assertRaises(ValueError):
            reopened.release(self.machine, op['id'], 'timeout')
        reopened.transition(op['id'], 'succeeded', evidence='provider confirmed stopped')
        reopened.release(self.machine, op['id'], 'provider confirmed stopped')
        reopened.reserve(self.machine, 'new_run', 'run')

    def test_cancel_before_dispatch_does_not_dispatch(self):
        op = self.state.request('one', 'start', self.machine, 0)
        self.state.cancel(op['id'])
        with self.assertRaises(ValueError):
            self.state.transition(op['id'], 'authorized', evidence='late message')

    def test_dispatch_requires_reservation_and_authorization(self):
        op = self.state.request('one', 'start', self.machine, 0)
        with self.assertRaises(ValueError):
            self.state.transition(op['id'], 'authorized')
        self.state.transition(op['id'], 'authorized', evidence='explicit request')
        with self.assertRaises(ValueError):
            self.state.transition(op['id'], 'dispatched')

    def test_reserved_runtime_cannot_change(self):
        self.state.reserve(self.machine, 'run1', 'run')
        with self.assertRaises(ValueError):
            self.state.register({'ssh': 'verified-host'}, {'name': 'changed'})

    def test_stop_setup_run_race_has_exactly_one_owner(self):
        args = [(self.temp.name, self.machine, 'owner' + str(i), purpose)
                for i, purpose in enumerate(['run', 'stop', 'setup'])]
        with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
            winners = [value for value in pool.map(contender, args) if value]
        self.assertEqual(len(winners), 1)
        self.assertEqual(State(self.temp.name).snapshot()['reservations'][self.machine]['owner_id'], winners[0])

    def test_schema_rejected_without_overwriting(self):
        path = self.state.path
        data = json.loads(path.read_text())
        data['schema'] = 999
        path.write_text(json.dumps(data))
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            self.state.select('one', self.machine, 0)
        self.assertEqual(before, path.read_bytes())

    def test_migration_preserves_jobs_and_requires_explicit_reconnect(self):
        root = Path(self.temp.name)
        (root / 'sessions').mkdir()
        cfg = {'kind': 'ssh', 'instance': 'old', 'ssh_access': {'host': 'verified'},
               'remote_root': '/srv/rfd4', 'target_id': 'old'}
        (root / 'sessions' / 'demo.compute.json').write_text(json.dumps(cfg))
        jobdir = root / 'state' / 'job1'
        jobdir.mkdir(parents=True)
        job = b'{"target":{"instance":"old"},"status":"running"}'
        (jobdir / 'job.json').write_bytes(job)
        result = self.state.migrate_legacy()
        self.assertEqual(result['state'], 'complete')
        selection = self.state.selection('demo')
        self.assertIsNone(selection['machine_id'])
        self.assertIsNotNone(selection['previous_machine_id'])
        self.assertEqual((jobdir / 'job.json').read_bytes(), job)
        self.assertEqual((self.state.root / 'legacy-backup/state/job1/job.json').read_bytes(), job)
        self.assertEqual(self.state.migrate_legacy(), result)

    def test_unknown_brev_identity_remains_unresolved(self):
        (Path(self.temp.name) / 'config.json').write_text(json.dumps({
            'kind': 'brev', 'instance': 'old', 'instance_id': 'id1'}))
        result = self.state.migrate_legacy()
        self.assertEqual(len(result['unresolved']), 1)
        self.assertIsNone(self.state.selection('workspace')['previous_machine_id'])

    def test_corrupt_migration_does_not_commit_partial_state(self):
        before = self.state.path.read_bytes()
        (Path(self.temp.name) / 'config.json').write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            self.state.migrate_legacy()
        self.assertEqual(before, self.state.path.read_bytes())

    def test_newer_backend_protocol_rejected_without_mutation(self):
        data=json.loads(self.state.path.read_text());data['minimum_backend_protocol']=4
        self.state.path.write_text(json.dumps(data));before=self.state.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'backend protocol'):self.state.snapshot()
        self.assertEqual(self.state.path.read_bytes(),before)

    def test_legacy_mutation_during_migration_aborts_atomically(self):
        from unittest.mock import patch
        import managed_state
        root=Path(self.temp.name);source=root/'config.json'
        source.write_text(json.dumps({'kind':'local','instance':'first'}))
        before=self.state.path.read_bytes();original=managed_state.legacy_snapshot;calls=[]
        def changed(path):
            calls.append(path)
            if len(calls)==2:source.write_text(json.dumps({'kind':'local','instance':'changed'}))
            return original(path)
        with patch('managed_state.legacy_snapshot',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed during migration'):self.state.migrate_legacy()
        self.assertEqual(self.state.path.read_bytes(),before)
        self.assertTrue((self.state.root/'legacy-backup/config.json').exists())

    def test_new_legacy_file_during_migration_aborts_atomically(self):
        from unittest.mock import patch
        import managed_state
        before=self.state.path.read_bytes();original=managed_state.legacy_snapshot;calls=[]
        def changed(path):
            calls.append(path)
            if len(calls)==2:(path/'config.json').write_text('{}')
            return original(path)
        with patch('managed_state.legacy_snapshot',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed during migration'):self.state.migrate_legacy()
        self.assertEqual(self.state.path.read_bytes(),before)

    def test_brev_and_ssh_aliases_share_reservation_domain(self):
        ssh=self.state.register({'linux_machine_id_sha256':'same-host'},{'kind':'ssh'})['id']
        brev=self.state.register({'provider':'brev','organization_id':'org','instance_id':'id'},{'kind':'brev'})['id']
        self.state.bind_physical_identity(brev,{'linux_machine_id_sha256':'same-host'})
        self.state.reserve(ssh,'run1','run')
        with self.assertRaisesRegex(ValueError,'Physical machine busy'):self.state.reserve(brev,'run2','run')
        self.state.release(ssh,'run1','terminal evidence')
        self.state.reserve(brev,'run2','run')
        with self.assertRaisesRegex(ValueError,'Physical machine busy'):self.state.reserve(ssh,'run3','run')

    def test_late_identity_discovery_cannot_dispatch_competing_reservation(self):
        first=self.state.register({'provider':'brev','instance_id':'a'},{'kind':'brev'})['id']
        second=self.state.register({'provider':'brev','instance_id':'b'},{'kind':'brev'})['id']
        self.state.reserve(first,'run1','run');self.state.reserve(second,'run2','run')
        self.state.bind_physical_identity(first,{'linux_machine_id_sha256':'same-host'})
        with self.assertRaisesRegex(ValueError,'reserved through another'):
            self.state.bind_physical_identity(second,{'linux_machine_id_sha256':'same-host'})

    def test_physical_identity_change_is_not_accepted(self):
        machine=self.state.register({'linux_machine_id_sha256':'original'},{'kind':'ssh'})['id']
        before=self.state.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'identity changed'):
            self.state.bind_physical_identity(machine,{'linux_machine_id_sha256':'replacement'})
        self.assertEqual(self.state.path.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
