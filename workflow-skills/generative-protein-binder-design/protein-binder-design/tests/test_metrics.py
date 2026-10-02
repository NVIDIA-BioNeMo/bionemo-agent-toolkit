# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Offline geometric fixtures for explicit PDB/mmCIF binder-chain handoffs."""
import io
import sys
import unittest
from pathlib import Path

import biotite.structure.io.pdb as pdb
import biotite.structure.io.pdbx as pdbx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from metrics import ca_rmsd_from_pdb, ca_rmsd_from_structures


def pdb_text(chains):
    lines = []
    for chain, coords in chains:
        for resid, (x, y, z) in enumerate(coords, 1):
            lines.append(f"ATOM  {len(lines)+1:5d}  CA  ALA {chain}{resid:4d}    "
                         f"{x:8.3f}{y:8.3f}{z:8.3f}{1.0:6.2f}{80.0:6.2f}           C  ")
    return "\n".join([*lines, "END", ""])


class StructureMetricTests(unittest.TestCase):
    def setUp(self):
        self.coords = [(0, 0, 0), (4, 0, 0), (0, 3, 0)]
        self.backbone = pdb_text([("D", self.coords)])
        rotated = [(8, 7, 0), (8, 11, 0), (5, 7, 0)]
        atoms = pdb.PDBFile.read(io.StringIO(pdb_text([("T", [(0, 0, 0)]), ("Y", rotated)]))).get_structure(model=1)
        cif = pdbx.CIFFile()
        pdbx.set_structure(cif, atoms)
        # Prediction label IDs differ from author IDs: the request named binder B.
        cif.block["atom_site"]["label_asym_id"] = pdbx.CIFColumn(["A", "B", "B", "B"])
        stream = io.StringIO()
        cif.write(stream)
        self.prediction = stream.getvalue()

    def test_cif_uses_requested_binder_chain_and_aligns_rigid_rotation(self):
        value = ca_rmsd_from_structures(self.backbone, self.prediction,
                                        backbone_chain="D", predicted_chain="B")
        self.assertAlmostEqual(value, 0.0, places=6)

    def test_missing_or_wrong_chain_does_not_produce_a_partial_rmsd(self):
        for chain in ("Y", "absent", "A"):
            with self.subTest(chain=chain), self.assertRaises(ValueError):
                ca_rmsd_from_structures(self.backbone, self.prediction,
                                        backbone_chain="D", predicted_chain=chain)

    def test_pdb_length_mismatch_is_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            ca_rmsd_from_pdb(self.backbone, pdb_text([("B", self.coords[:2])]), "D", "B")


if __name__ == "__main__":
    unittest.main()
