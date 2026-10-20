import contextlib
import hashlib
import io
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from runtime_recipe import PROBE

class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        (root/'model/.venv/bin').mkdir(parents=True)
        (root/'model/.venv/bin/rfd4-generate').write_text('entrypoint')
        (root/'model/.venv/bin/rfd4-generate').chmod(0o700)
        (root/'weight.ckpt').write_bytes(b'correct checkpoint')
        (root/'model/pyproject.toml').write_bytes(b'pinned source')
        self.cfg={'remote_root':str(root),'weight_paths':[str(root/'weight.ckpt')]}
        self.recipe={'id':'test','platform':'Linux','architecture':'x86_64','python_minor':list(sys.version_info[:2]),'python_version':'.'.join(map(str,sys.version_info[:3])),
                     'model_revision':'pinned','source_hashes':{'pyproject.toml':hashlib.sha256(b'pinned source').hexdigest()},
                     'packages':{'torch':'1.0'},'weights':[{'name':'weight.ckpt','size':18,'sha256':hashlib.sha256(b'correct checkpoint').hexdigest()}],
                     'minimum_gpu_memory_bytes':75,'minimum_compute_capability':[8,0]}
        self.gpu=SimpleNamespace(name='testGPU',total_memory=80)

    def probe(self, missing_dependency=False, installed_version='1.0'):
        cuda=SimpleNamespace(is_available=lambda:True,device_count=lambda:1,get_device_properties=lambda i:self.gpu,get_device_capability=lambda i:(8,0))
        out=io.StringIO()
        with patch.dict(sys.modules,{'torch':SimpleNamespace(cuda=cuda)}), patch('platform.system',return_value='Linux'), patch('platform.machine',return_value='x86_64'), patch('subprocess.check_output',side_effect=lambda args,**kwargs: b'100644 blob '+hashlib.sha1(b'blob 13\0pinned source').hexdigest().encode()+b'\tpyproject.toml\0' if 'ls-tree' in args else 'pinned'), patch('importlib.metadata.version',return_value=installed_version,side_effect=importlib.metadata.PackageNotFoundError('torch') if missing_dependency else None), patch.object(sys,'argv',['probe',json.dumps(self.cfg),json.dumps(self.recipe)]), contextlib.redirect_stdout(out):
            exec(PROBE,{})
        return json.loads(out.getvalue())

    def test_exact_recipe_passes(self):self.assertTrue(all(self.probe()['checks'].values()))
    def test_missing_dependency_returns_failed_check(self):
        self.assertFalse(self.probe(missing_dependency=True)['checks']['dependencies'])
    def test_non_executable_entrypoint_fails(self):
        (Path(self.temp.name)/'model/.venv/bin/rfd4-generate').chmod(0o600)
        self.assertFalse(self.probe()['checks']['entrypoint'])
    def test_same_size_wrong_checkpoint_fails(self):
        Path(self.cfg['weight_paths'][0]).write_bytes(b'x'*18)
        self.assertFalse(self.probe()['checks']['weights'])
    def test_partial_checkpoint_fails(self):
        Path(self.cfg['weight_paths'][0]).write_bytes(b'partial')
        self.assertFalse(self.probe()['checks']['weights'])
    def test_changed_source_fails(self):
        (Path(self.temp.name)/'model/pyproject.toml').write_text('changed')
        self.assertFalse(self.probe()['checks']['source'])
    def test_insufficient_gpu_fails(self):
        self.gpu.total_memory=40
        self.assertFalse(self.probe()['checks']['gpu'])
    def test_valid_but_wrong_filename_fails(self):
        self.recipe['weights'][0]['name']='other-release.ckpt'
        self.assertFalse(self.probe()['checks']['weights'])

    def test_different_cuda_build_is_rejected(self):
        self.recipe['packages']={'torch':'1.0+cu132'}
        self.assertFalse(self.probe(installed_version='1.0+cu128')['checks']['dependencies'])
    def test_wrong_python_patch_is_rejected(self):
        self.recipe['python_version']='3.12.9'
        self.assertFalse(self.probe()['checks']['python'])
    def test_readiness_inventory_matches_install_profile(self):
        from runtime_recipe import RECIPE
        from runtime_install import PROFILE
        self.assertEqual(RECIPE['packages'],dict(PROFILE['packages'],**{'rfd4-proteina':'0.0.1'}))
        self.assertEqual(RECIPE['dependency_lock_sha256'],PROFILE['lock_sha256'])
