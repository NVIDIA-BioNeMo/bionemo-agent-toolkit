# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Exercise missing-runtime planning without site packages or network access."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from plan_campaign import build_plan, write_plan  # noqa: E402

spec = importlib.util.spec_from_file_location("planning_artifact_grader", SKILL / "evals/grader.py")
GRADER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GRADER)
CASES = {case["id"]: case for case in json.loads((SKILL / "evals/evals.json").read_text())["evals"]}


class CampaignPlanningTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)

    def stage(self, case):
        for filename in CASES[case]["files"]:
            source = SKILL / filename
            dest = self.workspace / "input" / source.relative_to(SKILL / "evals/files")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        slug = GRADER.PLANNING_CASES[case]
        return self.workspace / f"input/planning/{slug}.json", self.workspace / f"output/planning-{slug}"

    def assert_grade(self, case, expected):
        result = GRADER.grade(case, self.workspace)
        self.assertEqual(result["custom_metrics"]["artifact_correctness"], expected, result["details"])

    def test_plans_execute_with_standard_python_only_and_pass_independent_grader(self):
        # A Dockerfile selects the managed image builder even for CPU tasks.
        self.assertFalse((SKILL / "evals/environment/Dockerfile").exists())
        positive_cases = {case for case, entry in CASES.items() if entry.get("expected_skill")}
        self.assertEqual(positive_cases, set(GRADER.PLANNING_CASES))
        for case in sorted(positive_cases):
            with self.subTest(case=case):
                source, output = self.stage(case)
                # -S excludes scientific site-packages; the network guard catches
                # accidental inference/downloads in this planning-only path.
                guard = "import runpy,socket,sys; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); p=sys.argv.pop(1); sys.path.insert(0,str(__import__('pathlib').Path(p).parent)); runpy.run_path(p,run_name='__main__')"
                result = subprocess.run([sys.executable, "-B", "-S", "-c", guard,
                                         str(SKILL / "scripts/plan_campaign.py"), "--request", str(source), "--out", str(output)],
                                        capture_output=True, text=True, timeout=15, shell=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_grade(case, 1.)
                self.assertEqual({p.name for p in output.iterdir()}, {"campaign_plan.json", "PLAN.md"})
                tests = self.workspace / "tests"
                tests.mkdir(exist_ok=True)
                (tests / "entry.json").write_text(json.dumps({"id": case}))
                verifier = self.workspace / "verifier" / case
                reward = verifier / "reward.json"
                env = {**os.environ, "HARBOR_TESTS_DIR": str(tests), "HARBOR_VERIFIER_DIR": str(verifier),
                       "HARBOR_REWARD_JSON": str(reward), "COMPLEXA_EVAL_WORKSPACE": str(self.workspace)}
                checked = subprocess.run([sys.executable, "-B", "-S", "-c", guard,
                                          str(SKILL / "evals/grader.py")], env=env,
                                         capture_output=True, text=True, timeout=15, shell=False)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                self.assertEqual(json.loads(reward.read_text())["custom_metrics"]["artifact_correctness"], 1.)

    def test_verifier_rejects_plans_that_change_intent_or_claim_execution(self):
        case = "planning-lysozyme-patch"
        source, output = self.stage(case)
        write_plan(source, output)
        original = json.loads((output / "campaign_plan.json").read_text())
        mutations = {
            "target": lambda p: p["target"].update(pdb_id="5JDR"),
            "chain": lambda p: p["target"].update(chain="B"),
            "goal_semantics": lambda p: p["goal"].update(kind="candidates"),
            "algorithm": lambda p: p["generation"].update(algorithm="single-pass"),
            "sample_count": lambda p: p["generation"].update(num_samples=100),
            "unbounded_rounds": lambda p: p["limits"].update(max_rounds=100),
            "unbounded_validation": lambda p: p["limits"].update(validation_per_round=100),
            "omit_stop": lambda p: p["limits"]["stop_conditions"].remove("zero_passers"),
            "weaken_gate": lambda p: p["validation"]["gate"].update(iptm=["min", .1]),
            "generator_scoring": lambda p: p["validation"].update(model="Proteina-Complexa"),
            "omit_apo": lambda p: p["validation"].update(predictions=["holo"]),
            "guess_residues": lambda p: p["epitope"].update(residues=[{"chain": "A", "position": 42}]),
            "omit_patch_blocker": lambda p: p["blocking_inputs"].remove("patch_residues"),
            "omit_gpu_blocker": lambda p: p["blocking_runtime"].remove("gpu"),
            "no_questions": lambda p: p.update(questions=[]),
            "fake_availability": lambda p: p["availability"].update(gpu=True),
            "claim_probe": lambda p: p.update(availability_source="checked"),
            "fake_go": lambda p: p.update(scientific_decision="GO"),
            "infrastructure_no_go": lambda p: p.update(scientific_decision="NO-GO"),
            "fake_inference": lambda p: p.update(inference_executed=True),
            "fake_passers": lambda p: p["results"].update(passed=5, quota_met=True),
            "fake_candidates": lambda p: p["results"].update(candidates=[{"iptm": .95}]),
            "fake_stage": lambda p: p["stages"][2].update(status="completed"),
            "missing_stage": lambda p: p["stages"].pop(0),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                data = copy.deepcopy(original)
                mutate(data)
                (output / "campaign_plan.json").write_text(json.dumps(data))
                self.assert_grade(case, 0.)
        (output / "campaign_plan.json").write_text(json.dumps(original))
        self.assert_grade(case, 1.)
        (output / "ranked_binders.json").write_text("[]")
        self.assert_grade(case, 0.)

    def test_missing_plan_and_input_tampering_fail(self):
        case = "planning-pdl1-blocked"
        source, output = self.stage(case)
        self.assert_grade(case, 0.)
        request = json.loads(source.read_text())
        request["generation"]["algorithm"] = "single-pass"
        source.write_text(json.dumps(request))
        write_plan(source, output)
        self.assert_grade(case, 0.)

    def test_unknown_availability_remains_blocked_and_defaults_are_bounded(self):
        source, _ = self.stage("planning-pdl1-blocked")
        request = json.loads(source.read_text())
        del request["availability"], request["generation"], request["validation"], request["max_rounds"]
        plan = build_plan(request, "source")
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertTrue(all(v is None for v in plan["availability"].values()))
        self.assertEqual(plan["generation"]["num_samples"], 8)
        self.assertEqual(plan["limits"]["max_rounds"], 1)
        self.assertEqual(plan["results"]["passed"], None)

    def test_declared_prerequisites_do_not_claim_verified_target_or_scientific_execution(self):
        source, _ = self.stage("planning-barnase-interface")
        request = json.loads(source.read_text())
        request["availability"] = dict.fromkeys(request["availability"], True)
        request["epitope"]["partner_chain"] = "D"
        plan = build_plan(request, "source")
        self.assertEqual(plan["status"], "PLANNED")
        self.assertEqual(plan["availability_source"], "supplied_not_probed")
        self.assertEqual(plan["scientific_decision"], "NOT_EVALUATED")
        self.assertTrue(all(s["status"] == "not_run" for s in plan["stages"]))

    def test_invalid_constraints_rejected_before_output_and_old_plans_preserved(self):
        source, output = self.stage("planning-pdl1-blocked")
        original = json.loads(source.read_text())
        mutations = [lambda r: r.update(max_rounds=0), lambda r: r.update(max_rounds=3),
                     lambda r: r["goal"].update(count=True), lambda r: r["goal"].update(count=-1),
                     lambda r: r["generation"].update(num_samples=9),
                     lambda r: r["generation"].update(algorithm="guess"),
                     lambda r: r["validation"].update(refolder="generator"),
                     lambda r: r["availability"].update(gpu="false"),
                     lambda r: r["target"].update(pdb_id=1234),
                     lambda r: r["target"].update(chain="A --unsafe"),
                     lambda r: r["epitope"].update(partner_chain="A"),
                     lambda r: r["epitope"].update(residues=[{"chain": "B", "position": 42}])]
        for mutate in mutations:
            request = copy.deepcopy(original)
            mutate(request)
            source.write_text(json.dumps(request))
            with self.assertRaises(ValueError):
                write_plan(source, output)
            self.assertFalse(output.exists())
        source.write_text(json.dumps(original))
        write_plan(source, output)
        before = (output / "campaign_plan.json").read_bytes()
        with self.assertRaises(FileExistsError):
            write_plan(source, output)
        self.assertEqual((output / "campaign_plan.json").read_bytes(), before)
