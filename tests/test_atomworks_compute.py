"""The editor API is a bounded bridge, not a command or arbitrary HTTP proxy."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"integrations/atomworks-studio/scripts"))
from editor_app import validate_route

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
