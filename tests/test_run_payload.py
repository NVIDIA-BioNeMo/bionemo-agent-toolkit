"""Review-time freeze and isolated publication bootstrap contract tests."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import execution_adapter
import execution_payload
import run_payload
from executor_ownership import checksum


class RunPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.directory=self.root/'plan';self.directory.mkdir()
        self.content=b'data_frozen\n';(self.directory/'input.cif').write_bytes(self.content)
        self.snapshot={'snapshot_id':'a'*32,'sha256':hashlib.sha256(self.content).hexdigest()}
        owner={'protocol':1,'executor_id':'b'*32,'controller_root_sha256':'c'*64,'linux_machine_id_sha256':'d'*64,'brev':None}
        self.proof={'owner':owner,'owner_checksum':checksum(owner),'brev':None}
        self.target={'remote_root':'/srv/rfd4'}
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for folder,dirs,files in os.walk(self.root):os.chmod(folder,0o700)
        self.temp.cleanup()

    def freeze(self,**kwargs):
        return run_payload.freeze(self.directory,self.target,self.snapshot,2,777,{'thinking':'high'},self.proof,**kwargs)

    def test_freeze_retains_reviewed_script_input_and_helpers_when_original_changes(self):
        sources=self.root/'sources'
        original=Path(run_payload.__file__).parent
        sources.mkdir()
        for name in {module+'.py' for module in execution_adapter.MODULES}|{'remote_job.py','ownership_adapter.py'}:
            shutil.copyfile(original/name,sources/name)
        frozen=self.freeze(scripts=sources)
        (sources/'remote_job.py').write_text('changed package after review')
        directory=run_payload.verified(self.directory,frozen)
        self.assertEqual((directory/'input.cif').read_bytes(),self.content)
        self.assertEqual((directory/'remote_job.py').read_bytes(),(original/'remote_job.py').read_bytes())
        script=(directory/'run.sh').read_text()
        self.assertIn('/payload/input.cif',script);self.assertIn('num_replicates=2',script);self.assertIn('seed=777',script)
        self.assertIn('recycle_strategy=thinking_high',script)
        self.assertEqual(execution_adapter.manifest(frozen['publication_bundle']),frozen['publication_files'])

    def test_changed_frozen_file_or_manifest_refuses_before_transport(self):
        frozen=self.freeze();directory=self.directory/'execution-payload'
        (directory/'run.sh').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Frozen run payload changed'):run_payload.verified(self.directory,frozen)

    def test_changed_input_during_review_publishes_no_payload(self):
        (self.directory/'input.cif').write_text('different')
        with self.assertRaisesRegex(ValueError,'Input changed'):self.freeze()
        self.assertFalse((self.directory/'execution-payload').exists())
        self.assertEqual(list(self.directory.glob('.run-payload-*')),[])

    def test_isolated_bootstrap_uses_frozen_bundle_and_rejects_changed_digest(self):
        frozen=self.freeze();upload=self.directory/'execution-payload'
        bundle=json.loads(json.dumps(frozen['publication_bundle']))
        # Protected ownership cannot exist on this Mac. Replace only that
        # reviewed fixture module, explicitly NOT live ownership qualification.
        bundle['sources']['executor_ownership']='''import hashlib,json
def validate(value):return value
def checksum(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def inspect(value):return {'state':'owned'}
'''
        files=execution_adapter.manifest(bundle)
        expected=execution_payload.validate_manifest(frozen['files'],{'kind':'run','id':self.snapshot['snapshot_id'],
            'review_checksum':'e'*64,'executor_ownership':self.proof})
        destination=self.root/'remote'/'payload'
        command=execution_adapter.command(upload,destination,expected,self.snapshot['snapshot_id'],reviewed_bundle=bundle,reviewed_files=files)
        args=shlex.split(command);args[0]=sys.executable
        result=subprocess.run(args,check=True,capture_output=True,text=True)
        receipt=json.loads(result.stdout);self.assertEqual(receipt['path'],str(destination))
        execution_payload.verify_path(destination,expected)
        bundle['bootstrap']+='\nraise RuntimeError("changed")\n'
        with self.assertRaisesRegex(ValueError,'differs from accepted review'):
            execution_adapter.command(upload,destination,expected,self.snapshot['snapshot_id'],reviewed_bundle=bundle,reviewed_files=files)


if __name__=='__main__':unittest.main()
