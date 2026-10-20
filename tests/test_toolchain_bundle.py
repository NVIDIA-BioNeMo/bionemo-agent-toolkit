import hashlib,os,sys,tempfile,unittest,json
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_bundle as bundle

class BundlePublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'protected';self.base.mkdir()
        self.source=self.root/'source';self.source.mkdir()
        for name in bundle.BUNDLE_FILES:(self.source/name).write_text('# reviewed '+name)
        self.hashes={name:hashlib.sha256((self.source/name).read_bytes()).hexdigest() for name in bundle.BUNDLE_FILES}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        @contextmanager
        def fixture(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        def verify(path,hashes):
            self.assertEqual({p.name for p in Path(path).iterdir()},set(hashes))
            for name,digest in hashes.items():
                if hashlib.sha256((Path(path)/name).read_bytes()).hexdigest()!=digest:raise ValueError('Existing bundle differs')
        self.stack.enter_context(patch('toolchain_bundle.os.geteuid',return_value=0))
        self.stack.enter_context(patch('toolchain_bundle.protected_directory',fixture))
        self.stack.enter_context(patch('toolchain_bundle.verify_bundle',side_effect=verify))
    def go(self):return bundle.publish_bundle(self.base,self.source,self.hashes)
    def test_exact_files_published_and_repeat_reuses(self):
        result=self.go();self.assertFalse(result['reused'])
        self.assertTrue(self.go()['reused'])
        self.assertEqual(len(list(self.base.iterdir())),1)
        for file in Path(result['path']).iterdir():self.assertEqual(file.stat().st_mode&0o777,0o444)
    def test_changed_source_cannot_publish_partial_bundle(self):
        (self.source/'remote_job.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'differs'):self.go()
        self.assertEqual(list(self.base.iterdir()),[])
    def test_symlink_source_refused_without_publish(self):
        path=self.source/'remote_job.py';content=path.read_text();path.unlink()
        target=self.root/'elsewhere';target.write_text(content);path.symlink_to(target)
        with self.assertRaises(OSError):self.go()
        self.assertEqual(list(self.base.iterdir()),[])
    def test_existing_changed_bundle_not_overwritten(self):
        result=self.go();path=Path(result['path'])/'remote_job.py';path.chmod(0o644);path.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Existing bundle differs'):self.go()
        self.assertEqual(path.read_text(),'changed')
    def test_incomplete_manifest_has_no_effect(self):
        self.hashes.pop('remote_job.py')
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.go()
        self.assertEqual(list(self.base.iterdir()),[])
