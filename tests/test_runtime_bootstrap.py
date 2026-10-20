import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from runtime_bootstrap import bootstrap

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.wheel=self.root/'source.whl'
        with zipfile.ZipFile(self.wheel,'w') as z:
            z.writestr('release.data/scripts/uv',b'pinned-executable')
            z.writestr('../../must-not-extract',b'bad')
        self.spec={'url':'https://example.invalid/pinned.whl','size':self.wheel.stat().st_size,
                   'digests':{'sha256':hashlib.sha256(self.wheel.read_bytes()).hexdigest()},
                   'binary_member':'release.data/scripts/uv','binary_size':len(b'pinned-executable'),
                   'binary_sha256':hashlib.sha256(b'pinned-executable').hexdigest()}
    def download(self,url,dest,expected):dest.write_bytes(self.wheel.read_bytes())
    def test_only_verified_binary_is_published_and_reused(self):
        output=bootstrap(self.root/'tools',self.spec,self.download)
        self.assertEqual(output.read_bytes(),b'pinned-executable')
        self.assertEqual(output.stat().st_mode & 0o777,0o700)
        self.assertFalse((self.root/'must-not-extract').exists())
        self.assertEqual(bootstrap(self.root/'tools',self.spec,self.download),output)
    def test_modified_binary_and_archive_cannot_execute(self):
        wrong=dict(self.spec,binary_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'checksum'):bootstrap(self.root/'tools',wrong,self.download)
        self.assertFalse((self.root/'tools/uv').exists())
        wrong=dict(self.spec,digests={'sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'pinned release'):bootstrap(self.root/'tools',wrong,self.download)
    def test_existing_symlink_not_overwritten(self):
        tools=self.root/'tools';tools.mkdir();(tools/'uv').symlink_to(self.wheel)
        with self.assertRaisesRegex(ValueError,'symlink'):bootstrap(tools,self.spec,self.download)
        self.assertTrue((tools/'uv').is_symlink())
