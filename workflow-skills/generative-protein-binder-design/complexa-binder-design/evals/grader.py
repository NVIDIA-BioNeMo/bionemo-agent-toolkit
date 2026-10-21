#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Standalone, offline artifact verifier. Imports no skill implementation.

Harbor stages this file in /tests. Input hashes pin truth outside the mutable
agent workspace. ACES remains the headline score; artifact_correctness is an
additional metric for campaign plans and executed CPU artifacts only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path


GATE = {"ipsae_min": ["min", 0.45], "iptm": ["min", 0.65],
        "binder_plddt": ["min", 0.7], "complex_plddt": ["min", 0.7],
        "apo_binder_plddt": ["min", 0.7], "binder_rmsd": ["max", 2.5],
        "hotspot_contact_frac": ["min", 0.2]}
RANKED = ["tie_higher", "tie_lower", "boundary", "failed_prediction",
          "high_reward_bad_contact", "unstable", "missing_apo", "invalid_score"]
FAILURES = {"failed_prediction": "synthetic timeout",
            "high_reward_bad_contact": "hotspot_contact_frac",
            "unstable": "binder_rmsd", "missing_apo": "apo_binder_plddt",
            "invalid_score": "iptm"}
CASE_PATHS = {
    "offline-interface-preflight": ["target_prep/", "CONTRACT.md"],
    "offline-missing-epitope": ["target_prep/", "CONTRACT.md"],
    "offline-independent-ranking": ["saved_scores.json", "CONTRACT.md"],
    "offline-interrupted-validation": ["interrupted_run/", "CONTRACT.md"],
}
PLANNING_CASES = {
    "planning-pdl1-blocked": "pdl1",
    "planning-barnase-interface": "barnase",
    "planning-lysozyme-patch": "lysozyme",
}


def file_bytes(path, workspace):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(workspace.resolve()) or not resolved.is_file():
        raise ValueError("artifact must be a file inside the workspace")
    if resolved.stat().st_size > 5_000_000:
        raise ValueError("artifact exceeds verifier size limit")
    return resolved.read_bytes()


def read_json(path, workspace):
    return json.loads(file_bytes(path, workspace))


def same(actual, expected):
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same(actual[k], v) for k, v in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(same(a, b) for a, b in zip(actual, expected)))
    if type(expected) in (int, float):
        return (type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-8))
    return type(actual) is type(expected) and actual == expected


def report_check(output, names, workspace, check):
    report = file_bytes(output / "REPORT.md", workspace).decode().lower()
    check("synthetic" in report and "offline" in report, "report labels synthetic offline coverage")
    check(all(name.lower() in report for name in names), "report names every audited candidate")


def verify_preflight(case, workspace, check):
    missing = case == "offline-missing-epitope"
    output = workspace / "output" / ("missing-patch" if missing else "interface")
    report = read_json(output / "preflight.json", workspace)
    hotspots = read_json(output / "hotspots.json", workspace)
    expected = [] if missing else ["B10(ALA)", "B20(GLY)"]
    check(report.get("chain") == "B" and report.get("conditioned_length") == 3, "target chain and length")
    check(same(report.get("n_hotspots"), len(expected)) and report.get("final_hotspots") == expected,
          "verified hotspot labels/count")
    partner = None if missing else "A"
    check(report.get("partner_chain") == partner and hotspots.get("partner_chain") == partner,
          "selected partner retained without pooling")
    check(hotspots.get("target_chain") == "B", "hotspot target identity")
    wanted = [] if missing else [("B", 10, "ALA"), ("B", 20, "GLY")]
    observed = [(h.get("chain"), h.get("position"), h.get("residue"))
                for h in hotspots.get("hotspot_residues", [])]
    check(observed == wanted, "author-numbered hotspots match chosen geometry")
    dropped = hotspots.get("dropped_hotspots", [])
    check(any(h.get("chain") == "B" and h.get("position") == 999 for h in dropped)
          if missing else not dropped, "absent patch recorded without a replacement")
    checks = report.get("checks", {})
    for name in ("size<=500", "compact<=30A", ">=1_hotspots", "<=15_hotspots", "crop_preserves_hotspots"):
        item = checks.get(name, [])
        check(isinstance(item, list) and len(item) == 2
              and item[0] is (not (missing and name == ">=1_hotspots")), f"geometry check {name}")
    atoms = []
    for line in file_bytes(output / "target_prepared.pdb", workspace).decode().splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            atoms.append((line[21], int(line[22:26]), line[26], line[17:20], line[12:16].strip(),
                          *(float(line[a:b]) for a, b in ((30, 38), (38, 46), (46, 54)))))
    check(atoms == [("B", 10, " ", "ALA", "CA", 0., 0., 0.),
                    ("B", 20, " ", "GLY", "CA", 4., 0., 0.),
                    ("B", 30, " ", "SER", "CA", 30., 0., 0.)], "saved target atoms preserve geometry and numbering")


def verify_tables(output, workspace, check):
    rows = read_json(output / "ranked_binders.json", workspace)
    check(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "JSON audit is a row list")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return []
    check(same(read_json(output / "validation/validation_scores.json", workspace), rows), "JSON audit copies agree")
    for path in (output / "ranked_binders.csv", output / "validation/validation_scores.csv"):
        reader = csv.DictReader(file_bytes(path, workspace).decode().splitlines())
        csv_rows = list(reader)
        fields = reader.fieldnames or []
        required = {"name", "rank", "pass", "failure_reason", *GATE}
        check(required.issubset(fields) and len(fields) == len(set(fields)), "CSV has complete unique columns")
        check(len(csv_rows) == len(rows), "CSV retains every candidate")
        for actual, expected in zip(csv_rows, rows):
            for field in required:
                value = expected.get(field)
                cell = actual.get(field)
                if type(value) in (int, float):
                    try:
                        matches = same(float(cell), value)
                    except (ValueError, TypeError):
                        matches = False
                elif isinstance(value, bool):
                    matches = cell in (str(value), str(value).lower())
                else:
                    matches = cell == ("" if value is None else str(value))
                check(matches, f"CSV {field} agrees for {expected.get('name')}")
    check([r.get("rank") for r in rows] == list(range(1, len(rows) + 1)), "consecutive ranks")
    return rows


def verify_ranking(workspace, check):
    output = workspace / "output/ranking"
    rows = verify_tables(output, workspace, check)
    check([r.get("name") for r in rows] == RANKED, "independent gate and tie-break ranking")
    source = read_json(workspace / "input/saved_scores.json", workspace)
    original = {row["name"]: row for row in source["scores"]}
    for row in rows:
        name = row.get("name")
        check(name in original, "candidate belongs to source")
        if name not in original:
            continue
        for metric in GATE:
            check(same(row.get(metric), original[name].get(metric)), f"preserved {metric} for {name}")
        expected_pass = name in RANKED[:3]
        check(row.get("pass") is expected_pass, f"gate decision for {name}")
        reason = row.get("failure_reason")
        check(reason is None if expected_pass else isinstance(reason, str) and FAILURES[name] in reason,
              f"failure evidence for {name}")
    summary = read_json(output / "summary.json", workspace)
    expected = {"evidence_kind": "synthetic", "live_inference": False,
                "source_sha256": INPUT_HASHES["saved_scores.json"], "hotspot_conditioned": True,
                "gate": GATE, "requested": 5, "evaluated": 8, "passed": 3, "delivered": 5,
                "quota_met": False, "decision": "NO-GO", "stop_reason": "saved_scores_exhausted"}
    check(all(same(summary.get(k), v) for k, v in expected.items()), "honest quota, policy and provenance summary")
    report_check(output, RANKED, workspace, check)


def verify_interrupted(workspace, check):
    output = workspace / "output/interrupted"
    rows = verify_tables(output, workspace, check)
    names = ["stale", "timeout", "missing"]
    check([r.get("name") for r in rows] == names, "authoritative batch order and membership")
    reasons = {"stale": "current refold batch", "timeout": "synthetic timeout", "missing": "missing"}
    for row in rows:
        check(row.get("pass") is False and all(row.get(k) is None for k in GATE), "unmeasured results cannot pass")
        check(reasons.get(row.get("name"), "!unknown!") in str(row.get("failure_reason", "")), "specific failure recorded")
        check(row.get("batch_id") == "current", "current batch recorded")
    for relative, digest in INPUT_HASHES.items():
        if relative.startswith("interrupted_run/validation/"):
            path = output / Path(relative).relative_to("interrupted_run")
            check(hashlib.sha256(file_bytes(path, workspace)).hexdigest() == digest, "raw/batch evidence preserved")
    report_check(output, names, workspace, check)


def verify_plan(entry_id, workspace, check):
    slug = PLANNING_CASES[entry_id]
    source = workspace / "input/planning" / f"{slug}.json"
    request = read_json(source, workspace)
    output = workspace / "output" / f"planning-{slug}"
    plan = read_json(output / "campaign_plan.json", workspace)
    expected = {"schema_version": 1, "mode": "planning_only", "status": "BLOCKED",
                "scientific_decision": "NOT_EVALUATED", "inference_executed": False,
                "source_sha256": hashlib.sha256(file_bytes(source, workspace)).hexdigest(),
                "availability_source": "supplied_not_probed", "availability": request["availability"],
                "target": request["target"], "goal": request["goal"],
                "epitope": {"mode": request["epitope"]["mode"], "partner_chain": None, "residues": []},
                "results": {"generated": 0, "validated": 0, "passed": None, "quota_met": None, "candidates": []}}
    for key, value in expected.items():
        check(same(plan.get(key), value), f"planning truth: {key}")
    gen = request["generation"]
    check(same(plan.get("generation"), {**gen, "model": "Proteina-Complexa", "verb": "generate", "af2_reward": "required"}),
          "preserve requested generation without an implicit AF2 bypass")
    validation = {"model": "Boltz2", "endpoint": request["validation"]["endpoint"], "independent": True,
                  "predictions": ["holo", "apo"], "gate": GATE, "rank_by": ["pass", "iptm", "ipsae_min"]}
    check(same(plan.get("validation"), validation), "independent holo/apo policy and all seven unchanged gates")
    cap, rounds = min(gen["num_samples"], 2 * request["goal"]["count"]), request["max_rounds"]
    limits = plan.get("limits", {})
    expected_limits = {"max_rounds": rounds, "validation_per_round": cap,
                       "max_generation_samples": rounds * gen["num_samples"],
                       "max_holo_predictions": rounds * cap, "max_apo_predictions": rounds * cap}
    check(all(same(limits.get(key), value) for key, value in expected_limits.items()), "bounded cumulative campaign limits")
    stop = {"round_cap", "budget_exhausted", "zero_passers", "input_or_runtime_failure"}
    stop.add("quota_reached" if request["goal"]["kind"] == "passing_candidates" else "candidate_count_reached")
    check(set(limits.get("stop_conditions", [])) == stop, "finite stop conditions without a guaranteed quota")
    unresolved = {"pdl1": "accessible_epitope", "barnase": "partner_chain", "lysozyme": "patch_residues"}[slug]
    check(set(plan.get("blocking_inputs", [])) == {"target_structure", unresolved}, "identify unresolved structural evidence")
    check(set(plan.get("blocking_runtime", [])) == {"gpu", "complexa", "checkpoints", "af2_params", "refolder"},
          "record all missing runtime prerequisites")
    questions = plan.get("questions", [])
    check(isinstance(questions, list) and len(questions) >= 2
          and all(isinstance(q, str) and q.strip() for q in questions), "record actionable missing-input questions")
    names = ["prepare_target", "register_target", "generate", "independent_holo", "independent_apo_and_score", "rank_and_report"]
    stages = plan.get("stages", [])
    check([s.get("name") for s in stages] == names, "ordered preparation through independent validation and reporting")
    check(all(s.get("status") == "not_run" and isinstance(s.get("tool"), str) and s["tool"].strip()
              and isinstance(s.get("outputs"), list) and s["outputs"]
              and all(isinstance(p, str) and p.strip() for p in s["outputs"]) for s in stages),
          "future tools/artifacts are specified and all stages remain unrun")
    check(not any(output.glob("ranked_binders.*")), "no invented ranked candidate files")
    report = file_bytes(output / "PLAN.md", workspace).decode().lower()
    check(all(term in report for term in ("planning only", "blocked", "not_evaluated", "boltz2", "holo", "apo",
                                          request["target"]["pdb_id"].lower(), gen["algorithm"], str(request["goal"]["count"]))),
          "report clearly identifies intent and planning coverage")


def grade(entry_id, workspace):
    if entry_id == "routing-gromacs-guidance":
        return {"overall": 1.0, "custom_metrics": {},
                "details": {"artifact_correctness": {"applicable": False, "reason": "guidance judged by ACES"}}}
    checks = []
    def check(passed, message):
        checks.append({"passed": bool(passed), "message": message})
    try:
        if entry_id not in CASE_PATHS and entry_id not in PLANNING_CASES:
            raise ValueError("unknown evaluation case")
        paths = ([f"planning/{PLANNING_CASES[entry_id]}.json", "planning/CONTRACT.md"]
                 if entry_id in PLANNING_CASES else CASE_PATHS[entry_id])
        for name, digest in INPUT_HASHES.items():
            if any(name == p or p.endswith("/") and name.startswith(p) for p in paths):
                check(hashlib.sha256(file_bytes(workspace / "input" / name, workspace)).hexdigest() == digest,
                      f"input integrity: {name}")
        if not all(c["passed"] for c in checks):
            raise ValueError("fixture bytes changed")
        if entry_id in PLANNING_CASES:
            verify_plan(entry_id, workspace, check)
        elif entry_id in ("offline-interface-preflight", "offline-missing-epitope"):
            verify_preflight(entry_id, workspace, check)
        elif entry_id == "offline-independent-ranking":
            verify_ranking(workspace, check)
        else:
            verify_interrupted(workspace, check)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        check(False, f"artifact verification failed: {type(error).__name__}: {error}")
    passed = bool(checks) and all(c["passed"] for c in checks)
    return {"overall": float(passed), "custom_metrics": {"artifact_correctness": float(passed)},
            "details": {"artifact_correctness": {"passed": passed, "checks": checks,
                        "scope": "planning and CPU artifacts; no proof of inference or scientific validity"}}}


def main():
    tests = Path(os.environ.get("HARBOR_TESTS_DIR", "/tests"))
    verifier = Path(os.environ.get("HARBOR_VERIFIER_DIR", "/logs/verifier"))
    entry = json.loads((tests / "entry.json").read_text())
    result = grade(entry["id"], Path(os.environ.get("COMPLEXA_EVAL_WORKSPACE", "/workspace")))
    verifier.mkdir(parents=True, exist_ok=True)
    Path(os.environ.get("HARBOR_REWARD_JSON", str(verifier / "reward.json"))).write_text(json.dumps(result, indent=2) + "\n")


# Filled from reviewed fixture bytes, never read from mutable task truth at runtime.
INPUT_HASHES = {
    "CONTRACT.md": "2096c0e4c862143a8606437bd7b033bc5cac2720f8964168b541fb86b5b669ee",
    "interrupted_run/ranked_binders.csv": "dde084dd947ce56be3f5269bcff0598ec7c9eecd5c35ce0fb91bc0451d366f0b",
    "interrupted_run/ranked_binders.json": "96615b8448b0137e33ba8edd09b9e528cbe9988bfd729c3f09e88479e4483133",
    "interrupted_run/validation/raw/orphan.json": "70d2028d02d7fe03ae7ba780fa7093c1393cc8754beef7a025144b44fc4bc9c1",
    "interrupted_run/validation/raw/stale.json": "fcf031fae5b144534704c9989d53fc1228dd19a3a6a8489efb46dbc632ec9f34",
    "interrupted_run/validation/raw/timeout.json": "6d7788482392c18b4d0c6b672a2dfe1fc25ebbb7720a063d0777b1fcda104220",
    "interrupted_run/validation/refold_batch.json": "ad4d62e834dd32485e03d8113f01a0817d8b62f5617ede20f60fa81098d3dd8e",
    "planning/CONTRACT.md": "59be18b9904a8d2af8e8801d32001dedf57032cbc7f2e386a6b1b6cbe9310d8d",
    "planning/barnase.json": "161519424dc954aee267b09d8f546eddcf08a96b9a21121bb0a6fcabffce3fc1",
    "planning/lysozyme.json": "74bbda06643c82e6541b1af4b0d1ffe76a50d617d482c44bee06ab658be71f2e",
    "planning/pdl1.json": "a55fb1a29969d2753b87ecb84744400a6a0b4d43f7c61149e13235c40ca55857",
    "saved_scores.json": "8694b8e144e81b2be692fb94fb4fb18e88209b383133765df2b208ea352cb84c",
    "target_prep/complex.pdb": "4f3fac0c7c0092bd09bf32fc30786ef127b305ecbbbdd30b66f684a9abf9964e",
    "target_prep/missing_patch.json": "48c6affb51f844937433e6b1f2b5e93c97ed5e0ef6181a077f56da1a67810693"
}


if __name__ == "__main__":
    main()
