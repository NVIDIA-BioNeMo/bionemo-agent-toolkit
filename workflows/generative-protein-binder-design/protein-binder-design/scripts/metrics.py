# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Deterministic structural metrics for binder design (numpy only)."""
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
    pc = p - p.mean(axis=0)
    qc = q - q.mean(axis=0)
    h = pc.T @ qc
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    p_rot = pc @ rot.T
    return float(np.sqrt(np.sum((p_rot - qc) ** 2) / p.shape[0]))


def ca_rmsd_from_pdb(pdb_a, pdb_b, chain_a=None, chain_b=None):
    """CA-RMSD between two structures (by chain). Truncates to common length."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pdb_utils import ca_coords

    a = ca_coords(pdb_a, chain_a)
    b = ca_coords(pdb_b, chain_b)
    n = min(len(a), len(b))
    if n == 0:
        raise ValueError("no CA atoms found for RMSD")
    return kabsch_rmsd(a[:n], b[:n])
