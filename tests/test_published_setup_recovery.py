"""Execute copied prerequisite helper against its frozen review.

The sudo runner is simulated; source validation, ordinary execution lease and
operation-root receipt publication are real. This is not Linux privilege UAT.
"""
import hashlib,json,os,shlex,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from setup_operation import setup_expected,checksum
from execution_payload import publish_payload
from toolchain_process import BUNDLE_FILES
from ownership_test_support import assume_owned

DRIVER=r'''
import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
payload,lease,action,root,job,review,digest=sys.argv[1:]
sys.path.insert(0,payload)
import prerequisite_privileged as helper
assert str(Path(helper.__file__).parent)==payload
def privileged_boundary(args,**kwargs):
    request=json.loads(kwargs['input'])
    assert request['source_directory']==payload
    assert request['action']==action
    tx=request['transaction']
    assert tx['changes'],'The fixture must exercise a nonempty package transaction'
    result={'job_id':job,'transaction_sha256':hashlib.sha256(json.dumps(tx,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'state':'pending' if action=='observe' else 'failed'}
    if action=='recover':result.update(dispatch_not_started=True,preparation_error='fixture proves no installer dispatch')
    return SimpleNamespace(stdout=json.dumps(result))
result=helper.reconcile_reviewed_setup(action,root,job,review,digest,run=privileged_boundary,lease_path=Path(lease))
print(json.dumps(result))
'''


class PublishedSetupRecoveryTests(unittest.TestCase):
    def test_actual_payload_helper_validates_frozen_review_and_updates_only_mutable_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();service=Service(root/'controller')
            assume_owned(self,service,skip_transport_identity=True)
            runtime=root/'runtime'
            service.register_compute('brev','fixture',str(runtime),'http://127.0.0.1',instance_id='fixed',organization_id='fixture',session_id='s')
            machine=service.config('s')['target_id'];operation=service.begin_setup('s')['id']
            scripts=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'
            profile=json.loads((scripts/'toolchain_profile.json').read_text())
            package=next(iter(profile['packages']))
            tx={'changes':{package:{'version':profile['packages'][package]['Version'],'actions':['Inst','Conf']}},
                'download_bytes':int(profile['packages'][package]['Size']),'profile_sha256':checksum(profile),
                'helper_hashes':{name:hashlib.sha256((scripts/name).read_bytes()).hexdigest() for name in BUNDLE_FILES}}
            from runtime_recipe import RECIPE
            legacy={key:value for key,value in RECIPE.items() if key!='install_mode'}
            # Recovery must import the recipe frozen with this historical review,
            # not today's public recipe from the controller installation.
            legacy_scripts=root/'legacy-scripts'
            shutil.copytree(scripts,legacy_scripts)
            (legacy_scripts/'runtime_recipe.json').write_text(json.dumps(legacy))
            with patch('setup_operation.__file__',str(legacy_scripts/'setup_operation.py')),patch('setup_operation.RECIPE',legacy),patch.object(service,'review_prerequisites',return_value=tx):
                public=service.prepare_runtime_setup(operation,machine)
            review=service.managed.operation(operation)['review'];digest=public['review_checksum']
            local=service.state/operation/'setup-payloads'/digest
            remote=runtime/'setup-operations'/operation
            expected=setup_expected(review,digest)
            publish_payload(local,remote/'payload',expected['files'],expected['binding'])
            before={p.name:p.read_bytes() for p in (remote/'payload').iterdir()}
            intent={'job_id':operation,'transaction':tx,'transaction_sha256':checksum(tx)}
            (remote/'package-intent.json').write_text(json.dumps(intent))
            (remote/'package-dispatch.lock').touch()
            lease=root/'execution.lock';lease.touch();calls=[]
            def execute(cfg,command,**kwargs):
                args=shlex.split(command)
                self.assertEqual(args[2],str(remote/'payload/prerequisite_privileged.py'))
                self.assertEqual(args[6],str(remote/'payload/setup-review.json'))
                calls.append(args[3])
                completed=subprocess.run([sys.executable,'-B','-I','-c',DRIVER,str(remote/'payload'),str(lease),*args[3:]],
                    capture_output=True,text=True)
                self.assertEqual(completed.returncode,0,completed.stderr)
                return completed.stdout
            try:
                op=service.managed.operation(operation)
                with patch.object(service,'target_exec',side_effect=execute):
                    self.assertEqual(service.reconcile_setup_prerequisites(op,'observe')['state'],'pending')
                    self.assertFalse((remote/'package-stage.json').exists())
                    self.assertEqual(service.reconcile_setup_prerequisites(op,'recover')['state'],'failed')
                self.assertEqual(calls,['observe','recover'])
                receipt=json.loads((remote/'package-stage.json').read_text())
                self.assertTrue(receipt['dispatch_not_started']);self.assertEqual(receipt['job_id'],operation)
                self.assertEqual({p.name:p.read_bytes() for p in (remote/'payload').iterdir()},before)
                self.assertFalse((remote/'payload/package-stage.json').exists())
            finally:
                os.chmod(remote/'payload',0o700)


if __name__=='__main__':unittest.main()
