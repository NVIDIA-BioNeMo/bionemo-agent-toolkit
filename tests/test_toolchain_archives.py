import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_archives import verify_archives

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'gcc.deb';self.path.write_bytes(b'fixture')
        digest=hashlib.sha256(b'fixture').hexdigest()
        self.profile={'packages':{'gcc':{'Version':'11','Size':'7','SHA256':digest}}}
        self.transaction={'profile_sha256':hashlib.sha256(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'changes':{'gcc':{'actions':['Inst'],'version':'11','sha256':digest}}}
    def test_exact_archive_verified(self):
        self.assertEqual(verify_archives(self.profile,self.transaction,{'gcc':self.path})['gcc']['size'],7)
    def test_corruption_then_recovery(self):
        self.path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'):verify_archives(self.profile,self.transaction,{'gcc':self.path})
        self.path.write_bytes(b'fixture')
        self.assertIn('gcc',verify_archives(self.profile,self.transaction,{'gcc':self.path}))
    def test_missing_or_extra_package_rejected(self):
        for archives in ({},{'gcc':self.path,'extra':self.path}):
            with self.assertRaisesRegex(ValueError,'exactly match'):verify_archives(self.profile,self.transaction,archives)
    def test_symlink_rejected(self):
        link=self.path.with_name('link');link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,'regular file'):verify_archives(self.profile,self.transaction,{'gcc':link})
    def test_wrong_profile_rejected(self):
        self.transaction['profile_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'reviewed profile'):verify_archives(self.profile,self.transaction,{'gcc':self.path})
    def test_partial_download_rejected(self):
        self.path.write_bytes(b'fix')
        with self.assertRaisesRegex(ValueError,'size mismatch'):verify_archives(self.profile,self.transaction,{'gcc':self.path})
