import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import runtime_install as installer

class LockedInstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);(self.root/'model').mkdir()
  self.profile=dict(installer.PROFILE,packages={'torch':'2.14.1+cu132'})
  scaffold=patch.object(installer,'scaffold');scaffold.start();self.addCleanup(scaffold.stop)
  self.commands=[]
  self.toolchain=patch.object(installer,'verify_toolchain',return_value={'paths':{'gcc':'/usr/bin/gcc','g++':'/usr/bin/g++','nvcc':'/usr/local/cuda-13.2/bin/nvcc'},'versions':{}})
  self.toolchain.start();self.addCleanup(self.toolchain.stop)
 def fake_run(self,args,**kwargs):
  self.commands.append((args,kwargs))
  if 'import platform; print(platform.python_version())' in args:return Mock(stdout='3.12.10\n')
  if len(args)>2 and args[1]=='-c':return Mock(stdout=json.dumps({'torch':'2.14.1+cu132','tmol':'0.1.64','tmol-ops-cu13':'0.1.64'}))
  return Mock(stdout='')
 def test_lock_is_enforced_and_native_tmol_uses_only_hashed_wheels(self):
  with patch.object(installer,'bootstrap',return_value=self.root/'uv'):
   result=installer.install(self.root,profile=self.profile,run=self.fake_run,download=Mock())
  sync=next((a,k) for a,k in self.commands if 'sync' in a)
  self.assertIn('--require-hashes',sync[0]);self.assertIn('--build-constraints',sync[0])
  self.assertNotIn('TMOL_FORCE_BUILD',sync[1]['env'])
  self.assertIn('--only-binary',sync[0])
  self.assertIn('tmol,tmol-ops-cu13',sync[0])
  self.assertFalse(any('tmol-0.1.' in str(a) for a,k in self.commands))
  self.assertTrue(all('--no-config' in a for a,k in self.commands if a[0]==str(self.root/'uv')))
  self.assertEqual(result['packages']['tmol'],'0.1.64')
 def test_wrong_lock_refuses_before_bootstrap(self):
  with patch.object(installer,'bootstrap') as boot:
   with self.assertRaisesRegex(ValueError,'lock checksum'):installer.install(self.root,profile=dict(self.profile,lock_sha256='wrong'),run=self.fake_run)
   boot.assert_not_called()
 def test_native_compilers_are_not_required_or_inherited(self):
  download=Mock()
  with patch.object(installer,'verify_toolchain',side_effect=ValueError('not needed')),patch.object(installer,'bootstrap',return_value=self.root/'uv'),patch.dict('os.environ',{'TMOL_FORCE_BUILD':'1'}):
   installer.install(self.root,profile=self.profile,run=self.fake_run,download=download)
  download.assert_not_called()
  self.assertTrue(all('TMOL_FORCE_BUILD' not in k.get('env',{}) for a,k in self.commands))
 def test_unsupported_install_mode_refuses_before_bootstrap(self):
  with patch.object(installer,'bootstrap') as boot:
   with self.assertRaisesRegex(ValueError,'installation mode'):
    installer.install(self.root,profile=dict(self.profile,install_mode='legacy_sdist'),run=self.fake_run)
   boot.assert_not_called()
 def test_wrong_python_refuses_dependency_changes(self):
  def run(args,**kwargs):
   self.commands.append(args)
   return Mock(stdout='3.12.9')
  with patch.object(installer,'bootstrap',return_value=self.root/'uv'):
   with self.assertRaisesRegex(ValueError,'Python version'):installer.install(self.root,profile=self.profile,run=run,download=Mock())
  self.assertFalse(any('sync' in args for args in self.commands))

class ToolchainTests(unittest.TestCase):
 def test_missing_compiler_fails_without_executing_anything(self):
  runner=Mock()
  with self.assertRaisesRegex(ValueError,r'g\+\+'):
   installer.verify_toolchain(run=runner,which=lambda name:None if name=='g++' else '/bin/'+name)
  runner.assert_not_called()
 def test_wrong_cuda_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'CUDA compiler 13.2'):
   installer.verify_toolchain(run=Mock(return_value=Mock(stdout='release 12.8,')),which=lambda name:'/bin/'+name)
 def test_matching_cuda_records_evidence(self):
  result=installer.verify_toolchain(run=Mock(return_value=Mock(stdout='release 13.2, V13.2')),which=lambda name:'/bin/'+name)
  self.assertEqual(result['paths']['nvcc'],'/bin/nvcc')

 def test_official_cuda_path_is_found_outside_path(self):
  def which(name):
   if name=='nvcc':return None
   return name if name.startswith('/') else '/usr/bin/'+name
  result=installer.verify_toolchain(run=Mock(return_value=Mock(stdout='release 13.2, V13.2')),which=which)
  self.assertEqual(result['paths']['nvcc'],'/usr/local/cuda-13.2/bin/nvcc')

class ScaffoldTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);(self.root/'scripts').mkdir()
  self.content=(Path(__file__).parent/'fixtures/runtime-custom-metrics.yaml').read_text()
  (self.root/'scripts/setup_venv.sh').write_text("cat << 'EOF'\n"+self.content+"EOF\n")
  (self.root/'.env.local.example').write_text('DATA_PATH=example\n')
 def test_canonical_scaffold_is_repeatable_and_preserves_environment(self):
  installer.scaffold(self.root)
  env=self.root/'.env.local'
  self.assertEqual(env.stat().st_mode&0o777,0o600)
  env.write_text('DATA_PATH=existing\n')
  installer.scaffold(self.root)
  self.assertEqual(env.read_text(),'DATA_PATH=existing\n')
  self.assertEqual((self.root/'configs/metrics/custom_metrics/all_custom_metrics.yaml').read_text(),self.content)
 def test_modified_scaffold_is_not_overwritten(self):
  installer.scaffold(self.root)
  target=self.root/'configs/metrics/custom_metrics/all_custom_metrics.yaml'
  target.write_text('changed')
  with self.assertRaisesRegex(ValueError,'Existing metrics scaffold'):installer.scaffold(self.root)
  self.assertEqual(target.read_text(),'changed')
 def test_changed_upstream_template_is_rejected_before_writes(self):
  (self.root/'scripts/setup_venv.sh').write_text("cat << 'EOF'\nchanged\nEOF\n")
  with self.assertRaisesRegex(ValueError,'Upstream metrics scaffold'):installer.scaffold(self.root)
  self.assertFalse((self.root/'configs').exists())

class PublicDependencyProfileTests(unittest.TestCase):
 def test_public_profile_matches_hashed_lock_and_native_artifacts(self):
  import hashlib,re
  profile=installer.PROFILE
  self.assertEqual(profile['install_mode'],'public_wheels')
  self.assertEqual(hashlib.sha256(installer.LOCK.read_bytes()).hexdigest(),profile['lock_sha256'])
  parsed=dict(re.findall(r'^([\w-]+)(?:\[[^]]+\])?==([^ \\\n;]+)',installer.LOCK.read_text(),re.M))
  self.assertEqual(parsed,profile['packages'])
  self.assertEqual(parsed['atomworks'],'3.0.4')
  self.assertEqual(parsed['huggingface-hub'],'1.33.0')
  self.assertEqual(parsed['cuequivariance'],'0.13.0')
  self.assertNotIn('bionemo-ir',parsed)
  self.assertNotIn('ipykernel',parsed)
  for name in ('tmol','tmol-ops-cu13'):
   artifact=profile['native_wheel_artifacts'][name]
   self.assertIn('cp312-cp312-manylinux_2_28_x86_64.whl',artifact['filename'])
   self.assertIn('--hash=sha256:'+artifact['sha256'],installer.LOCK.read_text())
