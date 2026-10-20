"""Real CPU parser checks; run with the Studio/Biotite environment."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from runtime_smoke import VALIDATE

@unittest.skipUnless(importlib.util.find_spec('biotite'), 'Requires the Studio Biotite environment')
class SmokeParserTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.output=self.root/'output';self.output.mkdir()
    def make_cif(self,finite=True):
        import biotite.structure as structure
        from biotite.structure.io.pdbx import CIFFile,set_structure
        atoms=structure.AtomArray(1)
        atoms.coord[:]=[[1,2,3] if finite else [float('nan'),2,3]]
        atoms.chain_id[:]='A';atoms.res_id[:]=1;atoms.res_name[:]='GLY'
        atoms.atom_name[:]='CA';atoms.element[:]='C';atoms.hetero[:]=False
        cif=CIFFile();set_structure(cif,atoms);cif.write(self.output/'design.cif')
    def validate(self):
        return subprocess.run([sys.executable,'-c',VALIDATE,str(self.output)],capture_output=True,text=True)
    def test_real_cif_is_parsed_and_hashed(self):
        self.make_cif();result=self.validate()
        self.assertEqual(result.returncode,0,result.stderr)
        evidence=json.loads(result.stdout)['structures'][0]
        self.assertEqual(evidence['atoms'],1);self.assertEqual(len(evidence['sha256']),64)
    def test_nonfinite_coordinates_fail(self):
        self.make_cif(False);self.assertNotEqual(self.validate().returncode,0)
    def test_missing_output_fails(self):
        self.assertNotEqual(self.validate().returncode,0)
    def test_malformed_output_fails(self):
        (self.output/'design.cif').write_text('not a structure')
        self.assertNotEqual(self.validate().returncode,0)
    def test_symlink_output_fails(self):
        self.make_cif();(self.output/'design.cif').rename(self.root/'external.cif')
        (self.output/'design.cif').symlink_to(self.root/'external.cif')
        self.assertNotEqual(self.validate().returncode,0)
