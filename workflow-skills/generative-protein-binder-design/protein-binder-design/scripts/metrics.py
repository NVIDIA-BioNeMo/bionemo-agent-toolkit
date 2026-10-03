# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Deterministic RMSD metrics (numpy; biotite for mmCIF input)."""
from __future__ import annotations

import numpy as np


def kabsch_rmsd(p, q):
    """Minimal RMSD after optimal superposition of two (N, 3) coord sets."""
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    if p.shape != q.shape or p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"coordinate shape mismatch: {p.shape} vs {q.shape}")
    if p.shape[0] == 0:
        raise ValueError("no coordinates provided")
    if not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError("non-finite coordinates cannot be aligned")
    pc = p - p.mean(axis=0)
    qc = q - q.mean(axis=0)
    h = pc.T @ qc
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    p_rot = pc @ rot.T
    return float(np.sqrt(np.sum((p_rot - qc) ** 2) / p.shape[0]))


def ca_rmsd_from_pdb(pdb_a, pdb_b, chain_a=None, chain_b=None):
    """CA-RMSD between equal-length PDB chains; missing residues are an error."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pdb_utils import ca_coords

    a = ca_coords(pdb_a, chain_a)
    b = ca_coords(pdb_b, chain_b)
    if not a or not b:
        raise ValueError("no CA atoms found for RMSD")
    return kabsch_rmsd(a, b)


def ca_rmsd_from_structures(backbone_pdb, predicted_text, *, backbone_chain,
                            predicted_chain, predicted_format="cif"):
    """Compare explicit binder chains, using mmCIF label IDs for predictions.

    Both chains must contain the full binder in residue order. Do not silently
    truncate missing residues or compare against the target chain.
    """
    from pdb_utils import structure_ca_coords

    designed = structure_ca_coords(backbone_pdb, backbone_chain, format="pdb")
    predicted = structure_ca_coords(predicted_text, predicted_chain, format=predicted_format)
    return kabsch_rmsd(designed, predicted)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Binder CA-RMSD from a PDB backbone and PDB/mmCIF prediction.")
    parser.add_argument("backbone", type=Path)
    parser.add_argument("prediction", type=Path)
    parser.add_argument("--backbone-chain", required=True)
    parser.add_argument("--predicted-chain", required=True)
    args = parser.parse_args()
    try:
        print(ca_rmsd_from_structures(
            args.backbone.read_text(), args.prediction.read_text(),
            backbone_chain=args.backbone_chain, predicted_chain=args.predicted_chain,
            predicted_format=args.prediction.suffix.lstrip("."),
        ))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"RMSD unavailable: {exc}\n")
