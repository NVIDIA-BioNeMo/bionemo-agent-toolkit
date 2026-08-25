"""Regression tests for Boltz template residue labeling."""
from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

import biotite.structure.io.pdbx as pdbx


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pdb_to_boltz_template_cif.py"
SPEC = importlib.util.spec_from_file_location("pdb_to_boltz_template_cif", SCRIPT)
assert SPEC and SPEC.loader
CONVERTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONVERTER)


def _atom_line(serial: int, atom: str, resname: str, res_id: int,
               ins_code: str, x: float) -> str:
    element = atom.strip()[0]
    return (
        f"ATOM  {serial:5d} {atom:^4s} {resname:>3s} A{res_id:4d}{ins_code:1s}   "
        f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{20.0:6.2f}          {element:>2s}  "
    )


def _pdb_text(residues: list[tuple[int, str, str]]) -> str:
    rows: list[str] = []
    serial = 1
    for i, (res_id, ins_code, resname) in enumerate(residues):
        for atom, offset in (("N", 0.0), ("CA", 0.5)):
            rows.append(_atom_line(serial, atom, resname, res_id, ins_code,
                                   i * 2.0 + offset))
            serial += 1
    return "\n".join([*rows, "TER", "END", ""])


def _convert(residues: list[tuple[int, str, str]]) -> tuple[str, int]:
    with tempfile.TemporaryDirectory() as tmp:
        pdb_path = Path(tmp) / "target.pdb"
        pdb_path.write_text(_pdb_text(residues))
        return CONVERTER.pdb_to_template_cif(str(pdb_path), "A")


class TestPdbToBoltzTemplateCif(unittest.TestCase):
    def test_insertion_code_gets_distinct_label(self) -> None:
        cif, length = _convert([
            (10, "", "ALA"),
            (10, "A", "GLY"),
            (11, "", "SER"),
        ])

        CONVERTER.verify(cif, length)
        block = pdbx.CIFFile.read(io.StringIO(cif)).block
        labels = block["atom_site"]["label_seq_id"].as_array(str).tolist()
        self.assertEqual(labels, ["1", "1", "2", "2", "3", "3"])

    def test_verifier_rejects_internal_label_gap(self) -> None:
        cif, length = _convert([
            (1, "", "ALA"),
            (2, "", "GLY"),
            (2, "A", "SER"),
            (3, "", "THR"),
        ])
        parsed = pdbx.CIFFile.read(io.StringIO(cif))
        block = parsed.block
        labels = block["atom_site"]["label_seq_id"].as_array(str)
        labels[labels == "2"] = "3"
        block["atom_site"]["label_seq_id"] = labels
        malformed = io.StringIO()
        parsed.write(malformed)

        with self.assertRaisesRegex(SystemExit, "label_seq not 1..N"):
            CONVERTER.verify(malformed.getvalue(), length)


if __name__ == "__main__":
    unittest.main()
