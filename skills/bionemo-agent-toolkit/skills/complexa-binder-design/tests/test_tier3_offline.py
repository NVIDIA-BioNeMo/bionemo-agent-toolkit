# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Execute staged CPU tasks and challenge the standalone artifact verifier."""
import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from binder_ranking import GATE, evaluate_gate, rank_saved_scores  # noqa: E402

spec = importlib.util.spec_from_file_location("complexa_artifact_grader", SKILL / "evals/grader.py")
GRADER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GRADER)
CASES = {c["id"]: c for c in json.loads((SKILL / "evals/deferred/cpu-artifacts.json").read_text())["evals"]}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


class OfflineTier3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def stage(self, case):
        for path in CASES[case]["files"]:
            source = SKILL / path
            destination = self.workspace / "input" / source.relative_to(SKILL / "evals/files")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)

    def cli(self, script, *args, expected=0):
        # A child Python guard makes unexpected network access fail even when a
        # production helper accidentally starts a request in these offline cases.
        guard = "import runpy,socket,sys; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); p=sys.argv.pop(1); sys.path.insert(0,str(__import__('pathlib').Path(p).parent)); runpy.run_path(p,run_name='__main__')"
        result = subprocess.run([sys.executable, "-B", "-c", guard, str(SKILL / "scripts" / script), *map(str, args)],
                                cwd=self.workspace, capture_output=True, text=True, timeout=30, shell=False)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def execute(self, case):
        self.stage(case)
        if case in ("offline-interface-preflight", "offline-missing-epitope"):
            missing = case == "offline-missing-epitope"
            output = self.workspace / "output" / ("missing-patch" if missing else "interface")
            args = ["--hotspots", self.workspace / "input/target_prep/missing_patch.json"] if missing else ["--partner-chain", "A"]
            self.cli("preflight_design.py", self.workspace / "input/target_prep/complex.pdb",
                     "--chain", "B", "--out", output, *args, expected=int(missing))
        elif case == "offline-independent-ranking":
            self.cli("binder_ranking.py", "--scores", self.workspace / "input/saved_scores.json",
                     "--out", self.workspace / "output/ranking")
        else:
            output = self.workspace / "output/interrupted"
            shutil.copytree(self.workspace / "input/interrupted_run", output)
            self.cli("validate_binders.py", "--run-dir", output, "--no-apo", "--endpoint", "local")
            (output / "REPORT.md").write_text(
                "Synthetic offline recovery; no inference. NO-GO: zero passers. "
                "stale: wrong batch; timeout: prediction failed; missing: no response.\n")

    def assert_grade(self, case, expected):
        result = GRADER.grade(case, self.workspace)
        errors = [c for c in result["details"]["artifact_correctness"]["checks"] if not c["passed"]]
        self.assertEqual(result["custom_metrics"]["artifact_correctness"], expected, errors)

    def test_all_staged_workflows_execute_offline_and_pass_independent_verifier(self):
        for case in GRADER.CASE_PATHS:
            with self.subTest(case=case):
                self.execute(case)
                self.assert_grade(case, 1.)

    def test_missing_outputs_never_pass(self):
        for case in GRADER.CASE_PATHS:
            with self.subTest(case=case):
                self.stage(case)
                self.assert_grade(case, 0.)

    def test_preflight_verifier_rejects_wrong_partner_and_coordinate_changes(self):
        case = "offline-interface-preflight"
        self.execute(case)
        output = self.workspace / "output/interface"
        report_path = output / "preflight.json"
        report = json.loads(report_path.read_text())
        wrong = {**report, "partner_chain": "C"}
        write_json(report_path, wrong)
        self.assert_grade(case, 0.)
        write_json(report_path, report)
        path = output / "target_prepared.pdb"
        path.write_text(path.read_text().replace("  30.000", "  31.000"))
        self.assert_grade(case, 0.)

    def test_missing_patch_cannot_be_replaced_by_a_ready_interface(self):
        self.execute("offline-interface-preflight")
        shutil.copytree(self.workspace / "output/interface", self.workspace / "output/missing-patch")
        self.assert_grade("offline-missing-epitope", 0.)

    def rewrite_rows(self, output, rows):
        # Change both formats together so semantic checks, not just file
        # disagreement, must catch a wrong gate or ranking.
        for parent, stem in ((output, "ranked_binders"), (output / "validation", "validation_scores")):
            path = parent / f"{stem}.csv"
            with path.open() as stream:
                fields = csv.DictReader(stream).fieldnames
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            write_json(parent / f"{stem}.json", rows)

    def test_ranking_verifier_rejects_consistently_wrong_artifacts(self):
        case = "offline-independent-ranking"
        self.execute(case)
        output = self.workspace / "output/ranking"
        original = json.loads((output / "ranked_binders.json").read_text())
        def reorder(rows):
            rows[0], rows[1] = rows[1], rows[0]
            for i, row in enumerate(rows, 1):
                row["rank"] = i
        mutations = {
            "tie-break": reorder,
            "relaxed_gate": lambda rows: rows[4].update({"pass": True, "failure_reason": None}),
            "invented_apo": lambda rows: rows[6].update({"apo_binder_plddt": .99}),
            "coerced_score": lambda rows: rows[7].update({"iptm": .99}),
            "omitted_failure": lambda rows: rows.pop(),
            "boolean_pass": lambda rows: rows[0].update({"pass": 1}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                rows = copy.deepcopy(original)
                mutate(rows)
                self.rewrite_rows(output, rows)
                self.assert_grade(case, 0.)
        self.rewrite_rows(output, original)
        self.assert_grade(case, 1.)
        summary_path = output / "summary.json"
        summary = json.loads(summary_path.read_text())
        for key, value in (("decision", "GO"), ("live_inference", True), ("passed", 5)):
            with self.subTest(key=key):
                write_json(summary_path, {**summary, key: value})
                self.assert_grade(case, 0.)

    def test_input_tampering_is_rejected_even_when_outputs_match(self):
        case = "offline-independent-ranking"
        self.stage(case)
        path = self.workspace / "input/saved_scores.json"
        data = json.loads(path.read_text())
        data["scores"][0]["hotspot_contact_frac"] = .9
        write_json(path, data)
        rank_saved_scores(path, self.workspace / "output/ranking")
        self.assert_grade(case, 0.)

    def test_interrupted_batch_verifier_rejects_stale_success_and_evidence_edits(self):
        case = "offline-interrupted-validation"
        self.execute(case)
        output = self.workspace / "output/interrupted"
        original = json.loads((output / "ranked_binders.json").read_text())
        changed = copy.deepcopy(original)
        changed[0].update({"pass": True, "iptm": .99, "failure_reason": None})
        self.rewrite_rows(output, changed)
        self.assert_grade(case, 0.)
        self.rewrite_rows(output, original)
        path = output / "validation/raw/stale.json"
        data = json.loads(path.read_text())
        data["_refold"]["batch_id"] = "current"
        write_json(path, data)
        self.assert_grade(case, 0.)

    def test_standalone_grader_and_negative_case_contract(self):
        self.execute("offline-independent-ranking")
        tests = self.workspace / "tests"
        tests.mkdir()
        write_json(tests / "entry.json", {"id": "offline-independent-ranking"})
        reward = self.workspace / "verifier/reward.json"
        with patch.dict("os.environ", {"HARBOR_TESTS_DIR": str(tests), "HARBOR_VERIFIER_DIR": str(reward.parent),
                                       "HARBOR_REWARD_JSON": str(reward), "COMPLEXA_EVAL_WORKSPACE": str(self.workspace)}):
            GRADER.main()
        self.assertEqual(json.loads(reward.read_text())["custom_metrics"], {"artifact_correctness": 1.})
        self.assertEqual(GRADER.grade("routing-gromacs-guidance", self.workspace)["custom_metrics"], {})

    def test_fixture_hashes_and_live_archive_are_separate(self):
        for name, digest in GRADER.INPUT_HASHES.items():
            self.assertEqual(hashlib.sha256((SKILL / "evals/files" / name).read_bytes()).hexdigest(), digest)
        archived = json.loads((SKILL / "evals/deferred/live-campaigns.json").read_text())["evals"]
        self.assertEqual(len(archived), 4)
        self.assertFalse({c["id"] for c in archived} & CASES.keys())
        active = json.loads((SKILL / "evals/evals.json").read_text())["evals"]
        self.assertFalse({c["id"] for c in active} & CASES.keys())

    def test_empty_ranking_and_preservation_of_existing_output(self):
        source = self.workspace / "scores.json"
        write_json(source, {"evidence_kind": "synthetic", "hotspot_conditioned": True, "requested": 5, "scores": []})
        output = self.workspace / "empty"
        summary = rank_saved_scores(source, output)
        self.assertEqual((summary["decision"], summary["passed"], summary["delivered"]), ("NO-GO", 0, 0))
        with (output / "ranked_binders.csv").open() as stream:
            self.assertEqual(list(csv.DictReader(stream)), [])
        before = (output / "REPORT.md").read_bytes()
        with self.assertRaises(FileExistsError):
            rank_saved_scores(source, output)
        self.assertEqual((output / "REPORT.md").read_bytes(), before)

    def test_all_gate_boundaries_and_invalid_values(self):
        metrics = {key: value for key, (_, value) in GATE.items()}
        self.assertTrue(evaluate_gate(metrics, True)[0])
        for key, (direction, value) in GATE.items():
            for invalid in (None, True, "0.99", float("nan"), float("inf"), value + (.01 if direction == "max" else -.01)):
                with self.subTest(key=key, invalid=invalid):
                    self.assertFalse(evaluate_gate({**metrics, key: invalid}, True)[0])


if __name__ == "__main__":
    unittest.main()
