import os,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_paths import transaction_directory,protected_directory

class ProtectedPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.fd)
    def test_create_and_reopen_same_protected_inode(self):
        with transaction_directory(self.fd,'operation',owner_uid=os.getuid()) as fd:first=os.fstat(fd).st_ino
        with transaction_directory(self.fd,'operation',owner_uid=os.getuid()) as fd:self.assertEqual(os.fstat(fd).st_ino,first)
    def test_symlink_transaction_refused(self):
        other=self.root/'other';other.mkdir();(self.root/'operation').symlink_to(other)
        with self.assertRaises(OSError):
            with transaction_directory(self.fd,'operation',owner_uid=os.getuid()):pass
    def test_world_writable_base_refused(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            with transaction_directory(self.fd,'operation',owner_uid=os.getuid()):pass
        self.assertFalse((self.root/'operation').exists())
    def test_path_injection_refused(self):
        for value in ('../escape','/absolute','a/b','.'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                with transaction_directory(self.fd,value,owner_uid=os.getuid()):pass
    def test_existing_writable_transaction_refused(self):
        (self.root/'operation').mkdir(mode=0o777);(self.root/'operation').chmod(0o777)
        with self.assertRaises(ValueError):
            with transaction_directory(self.fd,'operation',owner_uid=os.getuid()):pass
    def test_root_directory_can_be_inspected_without_mutation(self):
        with protected_directory('/') as fd:self.assertEqual(os.fstat(fd).st_uid,0)
    def test_relative_and_parent_paths_refused(self):
        for value in ('relative','/var/../tmp'):
            with self.assertRaises(ValueError):
                with protected_directory(value):pass

    def test_receipt_write_replaces_symlink_without_following_it(self):
        import json
        from toolchain_paths import write_record
        outside=self.root/'outside';outside.write_text('preserve')
        with transaction_directory(self.fd,'operation',owner_uid=os.getuid()) as fd:
            (self.root/'operation'/'stage.json').symlink_to(outside)
            write_record(fd,'stage.json',{'state':'running'},owner_uid=os.getuid())
        self.assertEqual(outside.read_text(),'preserve')
        self.assertEqual(json.loads((self.root/'operation'/'stage.json').read_text()),{'state':'running'})
        self.assertFalse((self.root/'operation'/'stage.json').is_symlink())
