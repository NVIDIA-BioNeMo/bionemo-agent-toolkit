"""Dependency drift must stop the narrowly qualified editor adapter."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from editor_compat import verify_compatibility_sources

def changed_upstream():
    return 'different implementation'

class EditorCompatibilityTests(unittest.TestCase):
    def test_changed_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'dependency changed'):
            verify_compatibility_sources({'studio_combine':changed_upstream,'atomworks_concatenate':changed_upstream})

    def test_missing_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'dependency changed'):
            verify_compatibility_sources({})
