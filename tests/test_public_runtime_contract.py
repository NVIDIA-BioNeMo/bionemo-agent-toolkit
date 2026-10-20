"""Public setup/probe boundary and the frozen inference contract."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import runtime_recipe
from generation import runtime_overrides
import test_runtime_recipe as legacy_tests

class PublicProbeContractTests(legacy_tests.RecipeTests):
    def setUp(self):
        super().setUp()
        self.temp.name=str(Path(self.temp.name).resolve())
        self.cfg['remote_root']=self.temp.name
        from public_model_bundle import MODEL_REVISION
        self.bundle=Path(self.temp.name)/'model-bundle';self.bundle.mkdir()
        weights=b'public fixture weights';digest=hashlib.sha256(weights).hexdigest()
        config=(json.dumps({'model_type':'rfd4_proteina','format_version':1,'config':{'autoencoder_config':{'nn_ae':{'present':True}}},'weights_sha256':digest})+'\n').encode()
        files=[{'name':n,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in [('config.json',config),('model.safetensors',weights)]]
        self.manifest={'repo_id':'nvidia/RFD4-Proteina','revision':MODEL_REVISION,'files':files}
        for name,body in [('config.json',config),('model.safetensors',weights)]: (self.bundle/name).write_bytes(body)
        (self.bundle/'.rfd4-public-bundle.json').write_text(json.dumps(self.manifest))
        self.cfg['weight_paths']=[str(self.bundle/f['name']) for f in files]
        self.recipe.pop('weights');self.recipe['model_bundle']=self.manifest
        source=runtime_recipe.BUNDLE_SOURCE
        start=source.index('BUNDLE_FILES = (');end=source.index('\nRECEIPT_NAME',start)
        source=source[:start]+'BUNDLE_FILES = '+repr(tuple(files))+'\n'+source[end:]
        self.public_probe=runtime_recipe.PROBE.replace(repr(runtime_recipe.BUNDLE_SOURCE),repr(source))
    def probe(self,*args,**kwargs):
        with patch('test_runtime_recipe.PROBE',self.public_probe):return super().probe(*args,**kwargs)
    def test_public_bundle_exact_contract_passes(self):self.assertTrue(self.probe()['checks']['weights'])
    def test_missing_receipt_fails_closed(self):
        (self.bundle/'.rfd4-public-bundle.json').unlink();self.assertFalse(self.probe()['checks']['weights'])
    def test_foreign_registration_does_not_retarget_bundle(self):
        self.cfg['weight_paths'][0]='/different/config.json';self.assertFalse(self.probe()['checks']['weights'])
    def test_recipe_manifest_drift_fails(self):
        self.recipe['model_bundle']['revision']='different';self.assertFalse(self.probe()['checks']['weights'])
    def test_symlink_bundle_fails(self):
        real=self.bundle.with_name('real-bundle');self.bundle.rename(real);self.bundle.symlink_to(real,target_is_directory=True)
        self.assertFalse(self.probe()['checks']['weights'])
    # Base legacy-checkpoint cases have their own original class; they do not
    # apply to this deliberately different fixture's two-file public bundle.
    def test_same_size_wrong_checkpoint_fails(self):
        (self.bundle/'model.safetensors').write_bytes(b'x'*len(b'public fixture weights'));self.assertFalse(self.probe()['checks']['weights'])
    def test_partial_checkpoint_fails(self):
        (self.bundle/'model.safetensors').write_bytes(b'partial');self.assertFalse(self.probe()['checks']['weights'])
    def test_valid_but_wrong_filename_fails(self):
        self.cfg['weight_paths'].reverse();self.assertFalse(self.probe()['checks']['weights'])

class FrozenPublicInferenceTests(unittest.TestCase):
    def test_public_inference_uses_exact_local_bundle_and_native_backend(self):
        from public_model_bundle import MODEL_REVISION
        args=runtime_overrides('/srv/rfd4-public')
        self.assertIn('hf_ckpt_path=/srv/rfd4-public/model-bundle',args)
        self.assertIn('hf_ckpt_revision='+MODEL_REVISION,args)
        self.assertIn('inference_backend=native',args);self.assertIn('~metrics',args)
        self.assertFalse(any('Private' in item or item.startswith('hf_ckpt_path=nvidia/') for item in args))
        for root in ('relative','/srv/../other'):
            with self.assertRaises(ValueError):runtime_overrides(root)
