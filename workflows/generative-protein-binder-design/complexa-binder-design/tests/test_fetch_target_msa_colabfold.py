"""Regression tests for ColabFold target-sequence extraction."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_target_msa_colabfold.py"
SPEC = importlib.util.spec_from_file_location("fetch_target_msa_colabfold", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _ca_line(record: str, serial: int, resname: str, res_id: int, chain: str) -> str:
    return (
        f"{record:<6s}{serial:5d}  CA  {resname:>3s} {chain}{res_id:4d}    "
        f"{0.0:8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{20.0:6.2f}          C   "
    )


def _write_pdb(tmp: str, lines: list[str]) -> str:
    pdb_path = Path(tmp) / "target.pdb"
    pdb_path.write_text("\n".join([*lines, "TER", "END", ""]))
    return str(pdb_path)


class TestSeqFromPdb(unittest.TestCase):
    def test_selenomethionine_is_kept_in_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdb_path = _write_pdb(tmp, [
                _ca_line("ATOM", 1, "ALA", 1, "A"),
                _ca_line("HETATM", 2, "MSE", 2, "A"),
                _ca_line("ATOM", 3, "GLY", 3, "A"),
            ])
            self.assertEqual(MODULE.seq_from_pdb(pdb_path, "A"), "AMG")

    def test_non_residue_hetatm_records_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdb_path = _write_pdb(tmp, [
                _ca_line("ATOM", 1, "ALA", 1, "A"),
                _ca_line("ATOM", 2, "GLY", 2, "A"),
                _ca_line("HETATM", 3, "CA", 3, "A"),   # Ca2+ ion, not a residue
                _ca_line("HETATM", 4, "HOH", 4, "A"),  # water
            ])
            self.assertEqual(MODULE.seq_from_pdb(pdb_path, "A"), "AG")


if __name__ == "__main__":
    unittest.main()
