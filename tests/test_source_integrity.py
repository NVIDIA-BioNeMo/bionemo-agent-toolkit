import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from source_integrity import verify_source

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'src').mkdir()
        (self.root/'src/model.py').write_text('pinned model\n')
        self.git('init','-q');self.git('add','src/model.py')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
        self.revision=self.git('rev-parse','HEAD').strip()
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],text=True,stderr=subprocess.DEVNULL)
    def test_exact_source(self):self.assertTrue(verify_source(self.root,self.revision))
    def test_changed_model_detected_even_with_assume_unchanged(self):
        self.git('update-index','--assume-unchanged','src/model.py')
        (self.root/'src/model.py').write_text('modified model\n')
        with self.assertRaisesRegex(ValueError,'differs'):verify_source(self.root,self.revision)
    def test_ignored_code_overlay_rejected(self):
        (self.root/'.git/info/exclude').write_text('src/injected.py\n')
        (self.root/'src/injected.py').write_text('injected')
        with self.assertRaisesRegex(ValueError,'Untracked'):verify_source(self.root,self.revision)
    def test_generated_config_requires_exact_digest(self):
        (self.root/'configs').mkdir();path=self.root/'configs/generated.yaml';path.write_bytes(b'known config')
        allowed={'configs/generated.yaml':hashlib.sha256(b'known config').hexdigest()}
        self.assertTrue(verify_source(self.root,self.revision,allowed))
        path.write_text('changed config')
        with self.assertRaises(ValueError):verify_source(self.root,self.revision,allowed)

    def test_root_and_bytecode_overlays_rejected(self):
        for relative in ('sitecustomize.py','src/model.pyc','src/__pycache__/model.cpython-312.pyc','lib/injected.pth'):
            with self.subTest(relative=relative):
                path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'injected')
                with self.assertRaisesRegex(ValueError,'Untracked'):verify_source(self.root,self.revision)
                path.unlink()

    def test_untracked_directory_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            (Path(external)/'injected.py').write_text('injected')
            (self.root/'src/overlay').symlink_to(external,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'directory link'):verify_source(self.root,self.revision)

    def test_tracked_parent_directory_symlink_rejected(self):
        (self.root/'src').rename(self.root/'original')
        (self.root/'src').symlink_to(self.root/'original',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'parent'):verify_source(self.root,self.revision)

    def test_executable_mode_mutation_rejected(self):
        (self.root/'src/model.py').chmod(0o755)
        with self.assertRaisesRegex(ValueError,'mode'):verify_source(self.root,self.revision)

    def test_managed_environment_is_not_source(self):
        (self.root/'.venv').mkdir()
        (self.root/'.venv/python').symlink_to('/usr/bin/python3')
        self.assertTrue(verify_source(self.root,self.revision))

    def test_traversal_error_cannot_be_reported_as_verified(self):
        from unittest.mock import patch
        def inaccessible(root,**kwargs):
            kwargs['onerror'](PermissionError('Cannot inspect runtime source'))
            return iter(())
        with patch('source_integrity.os.walk',side_effect=inaccessible):
            with self.assertRaises(PermissionError):verify_source(self.root,self.revision)
