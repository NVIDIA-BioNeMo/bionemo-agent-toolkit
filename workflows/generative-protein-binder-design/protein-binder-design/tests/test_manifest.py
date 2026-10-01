# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Offline bookkeeping tests; numeric fixtures are not scientific predictions."""
import importlib.util
import tempfile
import unittest
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "binder_manifest", Path(__file__).resolve().parents[1] / "scripts" / "manifest.py"
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
Manifest = _MODULE.Manifest


class ManifestFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = Manifest.create(self.temp.name, {"name": "bookkeeping fixture"})

    def add(self, cid, **scores):
        return self.manifest.set_scores(cid, **scores)

    def test_each_required_score_must_be_present(self):
        full = {"iptm": 0.85, "binder_plddt": 85, "self_consistency_rmsd": 1.5}
        for missing in full:
            with self.subTest(missing=missing):
                candidate = self.add(missing, **{k: v for k, v in full.items() if k != missing})
                self.manifest.apply_filters()
                self.assertFalse(candidate["passed_filter"])

    def test_boundaries_and_failures(self):
        passing = self.add("boundary", iptm=0.8, binder_plddt=80, self_consistency_rmsd=2.0)
        for cid, scores in (
            ("low_interface", dict(iptm=0.79, binder_plddt=90, self_consistency_rmsd=1.0)),
            ("low_plddt", dict(iptm=0.9, binder_plddt=79, self_consistency_rmsd=1.0)),
            ("high_rmsd", dict(iptm=0.9, binder_plddt=90, self_consistency_rmsd=2.01)),
        ):
            self.add(cid, **scores)
        self.manifest.apply_filters()
        self.assertTrue(passing["passed_filter"])
        self.assertEqual([c["id"] for c in self.manifest.rank(passed_only=True)], ["boundary"])

    def test_invalid_values_cannot_pass(self):
        for value in (float("inf"), float("-inf"), float("nan"), True, "0.9", None):
            for metric in ("iptm", "binder_plddt", "self_consistency_rmsd"):
                with self.subTest(value=value, metric=metric):
                    candidate = self.add("invalid", iptm=0.9, binder_plddt=90, self_consistency_rmsd=1.0)
                    candidate["scores"][metric] = value
                    self.manifest.apply_filters()
                    self.assertFalse(candidate["passed_filter"])

    def test_explicitly_disabled_metric_is_optional(self):
        self.manifest.data["filters"]["self_consistency_rmsd_max"] = None
        candidate = self.add("disabled", iptm=0.8, binder_plddt=80)
        self.manifest.apply_filters()
        self.assertTrue(candidate["passed_filter"])

    def test_no_scores_or_no_enabled_filters_cannot_pass(self):
        candidate = self.add("empty")
        self.manifest.apply_filters()
        self.assertFalse(candidate["passed_filter"])
        self.manifest.data["filters"] = {}
        self.add("empty", iptm=0.9, binder_plddt=90, self_consistency_rmsd=1.0)
        self.manifest.apply_filters()
        self.assertFalse(candidate["passed_filter"])

    def test_composite_confidence_does_not_replace_iptm(self):
        candidate = self.add("composite", boltz2_confidence=0.99, binder_plddt=90, self_consistency_rmsd=1.0)
        self.manifest.apply_filters()
        self.assertFalse(candidate["passed_filter"])

    def test_resume_and_summary_do_not_count_incomplete_as_passed(self):
        self.add("done", iptm=0.85, binder_plddt=85, self_consistency_rmsd=1.5)
        self.add("pending", iptm=0.85)
        self.add("control", iptm=0.85, binder_plddt=85, self_consistency_rmsd=1.5)
        self.manifest.upsert_candidate("control", is_control=True, control_type="published")
        self.manifest.apply_filters()
        loaded = Manifest.load(self.temp.name)
        self.assertEqual(loaded.summary(), {"n_candidates": 2, "n_passed": 1, "n_controls": 1})
        loaded.set_scores("pending", binder_plddt=85, self_consistency_rmsd=1.5)
        loaded.apply_filters()
        self.assertEqual(loaded.summary()["n_passed"], 2)
        self.assertEqual(loaded.data["candidates"][0], self.manifest.data["candidates"][0])


if __name__ == "__main__":
    unittest.main()
