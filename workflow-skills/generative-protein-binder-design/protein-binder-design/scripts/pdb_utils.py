#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Dependency-free PDB parsing helpers for binder-design handoffs.

Covers the fragile glue between NIM steps:
- extract a chain, keep ATOM records
- one-letter sequence from CA atoms
- map PDB author residue numbers -> 1-based sequence index (hotspot/pocket remap)
- CA coordinates for RMSD

Usage: Import extract_chain, sequence, remap_to_seq_index, or structure_ca_coords.
Arguments: Structure text, explicit chain ID, and author residue IDs where needed.
Output: Selected PDB text, sequence, residue indices, or CA coordinate tuples.
Exit codes: Not applicable to this library; missing/ambiguous residues or chains
    raise KeyError/ValueError. mmCIF input requires Biotite.
"""
from __future__ import annotations

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M", "SEC": "U", "PYL": "O",
}

# Fixed-width PDB ATOM columns, expressed as zero-based offsets/slices.
ATOM_NAME = slice(12, 16)
ALTLOC = 16
RESIDUE_NAME = slice(17, 20)
CHAIN_ID = 21
AUTHOR_RESIDUE_ID = slice(22, 27)
AUTHOR_RESIDUE_NUMBER = slice(22, 26)
INSERTION_CODE = 26
X_COORD = slice(30, 38)
Y_COORD = slice(38, 46)
Z_COORD = slice(46, 54)
OCCUPANCY = slice(54, 60)


def _first_model_lines(pdb_text):
    for line in pdb_text.splitlines():
        if line.startswith("ENDMDL"):
            break
        yield line


def _iter_atom_lines(pdb_text, chain=None):
    for line in _first_model_lines(pdb_text):
        if not line.startswith("ATOM"):
            continue
        if len(line) < Z_COORD.stop:
            continue
        if chain is not None and line[CHAIN_ID] != chain:
            continue
        yield line


def extract_chain(pdb_text, chain):
    """First model and chosen CA conformer; retain chain and author numbering."""
    keep = []
    selected = {line[AUTHOR_RESIDUE_ID]: line for line in _selected_ca_lines(pdb_text, chain)}
    for line in _first_model_lines(pdb_text):
        if line.startswith(("ATOM", "HETATM", "TER")) and len(line) > CHAIN_ID and line[CHAIN_ID] == chain:
            choice = selected.get(line[AUTHOR_RESIDUE_ID])
            if line.startswith("ATOM") and choice:
                if line[ATOM_NAME].strip() == "CA" and line != choice:
                    continue
                if choice[ALTLOC].strip() and line[ALTLOC] not in (" ", choice[ALTLOC]):
                    continue
            keep.append(line)
    return "\n".join(keep)


def _selected_ca_lines(pdb_text, chain=None):
    chosen = {}
    for line in _iter_atom_lines(pdb_text, chain):
        if line[ATOM_NAME].strip() != "CA":
            continue
        key = (line[CHAIN_ID], line[AUTHOR_RESIDUE_ID])
        occupancy = float(line[OCCUPANCY].strip() or 0) if len(line) >= OCCUPANCY.stop else 0
        priority = (bool(line[ALTLOC].strip()), -occupancy, line[ALTLOC])
        if key not in chosen or priority < chosen[key][0]:
            chosen[key] = (priority, line)
    return [line for _, line in chosen.values()]


def ca_residues(pdb_text, chain=None):
    """First model, one CA per author residue, preserving insertion codes.

    Prefer a blank alternate location, otherwise highest occupancy, then the
    lexicographically first altloc on a tie. Residue order is file order.
    """
    out = []
    for line in _selected_ca_lines(pdb_text, chain):
        res_name = line[RESIDUE_NAME].strip()
        res_seq = int(line[AUTHOR_RESIDUE_NUMBER])
        icode = line[INSERTION_CODE].strip()
        x, y, z = (float(line[field]) for field in (X_COORD, Y_COORD, Z_COORD))
        out.append((res_name, res_seq, icode, (x, y, z)))
    return out


def sequence(pdb_text, chain=None):
    """One-letter sequence from CA atoms (unknown residues -> 'X')."""
    return "".join(THREE_TO_ONE.get(r[0], "X") for r in ca_residues(pdb_text, chain))


def residue_index_map(pdb_text, chain=None):
    """Map PDB author residue id -> 1-based sequence index (CA order).

    '501' and '501A' are distinct keys. Never alias an insertion residue to a
    bare number: that silently moves a hotspot. Specify a chain when numbering
    overlaps across chains.
    """
    mapping = {}
    for i, (_, res_seq, icode, _) in enumerate(ca_residues(pdb_text, chain), start=1):
        key = f"{res_seq}{icode}"
        if key in mapping:
            raise ValueError(f"ambiguous author residue {key!r}; specify one chain")
        mapping[key] = i
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


def structure_ca_coords(structure_text, chain, *, format="pdb"):
    """Extract one chain's C-alpha coordinates from model 1 of PDB or mmCIF.

    mmCIF uses label chain IDs (the polymer IDs in the prediction request) and
    requires biotite. PDB-only callers retain the dependency-free parser.
    """
    if format.lower() == "pdb":
        # Only the first model: concatenating models corrupts RMSD matching.
        coords = ca_coords(structure_text.split("ENDMDL", 1)[0], chain)
    elif format.lower() in {"cif", "mmcif"}:
        from io import StringIO
        from biotite.structure.io import pdbx

        atoms = pdbx.get_structure(
            pdbx.CIFFile.read(StringIO(structure_text)), model=1,
            use_author_fields=False,
        )
        coords = atoms.coord[(atoms.chain_id == chain) & (atoms.atom_name == "CA")].tolist()
    else:
        raise ValueError(f"unsupported structure format: {format}")
    if not coords:
        raise ValueError(f"no CA atoms found for chain {chain!r}")
    return coords
