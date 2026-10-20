"""Dedicated Brev execution has no privileged claim; historical owners stay binding."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import executor_ownership as scope
from service import Service


def proof():
    owner={'protocol':1,'executor_id':'a'*32,'controller_root_sha256':'b'*64,
           'linux_machine_id_sha256':'c'*64,'brev':None}
    return {'scope':'dedicated_brev_user','owner':owner,'owner_checksum':scope.checksum(owner),
            'brev':{'organization_id':'org','instance_id':'immutable'}}


class DedicatedScopeTests(unittest.TestCase):
    def test_inspection_of_absent_store_is_read_only_and_requires_no_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            absent=Path(directory)/'not-created'
            with patch.object(scope,'BASE',absent),patch.object(scope,'physical_identity',return_value='c'*64),patch.object(scope,'protected_directory',side_effect=FileNotFoundError):
                self.assertEqual(scope.require_execution_scope(proof())['state'],'unclaimed')
            self.assertFalse(absent.exists())
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_dedicated_mode_cannot_adopt_owned_pending_or_unknown_machine(self):
        for state in ['owned','pending','foreign','unknown']:
            with self.subTest(state=state),patch.object(scope,'inspect',return_value={'state':state}):
                with self.assertRaisesRegex(ValueError,'cannot replace'):
                    scope.require_execution_scope(proof())

    def test_historical_owner_proof_still_requires_committed_owner(self):
        historical=proof();historical.pop('scope')
        with patch.object(scope,'inspect',return_value={'state':'unclaimed'}):
            with self.assertRaisesRegex(ValueError,'not committed'):scope.require_execution_scope(historical)
        with patch.object(scope,'inspect',return_value={'state':'owned'}):
            self.assertEqual(scope.require_execution_scope(historical)['state'],'owned')

    def test_identity_checksum_or_provider_changes_fail_before_inspection(self):
        for field,value in [('scope','unknown'),('owner_checksum','f'*64),('brev',None),('brev',{'instance_id':'missing-org'})]:
            candidate=proof();candidate[field]=value
            with self.subTest(field=field,value=value),patch.object(scope,'inspect') as read:
                with self.assertRaises(ValueError):scope.require_execution_scope(candidate)
                read.assert_not_called()

    def test_physical_machine_change_refuses_even_when_marker_absent(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(scope,'BASE',Path(directory)/'absent'),patch.object(scope,'physical_identity',return_value='f'*64):
            with self.assertRaisesRegex(ValueError,'Machine identity changed'):scope.require_execution_scope(proof())

    def test_new_brev_binding_does_not_change_catalog_or_enable_privileged_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            service=Service(directory)
            service.register_compute('brev','saved','/home/ubuntu/rfd4','http://127.0.0.1',instance_id='immutable',organization_id='org',session_id='s')
            cfg=service.config('s');machine=cfg['target_id']
            service.managed.bind_physical_identity(machine,{'linux_machine_id_sha256':'c'*64})
            before=service.managed.snapshot()
            with patch.object(service,'verify_target'),patch.object(service,'ownership_status',return_value={'state':'unclaimed'}):
                binding=service.require_execution_scope(cfg)
                self.assertEqual(binding['scope'],'dedicated_brev_user')
                self.assertEqual(service.managed.snapshot(),before)
                with self.assertRaisesRegex(ValueError,'ownership claim'):
                    service.require_executor_ownership(cfg)
                historical=dict(binding);historical.pop('scope')
                with self.assertRaisesRegex(ValueError,'scope changed'):
                    service.require_execution_scope(cfg,historical)

    def test_runtime_migration_preserves_same_machine_access_and_physical_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            service=Service(directory)
            service.register_compute('brev','saved','/home/ubuntu/legacy','http://127.0.0.1',instance_id='immutable',organization_id='org',session_id='s')
            machine=service.config('s')['target_id'];state=service.managed
            # A previously accepted refresh snapshot, without any claim receipt.
            with state.transaction() as data:
                data['machines'][machine]['config']['ssh_access']={'alias':'saved','host':'bound-endpoint'}
                data['machines'][machine]['physical_identity']='c'*64
            revision=state.selection('s')['revision']
            service.register_compute('brev','saved','/home/ubuntu/public','http://127.0.0.1',instance_id='immutable',organization_id='org',session_id='s',expected_revision=revision)
            after=service.config('s')
            self.assertEqual(after['target_id'],machine)
            self.assertEqual(after['ssh_access'],{'alias':'saved','host':'bound-endpoint'})
            self.assertEqual(state.machine(machine)['physical_identity'],'c'*64)
            self.assertEqual(len(state.snapshot()['machines']),1)


if __name__=='__main__':unittest.main()
