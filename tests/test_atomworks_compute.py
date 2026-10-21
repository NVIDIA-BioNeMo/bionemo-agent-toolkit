import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from editor_app import validate_route

class ComputeContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.s=Service(self.tmp.name)
        from ownership_test_support import assume_owned
        assume_owned(self,self.s,skip_transport_identity=False)
        recipe=patch('runtime_recipe.inspect',side_effect=lambda backend,cfg: {'checks':dict.fromkeys(['platform','python','revision','source','dependencies','entrypoint','cuda','gpu'],True)|{'weights':bool(cfg['weight_paths'])},'gpus':[{'name':'A100','memory':80*1024**3}], 'details':[]})
        recipe.start();self.addCleanup(recipe.stop)
        machine_identity=patch('registry.linux_machine_identity', side_effect=lambda cfg, run: {'linux_machine_id_sha256': cfg.get('ssh_host', 'local-test-host')})
        machine_identity.start(); self.addCleanup(machine_identity.stop)
        identity=patch('registry.effective_access',side_effect=lambda alias,run: {'alias':alias,'host':alias})
        identity.start();self.addCleanup(identity.stop)
    def register(self,kind='ssh',**kw):
        return self.s.register_compute(kind,'gpu','/srv/rfd4','http://127.0.0.1:18764',ssh_host='gpu-alias',instance_id='id123',**kw)
    def test_registration_only_identifies_machine_without_provisioning(self):
        with patch.object(self.s,'run',side_effect=AssertionError('Must not execute')):
            self.assertEqual(self.register()['state'],'registered')
    def test_unregistered_is_explicit(self):
        self.assertEqual(self.s.compute_status()['state'],'unregistered')
    def test_ssh_uses_existing_noninteractive_host(self):
        self.register()
        with patch.object(self.s,'run',return_value='GPU') as run:
            self.s.target_exec(self.s.config(),'nvidia-smi')
            args=run.call_args.args[0]
            self.assertEqual(args[0],'ssh');self.assertIn('BatchMode=yes',args);self.assertEqual(args[-2:],[ 'gpu-alias','nvidia-smi'])
    def test_local_uses_local_execution(self):
        self.register('local')
        with patch.object(self.s,'run',return_value='GPU') as run:
            self.s.target_exec(self.s.config(),'nvidia-smi')
            self.assertEqual(run.call_args.args[0],['bash','-lc','nvidia-smi'])
    def test_probe_records_limits_and_invalidates_after_registration_changes(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='A100'),patch.object(self.s,'studio',return_value={}):
            self.assertEqual(self.s.check_compute()['state'],'needs_setup')
            self.register(weight_paths=['/weights/model.ckpt'])
            self.assertEqual(self.s.check_compute()['state'],'ready')
        self.register('local')
        self.assertEqual(self.s.compute_status()['state'],'registered')
    def test_invalid_remote_values_rejected(self):
        for host in ['-oProxyCommand=evil','x;echo bad','bad host']:
            with self.assertRaises(ValueError): self.s.register_compute('ssh','gpu','/srv/rfd4','http://127.0.0.1',ssh_host=host)
    def test_studio_proxy_is_not_general_http_proxy(self):
        for method,path in [('GET','https://example.com'),('POST','/api/v1/generate'),('GET','/api/v1/../../etc/passwd'),('GET','/api/v1/sessions/a/cif?url=https://example.com')]:
            with self.assertRaises(ValueError): validate_route(method,path)
        for method,path in [('GET','/api/v1/schema'),('POST','/api/v1/sessions'),('POST','/api/v1/sessions/-a/undo'),('GET','/api/v1/sessions/a/atom-distance?atom1=1&atom2=2')]:validate_route(method,path)

    def test_public_studio_import_inspection_and_temporary_cleanup_are_bounded(self):
        validate_route('POST','/api/v1/import/inspect')
        validate_route('POST','/api/v1/sessions/temporary_1/conditions/reset')
        validate_route('DELETE','/api/v1/sessions/temporary_1')
        for method,path in [('GET','/api/v1/import/inspect'),
                ('DELETE','/api/v1/sessions'),('DELETE','/api/v1/sessions/a/cif'),
                ('DELETE','/api/v1/sessions/a?recursive=true')]:
            with self.assertRaises(ValueError): validate_route(method,path)
