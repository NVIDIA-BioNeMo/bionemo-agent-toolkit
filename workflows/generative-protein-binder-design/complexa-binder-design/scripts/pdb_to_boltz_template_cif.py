#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Convert a target PDB to an mmCIF that the Boltz2 NIM accepts as a
`structural_templates` entry.

Boltz2's template parser (`boltz.data.parse.mmcif.parse_polymer`) does
`res_name = sequence[label_seq_id - 1]`, so the template mmCIF MUST have:
  * `_entity_poly_seq` / a populated canonical sequence (`full_sequence`), and
  * `_atom_site.label_seq_id` numbered 1..N for the polymer.

A plain `gemmi.Structure.make_mmcif_document()` from a PDB leaves
`label_seq_id` as `.` and the canonical sequence empty, which makes the NIM
raise `IndexError: list index out of range` ("Failed to parse input response").
This script populates both, then re-parses the result the same way Boltz does
to verify it before writing.

Usage:
  python pdb_to_boltz_template_cif.py target.pdb target.cif [--chain A]
"""
from __future__ import annotations

import argparse
import sys

import gemmi


def pdb_to_template_cif(pdb_path: str, chain_id: str) -> tuple[str, int]:
    st = gemmi.read_structure(pdb_path)
    st.setup_entities()
    if chain_id not in [c.name for c in st[0]]:
        raise SystemExit(f"chain {chain_id} not in {pdb_path} "
                         f"(have {[c.name for c in st[0]]})")
    poly = st[0][chain_id].get_polymer()
    names = [r.name for r in poly]
    if not names:
        raise SystemExit(f"chain {chain_id} has no polymer residues")
    # canonical sequence on the polymer entities, then contiguous label_seq
    for ent in st.entities:
        if ent.entity_type == gemmi.EntityType.Polymer:
            ent.full_sequence = names
    st.assign_label_seq_id()
    for i, res in enumerate(poly, start=1):
        res.label_seq = i
    return st.make_mmcif_document().as_string(), len(names)


def verify(cif: str, expected_len: int) -> None:
    """Re-parse the way Boltz does and assert the polymer is well-formed."""
    block = gemmi.cif.read_string(cif)[0]
    st2 = gemmi.make_structure_from_block(block)
    st2.setup_entities()
    polys = [e for e in st2.entities if e.entity_type == gemmi.EntityType.Polymer]
    if not polys or len(polys[0].full_sequence) != expected_len:
        raise SystemExit("verification failed: canonical sequence missing/short "
                         f"(got {len(polys[0].full_sequence) if polys else 0}, "
                         f"want {expected_len})")
    lsids = [r.label_seq for r in st2[0][0].get_polymer()]
    if any(x is None for x in lsids) or lsids[:1] != [1]:
        raise SystemExit(f"verification failed: label_seq not 1..N ({lsids[:3]}...)")


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
