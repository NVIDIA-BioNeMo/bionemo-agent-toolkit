# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Dependency-free PDB parsing helpers for binder-design handoffs.

Covers the fragile glue between NIM steps:
- extract a chain, keep ATOM records
- one-letter sequence from CA atoms
- map PDB author residue numbers -> 1-based sequence index (hotspot/pocket remap)
- CA coordinates for RMSD
"""
from __future__ import annotations

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M", "SEC": "U", "PYL": "O",
}


def _iter_atom_lines(pdb_text, chain=None):
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if len(line) < 54:
            continue
        if chain is not None and line[21] != chain:
            continue
        yield line


def extract_chain(pdb_text, chain):
    """Return PDB text containing only records for ``chain``."""
    keep = []
    for line in pdb_text.splitlines():
        if line.startswith(("ATOM", "HETATM", "TER")) and len(line) > 21 and line[21] == chain:
            keep.append(line)
    return "\n".join(keep)


def ca_residues(pdb_text, chain=None):
    """Ordered list of (resName, resSeq, iCode, (x, y, z)) for CA atoms."""
    out = []
    for line in _iter_atom_lines(pdb_text, chain):
        if line[12:16].strip() != "CA":
            continue
        res_name = line[17:20].strip()
        res_seq = int(line[22:26])
        icode = line[26].strip()
        x = float(line[30:38]); y = float(line[38:46]); z = float(line[46:54])
        out.append((res_name, res_seq, icode, (x, y, z)))
    return out


def sequence(pdb_text, chain=None):
    """One-letter sequence from CA atoms (unknown residues -> 'X')."""
    return "".join(THREE_TO_ONE.get(r[0], "X") for r in ca_residues(pdb_text, chain))


def residue_index_map(pdb_text, chain=None):
    """Map PDB author residue id -> 1-based sequence index (CA order).

    Keys are stored both as the bare author number ('501') and, when an
    insertion code is present, as number+icode ('501A').
    """
    mapping = {}
    for i, (_, res_seq, icode, _) in enumerate(ca_residues(pdb_text, chain), start=1):
        mapping[str(res_seq)] = i
        if icode:
            mapping[f"{res_seq}{icode}"] = i
    return mapping


def remap_to_seq_index(pdb_text, chain, author_resnums):
    """Convert PDB author residue numbers to 1-based sequence indices."""
    mapping = residue_index_map(pdb_text, chain)
    out, missing = [], []
    for a in author_resnums:
        key = str(a)
        if key in mapping:
            out.append(mapping[key])
        else:
            missing.append(key)
    if missing:
        raise KeyError(f"residues not found in chain {chain!r}: {missing}")
    return out


def ca_coords(pdb_text, chain=None):
    """List of (x, y, z) for CA atoms in chain order."""
    return [r[3] for r in ca_residues(pdb_text, chain)]
