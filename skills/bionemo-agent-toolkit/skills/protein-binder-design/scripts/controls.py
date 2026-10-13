# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Negative controls for binder validation: composition-preserving scrambles."""
from __future__ import annotations

import random


def scramble_sequence(seq, seed=0):
    """Return a shuffled sequence (same amino-acid composition, new order)."""
    rng = random.Random(seed)
    chars = list(seq)
    rng.shuffle(chars)
    return "".join(chars)


def make_scrambled_controls(seqs, n=5, seed=0):
    """Generate ``n`` scrambled negative controls drawn from ``seqs``."""
    rng = random.Random(seed)
    if not seqs:
        return []
    out = []
    for i in range(n):
        base = seqs[i % len(seqs)]
        out.append(scramble_sequence(base, seed=rng.randint(0, 2 ** 31 - 1)))
    return out
