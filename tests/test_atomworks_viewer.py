"""Direct-viewer contract: no iframe, canonical selections, revision-bound edits."""
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/atomworks-studio/scripts'))
from service import Service
from preview import CSP

class Elements(HTMLParser):
    def __init__(self): super().__init__(); self.tags=[]
    def handle_starttag(self,tag,attrs): self.tags.append((tag,dict(attrs)))

class ViewerContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=Service(self.tmp.name)
    def test_bundled_page_needs_no_external_script_or_frame(self):
        asset=ROOT/'integrations/atomworks-studio/assets/studio-upstream.html'
        if not asset.exists(): self.skipTest('Private upstream frontend not built in this checkout')
        page=Elements();page.feed(asset.read_text())
        self.assertFalse(any(tag in ('iframe','object','embed') for tag,_ in page.tags))
        self.assertFalse(any(tag=='script' and 'src' in attrs for tag,attrs in page.tags))
        self.assertIn("frame-src 'none'",CSP)
        self.assertNotIn("'unsafe-eval'",CSP)
    def test_selection_uses_studio_residue_resolution(self):
        with patch.object(self.service,'studio',return_value={'atom_indices':[4,5,6]}) as api:
            result=self.service.resolve_selection('session',[5],'residue')
        self.assertEqual(result['atom_indices'],[4,5,6])
        api.assert_called_once_with('POST','sessions/session/selections/resolve',json={'atom_indices':[5],'scope':'residue'})
    def test_urlsafe_session_tokens_can_start_with_punctuation(self):
        with patch.object(self.service,'studio',return_value={'atom_indices':[0]}):
            for token in ('_session','-session'):
                self.assertEqual(self.service.resolve_selection(token,[0])['atom_indices'],[0])
        for token in ('../bad','bad/path','bad?query'):
            with self.assertRaises(ValueError): self.service.resolve_selection(token,[0])

    def test_condition_preserves_revision_guard(self):
        with patch.object(self.service,'studio',return_value={}) as api:
            self.service.set_condition('session',[4,5],'hotspot',True,7)
        self.assertEqual(api.call_args.kwargs['json']['expected_revision'],7)
        self.assertEqual(api.call_args.kwargs['json']['scope'],'atom')
    def test_invalid_atom_selection_does_not_reach_studio(self):
        for indices in ([],[-1],[True],[1.5]):
            with self.assertRaises(ValueError): self.service.resolve_selection('session',indices)
    def test_export_and_summary_must_be_same_revision(self):
        with patch.object(self.service,'studio',side_effect=[{'revision':1,'cif':'cif'},{'structure':{'revision':2}}]):
            with self.assertRaisesRegex(ValueError,'changed while loading'):
                self.service.viewer_payload({'session_id':'session','structure':{'revision':0}})
    def test_viewer_payload_has_cif_without_embed_url(self):
        with patch.object(self.service,'studio',return_value={'revision':1,'cif':'cif'}):
            result=self.service.viewer_payload({'session_id':'session','structure':{'revision':1},'editor_url':'old','editor_path':'old'})
        self.assertEqual(result['cif'],'cif');self.assertNotIn('editor_url',result)

if __name__=='__main__': unittest.main()
