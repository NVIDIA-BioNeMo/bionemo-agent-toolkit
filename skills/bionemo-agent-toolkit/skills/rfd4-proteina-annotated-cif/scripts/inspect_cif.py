#!/usr/bin/env python
"""Print a read-only inventory of structure, chemistry, and RFProteína conditions.

Usage: python inspect_cif.py input.cif
Arguments: One source CIF path.
Output: Read-only inventory of atoms, chains, chemistry, conditions, and segments on stdout.
Exit codes: 0 for success, 1 for parse/runtime failure, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import warnings
from collections import Counter
from itertools import pairwise
from pathlib import Path

import fire
import numpy as np
from atomworks.io import parse
from atomworks.io.utils.annotator import ensure_annotations
from atomworks.io.utils.atom_array_plus import AtomArrayPlus, as_atom_array_plus
from atomworks.io.utils.selection import get_residue_starts
from atomworks.io.utils.standard_annotations import S_SEGMAX, S_SEGMIN
from atomworks.ml.conditions import C_IDX

import rfproteina.conditions  # noqa: F401
from rfproteina.conditions_reporting import summarize_conditions
from rfproteina.utils.parse_presets import ANNOTATED_CIF


def _load(path: Path) -> AtomArrayPlus:
    """Load the first parsed assembly while preserving registered annotations."""
    parsed = parse(path, config=ANNOTATED_CIF)
    assemblies = parsed.get("assemblies") or {}
    value = next(iter(assemblies.values())) if assemblies else parsed["asym_unit"]
    if isinstance(value, list | tuple) or hasattr(value, "stack_depth"):
        value = value[0]
    return as_atom_array_plus(value)


def _residue_labels(array: AtomArrayPlus, mask: np.ndarray) -> list[str]:
    """Return labels for residues containing at least one selected atom."""
    starts = get_residue_starts(array, add_exclusive_stop=True)
    return [
        f"{array.chain_id[start]}/{array.res_name[start]}{array.res_id[start]}"
        for start, stop in pairwise(starts)
        if mask[start:stop].any()
    ]


def main(cif: str) -> None:
    """Inspect one CIF without changing it."""
    path = Path(cif)
    if not path.is_file():
        raise SystemExit(f"No such CIF: {path}")

    warnings.filterwarnings("ignore")
    array = _load(path)
    ensure_annotations(array, "is_ligand")
    starts = get_residue_starts(array)
    residue_chains = array.chain_id[starts]
    chain_counts = Counter(str(chain) for chain in residue_chains)

    print(path)
    print(f"  atoms: {array.array_length()}")
    print(f"  residues: {len(starts)}")
    print(f"  chains: {dict(sorted(chain_counts.items()))}")

    ligand_labels = _residue_labels(array, np.asarray(array.is_ligand, dtype=bool))
    print(f"  ligand/non-polymer residues: {', '.join(ligand_labels) if ligand_labels else 'none'}")
    print(f"  nonzero formal charges: {int(np.count_nonzero(array.charge))}")

    bonds = array.bonds.as_array() if array.bonds is not None else np.empty((0, 3), dtype=int)
    bond_counts = Counter(int(value) for value in bonds[:, 2]) if len(bonds) else {}
    print(f"  bonds: {len(bonds)} by type {dict(sorted(bond_counts.items()))}")

    if S_SEGMIN.has_annotation(array):
        segment_mask = S_SEGMIN.mask(array, default="generate")
        minimum = S_SEGMIN.annotation(array, default="generate")
        maximum = S_SEGMAX.annotation(array, default="generate")
        ranges = [f"{int(minimum[i])}-{int(maximum[i])}" for i in np.where(segment_mask)[0]]
        print(f"  expandable segments: {', '.join(ranges) if ranges else 'none'}")
    else:
        print("  expandable segments: none")

    if C_IDX.has_annotation(array):
        unindexed = ~C_IDX.mask(array, default="generate")
        labels = _residue_labels(array, unindexed)
        print(f"  unindexed residues: {', '.join(labels) if labels else 'none'}")
    else:
        print("  unindexed residues: none (implicit all-indexed default)")

    summary = summarize_conditions(array)
    print("  active conditions:")
    print(summary if summary else "    none explicitly set")


if __name__ == "__main__":
    fire.Fire(main)
