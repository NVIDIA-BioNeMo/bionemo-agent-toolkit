"""The editor API is a bounded bridge, not a command or arbitrary HTTP proxy."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"integrations/atomworks-studio/scripts"))
from editor_app import request, validate_route

class EditorRouteTests(unittest.TestCase):
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

    def test_shipped_viewer_queries_reach_editor_unchanged(self):
        base_url = 'http://127.0.0.1:18769'
        service = SimpleNamespace(studio_url=lambda: base_url)
        for method, path in (
                ('POST', '/api/v1/sessions/a/validate?full=true'),
                ('GET', '/api/v1/sessions/a/bonds?atom_index=0'),
                ('GET', '/api/v1/sessions/a/atom-distance?atom1=1&atom2=2')):
            with self.subTest(method=method, path=path):
                received = []
                def editor(incoming):
                    received.append(incoming)
                    return httpx.Response(200, json={'ok': True})
                client = httpx.Client(base_url=base_url, transport=httpx.MockTransport(editor))
                with patch('editor_app.ensure_editor'), patch('editor_app.httpx.Client', return_value=client):
                    result = request(service, method, path)
                self.assertEqual(result['status'], 200)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0].method, method)
                self.assertEqual(str(received[0].url), base_url + path)

    def test_unsupported_queries_are_rejected_before_editor_access(self):
        for method, path in (
                ('POST', '/api/v1/sessions/a/validate?full=true&unexpected=1'),
                ('GET', '/api/v1/sessions/a/bonds?atom_index=0&unexpected=1'),
                ('GET', '/api/v1/sessions/a/atom-distance?atom1=1&atom2=2&unexpected='),
                ('POST', '/api/v1/sessions/a/bonds?atom_index=0'),
                ('GET', '/api/v1/sessions/a/bonds?full=true'),
                ('POST', '/api/v1/sessions/a/conditions?full=true'),
                ('GET', '/api/v1/sessions/a/annotations/bonds?atom_index=0')):
            with self.subTest(method=method, path=path), patch('editor_app.ensure_editor') as ensure:
                with self.assertRaisesRegex(ValueError, 'Unsupported Studio query'):
                    request(None, method, path)
                ensure.assert_not_called()
