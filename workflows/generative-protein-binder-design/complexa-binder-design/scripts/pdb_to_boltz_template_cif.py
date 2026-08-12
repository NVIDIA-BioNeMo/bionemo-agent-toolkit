#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Convert a target PDB to an mmCIF that the Boltz2 NIM accepts as a
`structural_templates` entry.

Boltz2's template parser (`boltz.data.parse.mmcif.parse_polymer`) does
`res_name = sequence[label_seq_id - 1]`, so the template mmCIF MUST have:
  * `_entity_poly_seq` (the canonical monomer sequence, one row per residue), and
  * `_atom_site.label_seq_id` numbered 1..N for the polymer.

A structure written straight from a PDB leaves `label_seq_id` as `.` and the
canonical sequence empty, which makes the NIM raise
`IndexError: list index out of range` ("Failed to parse input response").
This script populates both explicitly with biotite, then re-parses the result to
verify it before writing.

Usage:
  python pdb_to_boltz_template_cif.py target.pdb target.cif [--chain A]
"""
from __future__ import annotations

import argparse
import io
import sys

_AA3to1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M",
}


def pdb_to_template_cif(pdb_path: str, chain_id: str) -> tuple[str, int]:
    import numpy as np
    import biotite.structure as struc
    import biotite.structure.io.pdb as pdb
    import biotite.structure.io.pdbx as pdbx

    arr = pdb.PDBFile.read(pdb_path).get_structure(model=1)
    if chain_id not in set(str(c) for c in arr.chain_id):
        have = list(dict.fromkeys(str(c) for c in arr.chain_id))
        raise SystemExit(f"chain {chain_id} not in {pdb_path} (have {have})")
    chain = arr[arr.chain_id == chain_id]

    # Polymer (amino-acid) residues of the chain, in order → canonical sequence.
    names: list[str] = []
    label_of: dict[int, int] = {}   # auth res_id -> contiguous label_seq 1..N
    for s in struc.get_residue_starts(chain):
        rn = str(chain.res_name[s]).upper()
        if rn in _AA3to1:
            label_of[int(chain.res_id[s])] = len(names) + 1
            names.append(rn)
    if not names:
        raise SystemExit(f"chain {chain_id} has no polymer residues")

    # atom_site written by biotite, then label_seq_id / entity columns patched so
    # the polymer is numbered 1..N (hetero atoms, if any, keep '.').
    block = pdbx.CIFBlock()
    pdbx.set_structure(block, chain)
    atom_site = block["atom_site"]
    lseq, ent = [], []
    for rid in chain.res_id:
        i = label_of.get(int(rid))
        lseq.append(str(i) if i is not None else ".")
        ent.append("1" if i is not None else ".")
    atom_site["label_seq_id"] = np.array(lseq)
    atom_site["label_entity_id"] = np.array(ent)

    # Canonical sequence: _entity_poly_seq (what Boltz indexes) + _entity_poly.
    one = "".join(_AA3to1.get(n, "X") for n in names)
    block["entity"] = pdbx.CIFCategory({"id": ["1"], "type": ["polymer"]})
    block["entity_poly"] = pdbx.CIFCategory({
        "entity_id": ["1"],
        "type": ["polypeptide(L)"],
        "pdbx_seq_one_letter_code": [one],
        "pdbx_seq_one_letter_code_can": [one],
    })
    block["entity_poly_seq"] = pdbx.CIFCategory({
        "entity_id": ["1"] * len(names),
        "num": [str(i) for i in range(1, len(names) + 1)],
        "mon_id": names,
        "hetero": ["n"] * len(names),
    })

    cif = pdbx.CIFFile()
    cif["target"] = block
    sio = io.StringIO()
    cif.write(sio)
    return sio.getvalue(), len(names)


def verify(cif: str, expected_len: int) -> None:
    """Re-parse and assert the polymer is well-formed the way Boltz needs it:
    canonical sequence of the right length + contiguous label_seq_id 1..N."""
    import biotite.structure.io.pdbx as pdbx
    block = pdbx.CIFFile.read(io.StringIO(cif)).block

    eps = block.get("entity_poly_seq")
    mon = list(eps["mon_id"].as_array(str)) if eps is not None else []
    if len(mon) != expected_len:
        raise SystemExit("verification failed: canonical sequence missing/short "
                         f"(got {len(mon)}, want {expected_len})")

    lsids = [x for x in block["atom_site"]["label_seq_id"].as_array(str) if x != "."]
    nums = sorted({int(x) for x in lsids})
    if not nums or nums[0] != 1 or nums[-1] != expected_len:
        raise SystemExit("verification failed: label_seq not 1..N "
                         f"(got {nums[:3]}..{nums[-1:]}, want 1..{expected_len})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdb")
    ap.add_argument("cif_out")
    ap.add_argument("--chain", default="A", help="target chain ID (default A)")
    args = ap.parse_args()

    cif, n = pdb_to_template_cif(args.pdb, args.chain)
    verify(cif, n)
    with open(args.cif_out, "w") as fh:
        fh.write(cif)
    print(f"wrote {args.cif_out} ({len(cif)} chars); chain {args.chain}, {n} residues; "
          f"verified label_seq 1..{n} + canonical sequence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
