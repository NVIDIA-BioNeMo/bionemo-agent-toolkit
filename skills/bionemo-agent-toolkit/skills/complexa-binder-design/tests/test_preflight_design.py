"""Offline regression coverage for PDB/chain preflight and the UniProt path."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import biotite.structure.io.pdb as pdb
import biotite.structure.io.pdbx as pdbx


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preflight_design.py"
SPEC = importlib.util.spec_from_file_location("preflight_design", SCRIPT)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def structure_text(partner=True, insertion=""):
    # Residue IDs are deliberately offset and shared across chains. Only B10
    # and B20 contact the partner; B30 is distant and must not become a hotspot.
    residues = [("B", 10, "ALA", 0.0, 0.0), ("B", 20, "GLY", 4.0, 0.0),
                ("B", 30, "SER", 30.0, 0.0)]
    if partner:
        residues.append(("A", 10, "ALA", 2.0, 3.0))
    lines = []
    for serial, (chain, resid, name, x, y) in enumerate(residues, 1):
        code = insertion if serial == 1 else ""
        lines.append(
            f"ATOM  {serial:5d} {'CA':^4s} {name:>3s} {chain}{resid:4d}{code:1s}   "
            f"{x:8.3f}{y:8.3f}{0.0:8.3f}{1.0:6.2f}{20.0:6.2f}           C  "
        )
    return "\n".join([*lines, "TER", "END", ""])


class TestPreflightDesign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "target.pdb"
        self.target.write_text(structure_text())

    def assert_interface(self, report):
        self.assertEqual(report["full_length"], 3)
        self.assertEqual(report["conditioned_length"], 3)
        self.assertEqual(report["chain"], "B")
        self.assertEqual(report["source"], "pdb_interface")
        self.assertEqual(report["final_hotspots"], ["B10(ALA)", "B20(GLY)"])
        self.assertTrue(all(passed for passed, _ in report["checks"].values()))

    def test_local_pdb_keeps_author_chain_numbering_and_partner_contacts(self):
        with patch.object(PREFLIGHT.P, "_run", side_effect=AssertionError("unexpected external helper")):
            self.assert_interface(PREFLIGHT.plan(str(self.target), chain="B"))

    def test_pdb_id_uses_rcsb_without_requiring_uniprot(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(structure_text().encode())) as fetch:
            with patch.object(PREFLIGHT.P, "_run", side_effect=AssertionError("unexpected UniProt lookup")):
                report = PREFLIGHT.plan("1BRS", chain="B")
        self.assertEqual(report["pdb"], "1BRS")
        fetch.assert_called_once_with("https://files.rcsb.org/download/1brs.pdb", timeout=120)
        self.assert_interface(report)

    def test_local_cif_uses_author_fields(self):
        array = pdb.PDBFile.read(io.StringIO(structure_text())).get_structure(model=1)
        cif = pdbx.CIFFile()
        pdbx.set_structure(cif, array)
        path = self.target.with_suffix(".cif")
        cif.write(path)
        self.assert_interface(PREFLIGHT.plan(str(path), chain="B"))

    def test_chain_choice_is_explicit_for_multichain_inputs(self):
        for chain, message in ((None, "select a target with --chain"), ("Z", "absent")):
            with self.subTest(chain=chain), self.assertRaisesRegex(ValueError, message):
                PREFLIGHT.plan(str(self.target), chain=chain)

    def test_single_chain_has_no_invented_interface_and_nonzero_cli_status(self):
        self.target.write_text(structure_text(partner=False))
        report = PREFLIGHT.plan(str(self.target))
        self.assertEqual(report["chain"], "B")
        self.assertEqual(report["n_hotspots"], 0)
        self.assertEqual(report["source"], "none")
        self.assertFalse(report["checks"][">=2_hotspots"][0])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(PREFLIGHT.main([str(self.target)]), 1)
        self.assertIn("NEEDS ATTENTION", output.getvalue())

    def test_insertion_codes_are_not_silently_merged_into_integer_hotspots(self):
        self.target.write_text(structure_text(insertion="A"))
        with self.assertRaisesRegex(ValueError, "insertion codes"):
            PREFLIGHT.plan(str(self.target), chain="B")

    def test_uniprot_accessibility_and_hotspot_path_still_works(self):
        model = pdb.PDBFile.read(io.StringIO(structure_text(partner=False))).get_structure(model=1)
        hotspots = [{"chain": "B", "position": p, "source": "uniprot"} for p in (10, 20)]

        def run(command, **kwargs):
            if str(PREFLIGHT.P.FETCH_STRUCTURE) in command:
                Path(command[-1], "AF-P04626-F1-model_v4.cif").touch()
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 0, json.dumps({"features": []}), "")

        with patch.object(PREFLIGHT.P, "_run", side_effect=run), \
             patch.object(PREFLIGHT, "_model", return_value=model), \
             patch.object(PREFLIGHT.HS, "resolve_hotspots", return_value=(hotspots, [(10, 20)], "uniprot", [])), \
             patch.object(PREFLIGHT.HS, "accessibility", return_value={"note": "extracellular"}):
            report = PREFLIGHT.plan("P04626")
        self.assertEqual(report["uniprot"], "P04626")
        self.assertEqual(report["conditioned_length"], 2)
        self.assertEqual(report["topology"], "extracellular")
        self.assertEqual(report["final_hotspots"], ["B10(ALA)", "B20(GLY)"])

    def test_cli_help_does_not_attempt_target_resolution(self):
        with patch.object(PREFLIGHT.P, "resolve_target_spec", side_effect=AssertionError("network")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as stopped:
                PREFLIGHT.main(["--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("--chain", output.getvalue())


if __name__ == "__main__":
    unittest.main()
