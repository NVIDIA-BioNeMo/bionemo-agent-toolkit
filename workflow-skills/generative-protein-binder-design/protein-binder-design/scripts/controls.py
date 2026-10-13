#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Negative controls for binder validation: composition-preserving scrambles.

Usage: Import scramble_sequence or make_scrambled_controls; no command-line API.
Arguments: Uppercase canonical amino-acid sequences, nonnegative count n, integer seed.
Output: A shuffled sequence or list of sequences with unchanged composition.
Exit codes: Not applicable to this library; invalid inputs raise ValueError.
"""
from __future__ import annotations

import random

AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
DEFAULT_CONTROL_COUNT = 5
MAX_SCRAMBLE_SEED = 2 ** 31 - 1


def _validate_sequence(seq):
    if not isinstance(seq, str) or not seq or set(seq) - AMINO_ACIDS:
        raise ValueError("sequence must be a nonempty uppercase canonical amino-acid string")


def _validate_seed(seed):
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")


def scramble_sequence(seq, seed=0):
    """Return a shuffled sequence; a shuffle can coincide with the input."""
    _validate_sequence(seq)
    _validate_seed(seed)
    rng = random.Random(seed)
    chars = list(seq)
    rng.shuffle(chars)
    return "".join(chars)


def make_scrambled_controls(seqs, n=DEFAULT_CONTROL_COUNT, seed=0):
    """Draw controls cyclically from a sequence list; an empty list yields none."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    if not isinstance(seqs, (list, tuple)):
        raise ValueError("seqs must be a list or tuple of amino-acid sequences")
    _validate_seed(seed)
    for seq in seqs:
        _validate_sequence(seq)
    rng = random.Random(seed)
    if not seqs:
        return []
    out = []
    for i in range(n):
        base = seqs[i % len(seqs)]
        out.append(scramble_sequence(base, seed=rng.randint(0, MAX_SCRAMBLE_SEED)))
    return out
