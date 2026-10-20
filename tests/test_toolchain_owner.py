import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_owner as owner
import toolchain_paths as paths

class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.tx={'changes':{}}
        self.digest=hashlib.sha256(json.dumps(self.tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def publish(self,job='job',digest=None):
        @contextmanager
        def fixture(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        with patch('toolchain_owner.os.geteuid',return_value=0),patch('toolchain_owner.protected_directory',side_effect=fixture),patch('toolchain_owner.transaction_directory',side_effect=lambda fd,name:paths.transaction_directory(fd,name,owner_uid=os.getuid())),patch('toolchain_owner.read_record',side_effect=lambda fd,name:paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_owner.write_record',side_effect=lambda fd,name,value:paths.write_record(fd,name,value,owner_uid=os.getuid())):
            return owner.publish(self.root,job,self.tx,digest or self.digest)
    def test_exact_retry_reuses_original_owner(self):
        self.assertFalse(self.publish()['reused'])
        self.assertTrue(self.publish()['reused'])
    def test_other_operation_cannot_replace_pending_owner(self):
        self.publish();before=(self.root/'package-owner.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'reconciled'):self.publish('other')
        self.assertEqual((self.root/'package-owner.json').read_bytes(),before)
    def test_changed_review_cannot_publish(self):
        with self.assertRaisesRegex(ValueError,'checksum'):self.publish(digest='wrong')
        self.assertFalse((self.root/'package-owner.json').exists())
    def test_crash_after_intent_can_finish_owner_publication(self):
        directory=self.root/'job';directory.mkdir()
        (directory/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'job','transaction':self.tx,'transaction_sha256':self.digest}))
        self.assertTrue(self.publish()['reused'])
        self.assertEqual(json.loads((self.root/'package-owner.json').read_text())['job_id'],'job')

    def test_old_unpublished_intent_cannot_replace_later_terminal_owner(self):
        directory=self.root/'old';directory.mkdir()
        (directory/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'old','transaction':self.tx,'transaction_sha256':self.digest}))
        self.publish('new')
        (self.root/'new'/'package-dispatch.lock').touch()
        (self.root/'new'/'package-stage.json').write_text(json.dumps({'job_id':'new','transaction_sha256':self.digest,'state':'failed','dispatch_not_started':True,'preparation_error':'no dispatch'}))
        with self.assertRaisesRegex(ValueError,'superseded'):self.publish('old')
        self.assertEqual(json.loads((self.root/'package-owner.json').read_text())['job_id'],'new')
