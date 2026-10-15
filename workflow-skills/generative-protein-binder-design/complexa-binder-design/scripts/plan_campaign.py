#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Write a bounded PDB-target campaign plan without scientific dependencies.

Usage: python3 scripts/plan_campaign.py --request request.json --out NEW_DIRECTORY
Input schema: references/planning.md. Output: campaign_plan.json and PLAN.md.
Availability is supplied evidence, not probed by this command. No downloads,
installation, generation, refolding or structural verification are performed.
Exit 0 means the plan was written, including BLOCKED plans; invalid input or an
existing output directory exits 2. A plan is never a scientific GO/NO-GO result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from execution import algorithm, bounded_int
from validation_policy import GATE


RUNTIME = ("gpu", "complexa", "checkpoints", "af2_params", "refolder")


def fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"{label} must be an object with only: {', '.join(allowed)}")
    return value


def build_plan(request, source_sha256):
    fields(request, ("target", "epitope", "goal", "generation", "validation", "availability", "max_rounds"), "request")
    target = fields(request.get("target"), ("name", "pdb_id", "chain"), "target")
    if not isinstance(target.get("pdb_id"), str) or not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", target["pdb_id"]):
        raise ValueError("target.pdb_id must be a four-character PDB identifier")
    chain = target.get("chain")
    if not isinstance(chain, str) or not re.fullmatch(r"[A-Za-z0-9]", chain):
        raise ValueError("target.chain must be one PDB author-chain character")
    if not isinstance(target.get("name"), str) or not target["name"].strip() or len(target["name"]) > 200:
        raise ValueError("target.name must be 1..200 characters")

    epitope = fields(request.get("epitope", {"mode": "unspecified"}), ("mode", "partner_chain", "residues"), "epitope")
    mode = epitope.get("mode")
    if mode not in ("unspecified", "partner_interface", "explicit_patch"):
        raise ValueError("epitope.mode must be unspecified, partner_interface or explicit_patch")
    partner = epitope.get("partner_chain")
    if partner is not None and (not isinstance(partner, str) or not re.fullmatch(r"[A-Za-z0-9]", partner) or partner == chain):
        raise ValueError("partner_chain must be a different PDB author chain")
    residues = epitope.get("residues", [])
    if not isinstance(residues, list):
        raise ValueError("epitope.residues must be a list")
    for residue in residues:
        fields(residue, ("chain", "position"), "residue")
        if residue.get("chain") != chain:
            raise ValueError("patch residues must belong to the target chain")
        bounded_int(residue.get("position"), 1, 100000, "residue position")
    if (partner is not None and mode != "partner_interface") or (residues and mode != "explicit_patch"):
        raise ValueError("epitope evidence must match the selected mode")

    goal = fields(request.get("goal"), ("kind", "count"), "goal")
    if goal.get("kind") not in ("candidates", "passing_candidates"):
        raise ValueError("goal.kind must be candidates or passing_candidates")
    count = bounded_int(goal.get("count"), 1, 10000, "goal.count")
    generation = fields(request.get("generation", {}), ("algorithm", "num_samples", "seed"), "generation")
    search = algorithm(generation.get("algorithm", "best-of-n"))
    default_samples = count if goal["kind"] == "candidates" else min(2 * count, 10000)
    samples = bounded_int(generation.get("num_samples", default_samples), 1, 10000, "num_samples")
    seed = bounded_int(generation.get("seed", 0), 0, 2**32 - 1, "seed")
    rounds = bounded_int(request.get("max_rounds", 1 if goal["kind"] == "candidates" else 2), 1, 2, "max_rounds")
    if goal["kind"] == "candidates" and (rounds != 1 or samples != count):
        raise ValueError("a fixed candidate count requires one round and num_samples == goal.count")
    validation = fields(request.get("validation", {}), ("refolder", "endpoint"), "validation")
    if validation.get("refolder", "boltz2") != "boltz2":
        raise ValueError("this planner currently supports independent Boltz2 validation")
    endpoint = validation.get("endpoint", "hosted")
    if endpoint not in ("hosted", "local"):
        raise ValueError("validation.endpoint must be hosted or local")
    availability = fields(request.get("availability", {}), (*RUNTIME, "structure"), "availability")
    if any(value is not None and not isinstance(value, bool) for value in availability.values()):
        raise ValueError("availability values must be true, false or null (unknown)")
    availability = {key: availability.get(key) for key in (*RUNTIME, "structure")}

    inputs, questions = [], []
    if availability["structure"] is not True:
        inputs.append("target_structure")
        questions.append(f"Provide or resolve PDB {target['pdb_id']} chain {chain}, preserving source and author numbering.")
    if mode == "unspecified":
        inputs.append("accessible_epitope")
        questions.append("Specify a reviewed accessible epitope or a biologically relevant interface partner.")
    elif mode == "partner_interface" and partner is None:
        inputs.append("partner_chain")
        questions.append("Which verified partner author chain defines the requested interface? Check the co-complex before selecting it.")
    elif mode == "explicit_patch" and not residues:
        inputs.append("patch_residues")
        questions.append("Supply the intended patch residues with target author-chain numbering and supporting evidence.")
    runtime = [key for key in RUNTIME if availability[key] is not True]
    cap = min(samples, 2 * count)
    stop = ["round_cap", "budget_exhausted", "zero_passers", "input_or_runtime_failure"]
    stop.append("quota_reached" if goal["kind"] == "passing_candidates" else "candidate_count_reached")
    stages = [
        ("prepare_target", "scripts/preflight_design.py", ["target_prepared.pdb", "hotspots.json", "preflight.json"]),
        ("register_target", "scripts/pipeline.py:register_complexa_target", ["registered target configuration"]),
        ("generate", "scripts/complexa_design.py run", ["complex PDBs", "co-designed sequences", "generation provenance"]),
        ("independent_holo", "scripts/boltz2_refold.py", ["validation/refold_batch.json", "validation/raw/"]),
        ("independent_apo_and_score", "scripts/validate_binders.py", ["validation/apo/", "validation/validation_scores.json"]),
        ("rank_and_report", "agent report from measured validation results", ["ranked_binders.json", "ranked_binders.csv", "REPORT.md"]),
    ]
    return {
        "schema_version": 1, "mode": "planning_only", "status": "BLOCKED" if inputs or runtime else "PLANNED",
        "scientific_decision": "NOT_EVALUATED", "inference_executed": False, "source_sha256": source_sha256,
        "availability_source": "supplied_not_probed", "availability": availability,
        "target": dict(target), "epitope": {"mode": mode, "partner_chain": partner, "residues": residues},
        "goal": dict(goal),
        "generation": {"model": "Proteina-Complexa", "verb": "generate", "algorithm": search,
                       "num_samples": samples, "seed": seed, "af2_reward": "required"},
        "validation": {"model": "Boltz2", "endpoint": endpoint, "independent": True,
                       "predictions": ["holo", "apo"], "gate": GATE,
                       "rank_by": ["pass", "iptm", "ipsae_min"]},
        "limits": {"max_rounds": rounds, "validation_per_round": cap,
                   "max_generation_samples": samples * rounds, "max_holo_predictions": cap * rounds,
                   "max_apo_predictions": cap * rounds, "stop_conditions": stop},
        "blocking_inputs": inputs, "blocking_runtime": runtime, "questions": questions,
        "stages": [{"name": name, "tool": tool, "status": "not_run", "outputs": outputs}
                   for name, tool, outputs in stages],
        "results": {"generated": 0, "validated": 0, "passed": None, "quota_met": None, "candidates": []},
    }


def write_plan(source: Path, output: Path):
    content = source.read_bytes()
    plan = build_plan(json.loads(content), hashlib.sha256(content).hexdigest())
    target, gen, limits = plan["target"], plan["generation"], plan["limits"]
    lines = ["# Campaign plan", "", f"Status: **{plan['status']} — planning only**.",
             "Scientific decision: NOT_EVALUATED. No generation or independent validation was executed.",
             "Availability below was supplied, not probed. This plan does not establish target readiness or binding.", "",
             f"Target: {target['name']} (PDB {target['pdb_id']}, chain {target['chain']}).",
             f"Goal: {plan['goal']['count']} {plan['goal']['kind']}; passing designs cannot be guaranteed.",
             f"Generate with {gen['algorithm']}, {gen['num_samples']} samples per round, seed {gen['seed']}.",
             "Preserve the co-designed sequences. Keep the AF2 reward; missing parameters block this plan, with no automatic bypass.",
             f"Limits: {limits['max_rounds']} rounds, {limits['validation_per_round']} designs validated per round, "
             f"{limits['max_generation_samples']} generated samples total, {limits['max_holo_predictions']} holo and "
             f"{limits['max_apo_predictions']} apo predictions total before retries.",
             "Stop on: " + ", ".join(limits["stop_conditions"]) + ".",
             "Record cumulative usage across rounds/resumes; agree a call/time budget including bounded retries before execution.", "",
             "## Inputs and runtime to resolve", ""]
    lines.extend(f"- {question}" for question in plan["questions"])
    lines.append("- Missing or unverified runtime: " + (", ".join(plan["blocking_runtime"]) or "none declared") + ".")
    lines.extend(["", "## Resume after prerequisites and epitope review", "",
                  "1. On the provisioned host run `bash scripts/check_setup.sh` once (use `--endpoint local` for a local refolder). Verify config, checkpoint paths and endpoint health.",
                  f"2. Run `python3 scripts/preflight_design.py {target['pdb_id']} --chain {target['chain']}` with the reviewed `--partner-chain` or `--hotspots` and a fresh `--out`. Verify geometry, numbering, hotspot accessibility and size before registration.",
                  "3. Register the prepared target using `register_complexa_target` as described in `references/pipeline.md`; never register guessed hotspots.",
                  f"4. Run `python3 scripts/complexa_design.py run --task-name <registered-target> --run-name <fresh-round> --algorithm {gen['algorithm']} --num-samples {gen['num_samples']} --seed {gen['seed']} --out <fresh-run-dir>`. These placeholders must be resolved; this command has not run.",
                  f"5. Select the capped shortlist and verify target/binder chain IDs. Run `python3 scripts/boltz2_refold.py --run-dir <fresh-run-dir> --pdbs <shortlisted-PDBs> --target-chain <verified-target-chain> --binder-chain <verified-binder-chain> --max-designs {limits['validation_per_round']} --endpoint {plan['validation']['endpoint']} --validate scripts/validate_binders.py --hotspots <prepared-hotspots.json>`. Boltz2 performs separate holo and apo predictions; retain raw evidence and every failure.",
                  "6. Apply every gate below; missing or invalid metrics fail. Rank passers first, then descending ipTM and ipSAE_min, using independent results. Report measured counts and the actual stop reason, even if fewer candidates pass. Generator reward cannot establish validation.", "",
                  "## Independent Boltz2 gate", "", "| Metric | Direction | Threshold |", "| --- | --- | --- |"])
    lines.extend(f"| {metric} | {direction} | {threshold} |" for metric, (direction, threshold) in GATE.items())
    output.mkdir(parents=True, exist_ok=False)
    (output / "campaign_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (output / "PLAN.md").write_text("\n".join(lines) + "\n")
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        plan = write_plan(args.request, args.out)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({"status": plan["status"], "scientific_decision": plan["scientific_decision"],
                      "blocking_inputs": plan["blocking_inputs"], "blocking_runtime": plan["blocking_runtime"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
