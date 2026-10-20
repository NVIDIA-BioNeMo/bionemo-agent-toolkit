"""Public setup review and package-mutation boundary; no live GPU claims."""
import hashlib
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import public_prerequisite as prerequisite
import runtime_setup
from setup_operation import checksum

class PublicSetupContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.scripts=Path(prerequisite.__file__).parent
        self.recipe={'id':'public-test','install_mode':'public_wheels','model_revision':'fixed','source_hashes':{}}
        self.prereq=prerequisite.bind_review({'kind':'public_wheels','status':'ready','profile_sha256':prerequisite.profile_sha(),
            'installation_authorized':False,'changes':{},'download_bytes':0,'observation':{'platform':'Linux','architecture':'x86_64','libc':'glibc','libc_version':'2.35','driver_versions':['595.91.07']}})
        self.review={'operation_id':'test','action':'setup','remote_root':str(self.root),
            'recipe_id':self.recipe['id'],'recipe_checksum':checksum(self.recipe),'recipe':self.recipe,
            'files':prerequisite.helper_hashes(),'prerequisites':self.prereq}
    def validate(self):
        path=self.root/'review.json';path.write_text(json.dumps(self.review))
        return runtime_setup.validate_setup_review(path,checksum(self.review),self.root,'test',recipe=self.recipe,scripts=self.scripts)
    def test_public_review_binds_own_profile_and_source(self):
        self.assertEqual(self.validate(),self.review)
    def test_public_review_rejects_legacy_archive_phase(self):
        self.review['phase']='prepare_archives'
        with self.assertRaisesRegex(ValueError,'does not prepare'):self.validate()
    def test_public_review_rejects_mutations_and_missing_source_binding(self):
        self.review['prerequisites']=dict(self.prereq,changes={'gcc':'install'})
        with self.assertRaises(ValueError):self.validate()
        self.review['prerequisites']=self.prereq
        self.review['files']={'runtime_setup.py':hashlib.sha256(Path(runtime_setup.__file__).read_bytes()).hexdigest()}
        with self.assertRaisesRegex(ValueError,'differs from reviewed'):self.validate()
    def test_direct_setup_refuses_archive_phase_before_any_mutation(self):
        with self.assertRaisesRegex(ValueError,'does not prepare'):
            runtime_setup.setup(self.root,recipe=self.recipe,reviewed=dict(self.review,phase='prepare_archives'))
        self.assertFalse((self.root/'runtime-setup.json').exists())
    def test_public_setup_reaches_wheel_installer_without_package_coordinator(self):
        (self.root/'model').mkdir()
        with patch('runtime_setup.verify_source',return_value=True), patch('runtime_setup.install',side_effect=RuntimeError('wheel installer reached')) as install, patch('prerequisite_setup.install_prerequisites',side_effect=AssertionError('APT forbidden')) as apt:
            with self.assertRaisesRegex(RuntimeError,'wheel installer reached'):
                runtime_setup.setup(self.root,recipe=self.recipe,reviewed=self.review,operation_id='test',lock_path=self.root/'lock',run=lambda *a,**k:SimpleNamespace(stdout='fixed\n'),privileged=lambda *a: self.fail('sudo forbidden'))
        install.assert_called_once();apt.assert_not_called()
        journal=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertEqual(journal['prerequisites'],{'kind':'public_wheels','package_mutations':0,'requires_sudo':False})
        self.assertFalse(journal['ready'])
    def test_actual_frozen_public_payload_imports_in_isolation(self):
        from service import Service
        from ownership_test_support import assume_owned
        service=Service(str(self.root/'controller'))
        assume_owned(self,service,skip_transport_identity=False)
        verification=patch.object(service,'verify_target');verification.start();self.addCleanup(verification.stop)
        with patch.object(service,'verify_target'):
            service.register_compute('brev','demo','/srv/public-rfd4','http://127.0.0.1',instance_id='fixed',organization_id='org',session_id='demo')
        machine=service.config('demo')['target_id']
        operation=service.begin_setup('demo')['id']
        with patch.object(service,'review_prerequisites',return_value=self.prereq):
            review=service.prepare_runtime_setup(operation,machine)
        self.assertEqual(review['recipe']['install_mode'],'public_wheels')
        self.assertFalse(review['prerequisite_requires_sudo'])
        for name in ('generation.py','public_model_bundle.py','public_prerequisite.py'):
            self.assertIn(name,review['files'])
        frozen=service.state/operation/'setup-payloads'/review['review_checksum']
        isolated=self.root/'remote-payload'
        shutil.copytree(frozen,isolated)
        code="import sys; sys.path.insert(0,sys.argv[1]); import runtime_setup; runtime_setup.validate_setup_review(sys.argv[1]+'/setup-review.json',sys.argv[2],sys.argv[3],sys.argv[4]); print('copied public setup imports and validates')"
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(isolated),review['review_checksum'],review['remote_root'],operation],check=True,capture_output=True,text=True,cwd=self.root)
        self.assertIn('imports and validates',result.stdout)
        # This must detect precisely the staging omission found during migration.
        (isolated/'generation.py').unlink()
        missing=subprocess.run([sys.executable,'-I','-B','-c',code,str(isolated),review['review_checksum'],review['remote_root'],operation],capture_output=True,text=True,cwd=self.root)
        self.assertNotEqual(missing.returncode,0)
        self.assertIn('generation',missing.stderr)

if __name__=='__main__':unittest.main()
