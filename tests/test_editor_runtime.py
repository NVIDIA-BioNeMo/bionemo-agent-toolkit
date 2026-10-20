"""Editor reuse is bound to the workspace and qualified adapter."""
import os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from editor_runtime import ensure_editor
from editor_identity import store_identity
from editor_compat import EXPECTED_SOURCE

class EditorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.service=SimpleNamespace(root=self.root,studio_url=lambda:'http://127.0.0.1:18769')
        self.health=httpx.Response(200,json={'version':'0.0.1'},request=httpx.Request('GET','http://localhost'))
        self.receipt={'adapter':'rfd4-editor-1','sources':EXPECTED_SOURCE,'store_identity':store_identity(self.root/'editor-sessions')}
    def response(self):return httpx.Response(200,json=self.receipt)
    def test_legacy_workspace_refuses_before_editor_lock_or_network(self):
        (self.root/'config.json').write_text('{}')
        from upgrade_state import inventory
        before=inventory(self.root)
        with patch('editor_runtime.httpx.get') as request,patch('editor_runtime.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError,'requires offline upgrade'):ensure_editor(self.service)
        request.assert_not_called();launch.assert_not_called()
        self.assertEqual(inventory(self.root),before)

    def test_editor_app_refuses_before_session_identity_creation(self):
        from editor_app import create_app
        (self.root/'config.json').write_text('{}')
        with patch.dict(os.environ,{'RFD4_STUDIO_HOME':str(self.root),
                'ANNOTATION_STUDIO_SESSION_DIR':str(self.root/'editor-sessions')},clear=True),patch('editor_app.store_identity') as owner:
            with self.assertRaisesRegex(ValueError,'requires offline upgrade'):create_app()
        owner.assert_not_called()
    def test_receipt_precedes_public_static_catchall_and_replaces_stale_registration(self):
        from editor_app import install_compatibility_route
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Route
        from starlette.testclient import TestClient
        async def static(request): return Response('static', status_code=404)
        app=Starlette(routes=[Route('/{path:path}', static)])
        install_compatibility_route(app,'first',EXPECTED_SOURCE)
        install_compatibility_route(app,'second',EXPECTED_SOURCE)
        client=TestClient(app)
        response=client.get('/rfd4/compatibility')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['store_identity'],'second')
        self.assertEqual(sum(r.name=='rfd4_compatibility' for r in app.routes),1)
        self.assertEqual(client.get('/missing').status_code,404)
        self.assertNotEqual(client.post('/rfd4/compatibility').status_code,200)

    def test_matching_editor_reused_even_without_python_setting(self):
        with patch.dict(os.environ,{},clear=True),patch('editor_runtime.httpx.get',side_effect=[self.health,self.response()]),patch('editor_runtime.subprocess.Popen') as launch:
            ensure_editor(self.service);launch.assert_not_called()
    def test_wrong_workspace_never_reused_or_replaced(self):
        self.receipt['store_identity']='wrong'
        with patch.dict(os.environ,{},clear=True),patch('editor_runtime.httpx.get',side_effect=[self.health,self.response()]),patch('editor_runtime.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError,'another workspace'):ensure_editor(self.service)
            launch.assert_not_called()
    def test_stale_adapter_rejected_without_python_setting(self):
        self.receipt['sources']={}
        with patch.dict(os.environ,{},clear=True),patch('editor_runtime.httpx.get',side_effect=[self.health,self.response()]):
            with self.assertRaisesRegex(ValueError,'compatibility adapter'):ensure_editor(self.service)
    def test_unreachable_editor_without_python_explains_setup(self):
        with patch.dict(os.environ,{},clear=True),patch('editor_runtime.httpx.get',side_effect=httpx.ConnectError('unreachable')):
            with self.assertRaisesRegex(ValueError,'RFD4_EDITOR_PYTHON'):ensure_editor(self.service)
    def test_start_uses_same_port_and_workspace_then_checks_receipt(self):
        process=Mock();process.poll.return_value=None
        with patch.dict(os.environ,{'RFD4_EDITOR_PYTHON':sys.executable},clear=True),patch('editor_runtime.httpx.get',side_effect=[httpx.ConnectError('down'),self.health,self.response()]),patch('editor_runtime.subprocess.Popen',return_value=process) as launch:
            ensure_editor(self.service)
            args,kwargs=launch.call_args
            self.assertEqual(args[0][-2:],['--port','18769'])
            self.assertEqual(kwargs['env']['ANNOTATION_STUDIO_SESSION_DIR'],str(self.root/'editor-sessions'))
            self.assertEqual(kwargs['env']['RFD4_STUDIO_HOME'],str(self.root))
    def test_failed_start_is_actionable(self):
        process=Mock();process.poll.return_value=1
        with patch.dict(os.environ,{'RFD4_EDITOR_PYTHON':sys.executable},clear=True),patch('editor_runtime.httpx.get',side_effect=httpx.ConnectError('down')),patch('editor_runtime.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(RuntimeError,'could not start'):ensure_editor(self.service)

    def test_slow_existing_editor_does_not_launch_replacement(self):
        with patch.dict(os.environ,{'RFD4_EDITOR_PYTHON':sys.executable},clear=True),patch('editor_runtime.httpx.get',side_effect=httpx.ReadTimeout('slow')),patch('editor_runtime.subprocess.Popen') as launch:
            with self.assertRaisesRegex(RuntimeError,'retry the connection'):ensure_editor(self.service)
            launch.assert_not_called()
        # A subsequent explicit check can reuse the original editor.
        with patch('editor_runtime.httpx.get',side_effect=[self.health,self.response()]),patch('editor_runtime.subprocess.Popen') as launch:
            ensure_editor(self.service);launch.assert_not_called()

    def test_wrong_version_on_occupied_port_never_replaced(self):
        other=httpx.Response(200,json={'version':'0.2.0'},request=httpx.Request('GET','http://localhost'))
        with patch('editor_runtime.httpx.get',return_value=other),patch('editor_runtime.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError,'unexpected service'):ensure_editor(self.service)
            launch.assert_not_called()
