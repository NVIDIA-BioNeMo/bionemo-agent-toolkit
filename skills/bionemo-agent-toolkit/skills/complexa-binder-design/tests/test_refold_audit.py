# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Offline regressions for refold failure accounting, chains, and call budgets."""
import contextlib
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REFOLD = load("refold_audit_test", "boltz2_refold.py")
VALIDATOR = load("validator_audit_test", "validate_binders.py")
PIPELINE = load("pipeline_audit_test", "pipeline.py")


def pdb_text(include_binder=True):
    residues = [("X", 101, "ALA"), ("X", 105, "GLY")]
    if include_binder:
        residues += [("Y", 1, "SER"), ("Y", 2, "THR")]
    return "\n".join(
        f"ATOM  {i:5d}  CA  {name} {chain}{pos:4d}    "
        f"{float(i):8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{80.0:6.2f}           C  "
        for i, (chain, pos, name) in enumerate(residues, 1)
    ) + "\nEND\n"


class RefoldAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.good = self.root / "good.pdb"
        self.good.write_text(pdb_text())
        self.bad = self.root / "missing_chain.pdb"
        self.bad.write_text(pdb_text(False))
        self.run_dir = self.root / "run"

    def run_refold(self, paths, extra=()):
        argv = ["boltz2_refold.py", "--run-dir", str(self.run_dir),
                "--pdbs", *map(str, paths), "--target-chain", "X", "--binder-chain", "Y",
                "--endpoint", "local", "--throttle", "0", *extra]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return REFOLD.main()

    def run_validator(self):
        argv = ["validate_binders.py", "--run-dir", str(self.run_dir), "--no-apo", "--endpoint", "local"]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return VALIDATOR.main()

    def test_missing_chain_and_endpoint_failure_survive_into_ranked_tables(self):
        with patch.object(REFOLD, "boltz2_holo", side_effect=TimeoutError("synthetic timeout")) as call:
            status = self.run_refold([self.bad, self.good])
        self.assertEqual(status, 1)
        self.assertEqual(call.call_count, 1)
        with patch.object(VALIDATOR, "boltz2_predict_apo") as apo:
            self.assertEqual(self.run_validator(), 0)
            apo.assert_not_called()
        rows = json.loads((self.run_dir / "ranked_binders.json").read_text())
        self.assertEqual({r["name"] for r in rows}, {"missing_chain", "good"})
        self.assertTrue(all(not r["pass"] and r["failure_reason"].startswith("holo prediction failed") for r in rows))
        self.assertTrue(all(r["iptm"] is None and r["ipsae_min"] is None for r in rows))
        with (self.run_dir / "ranked_binders.csv").open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_nonstandard_chain_ids_reach_payload_and_remapped_hotspots_reach_scoring(self):
        response = {"structures": [{"structure": "synthetic"}], "pae": [[[0.0, 1.0], [1.0, 0.0]]],
                    "iptm_scores": [0.8], "complex_plddt_scores": [0.9]}
        hotspots = self.root / "hotspots.json"
        hotspots.write_text(json.dumps([{"chain": "X", "position": 105}]))
        with patch.object(REFOLD, "post_with_retry", return_value=response) as post:
            self.assertEqual(self.run_refold([self.good], ["--hotspots", str(hotspots)]), 0)
        self.assertEqual([p["id"] for p in post.call_args.args[1]["polymers"]], ["X", "Y"])
        raw = json.loads((self.run_dir / "validation/raw/good.json").read_text())
        self.assertEqual(raw["_refold"]["hotspots"][0]["position"], 2)
        atoms = [{"chain": chain, "resnum": 1, "resname": "ALA", "atom": "CA",
                  "bfac": 90.0, "xyz": np.zeros(3)} for chain in ("X", "Y")]
        with patch.object(VALIDATOR, "parse_cif_atoms", return_value=atoms), \
             patch.object(VALIDATOR, "run_ipsae", return_value={"ipsae_min": 0.6, "ipsae_max": 0.7, "ipsae_asym": {}}), \
             patch.object(VALIDATOR, "hotspot_contacts", return_value={"contact_frac": 1.0}) as contacts:
            self.assertEqual(self.run_validator(), 0)
        self.assertEqual(contacts.call_args.args[1:3], ("X", "Y"))
        self.assertEqual(contacts.call_args.args[3][0]["position"], 2)
        scored = json.loads((self.run_dir / "ranked_binders.json").read_text())[0]
        self.assertEqual(scored["binder_len"], 1)
        self.assertNotIn("scoring error", scored["failure_reason"])

    def test_batch_budget_is_checked_before_network_calls(self):
        with patch.object(REFOLD, "boltz2_holo") as call, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                self.run_refold([self.good, self.bad], ["--max-designs", "1"])
        self.assertEqual(error.exception.code, 2)
        call.assert_not_called()

    def test_invalid_gate_metrics_never_pass(self):
        metrics = {key: threshold for key, (_, threshold) in VALIDATOR.GATE.items()}
        self.assertTrue(VALIDATOR.evaluate_gate(metrics, True)[0])
        for value in (None, float("nan"), float("inf"), float("-inf"), True, "0.9"):
            with self.subTest(value=value):
                self.assertFalse(VALIDATOR.evaluate_gate({**metrics, "iptm": value}, True)[0])

    def test_failed_rerun_replaces_stale_success_and_still_chains_validator(self):
        raw_dir = self.run_dir / "validation/raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "good.json").write_text(json.dumps({"structures": ["old success"]}))
        with patch.object(REFOLD, "boltz2_holo", side_effect=TimeoutError("synthetic timeout")), \
             patch.object(REFOLD.subprocess, "run") as validator:
            validator.return_value.returncode = 0
            self.assertEqual(self.run_refold([self.good], ["--validate", "validate_binders.py"]), 1)
        validator.assert_called_once()
        self.assertIn("--url", validator.call_args.args[0])
        raw = json.loads((raw_dir / "good.json").read_text())
        self.assertIn("failure_reason", raw)
        self.assertNotIn("structures", raw)

    def test_shortlist_caps_actual_csv_extraction_independently_of_gpu_count(self):
        results = self.root / "results.csv"
        with results.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["self_sequence", "self_complex_i_pTM", "self_complex_pLDDT"])
            writer.writeheader()
            for i in range(30):
                writer.writerow({"self_sequence": "ACDEFGHIKLMNPQRSTVWY" * 2,
                                 "self_complex_i_pTM": 0.8 + i / 1000, "self_complex_pLDDT": 0.9})
        self.assertEqual(PIPELINE.validation_count(64), 20)
        cap = PIPELINE.validation_count(64, n_requested=3)
        with patch.object(PIPELINE, "_find_combined_csvs", return_value=[results]), \
             patch.object(PIPELINE, "_find_inference_dir", return_value=None):
            events = list(PIPELINE.extract_complexa_designs(self.run_dir, "target", "run", n_top=cap))
        self.assertEqual(events[-1].data["n_designs"], 6)
        fasta = (self.run_dir / "sequences/binders_complexa_native.fasta").read_text()
        self.assertEqual(fasta.count(">"), 6)


if __name__ == "__main__":
    unittest.main()
