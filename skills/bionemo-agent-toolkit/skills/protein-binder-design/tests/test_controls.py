#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Check reproducibility, composition, and input boundaries for negative controls."""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from controls import make_scrambled_controls, scramble_sequence  # noqa: E402


class ScrambledControlTests(unittest.TestCase):
    def test_controls_preserve_each_source_composition_and_repeat_by_seed(self):
        sources = ["ACDEFGHIKLMNPQRSTVWY", "AACCGGTT"]
        controls = make_scrambled_controls(sources, n=7, seed=42)
        self.assertEqual(len(controls), 7)
        self.assertEqual(controls, make_scrambled_controls(sources, n=7, seed=42))
        for index, control in enumerate(controls):
            self.assertEqual(Counter(control), Counter(sources[index % 2]))
        self.assertEqual(sources, ["ACDEFGHIKLMNPQRSTVWY", "AACCGGTT"])

    def test_zero_count_and_empty_source_set_produce_no_controls(self):
        self.assertEqual(make_scrambled_controls(["ACDE"], n=0), [])
        self.assertEqual(make_scrambled_controls([]), [])
        self.assertEqual(scramble_sequence("AAAA"), "AAAA")

    def test_invalid_sequences_cannot_be_sent_as_negative_controls(self):
        for seq in ("", "acde", "AC X", "AX", "AC*", None, ["A", "C"]):
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                scramble_sequence(seq)
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                make_scrambled_controls(["ACDE", seq])

    def test_invalid_count_seed_or_collection_is_rejected(self):
        for count in (-1, 1.5, True, "5"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                make_scrambled_controls(["ACDE"], n=count)
        for seed in (None, True, 0.5, "42"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                scramble_sequence("ACDE", seed=seed)
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                make_scrambled_controls(["ACDE"], seed=seed)
        for sources in ("ACDE", None, {"ACDE"}):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                make_scrambled_controls(sources)


if __name__ == "__main__":
    unittest.main()
