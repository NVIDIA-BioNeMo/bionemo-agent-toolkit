#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Shared validation gate and offline ranking of saved metrics.

Usage: python scripts/binder_ranking.py --scores scores.json --out NEW_DIRECTORY
Input: {evidence_kind: synthetic|saved_metrics, hotspot_conditioned: bool,
        requested: positive integer, scores: [{name, ...metrics...}]}.
Output: ranked_binders.json/.csv, summary.json and REPORT.md. No inference or
verification of the upstream measurements is performed. Exit 0 on completion,
2 for invalid input or an existing output directory; a quota shortfall is a result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from execution import bounded_int, identifier
from validation_policy import GATE


def numeric(value):
    return (not isinstance(value, (bool, np.bool_))
            and isinstance(value, (int, float, np.integer, np.floating))
            and np.isfinite(value))


def evaluate_gate(metrics: dict, hotspot_conditioned: bool) -> tuple[bool, str | None]:
    reasons = []
    for key, (mode, threshold) in GATE.items():
        if key == "hotspot_contact_frac" and not hotspot_conditioned:
            continue
        value = metrics.get(key)
        if not numeric(value):
            reasons.append(f"{key}=NA (not measured)")
        elif mode == "min" and value < threshold:
            reasons.append(f"{key}={value:.3f} < {threshold}")
        elif mode == "max" and value > threshold:
            reasons.append(f"{key}={value:.3f} > {threshold}")
    return not reasons, "; ".join(reasons) or None


def rank_rows(rows: list[dict]) -> list[dict]:
    """Rank the complete audit, passers first; invalid metrics sort last."""
    def key(row):
        def descending(metric):
            value = row.get(metric)
            return -value if numeric(value) else float("inf")
        return not row.get("pass", False), descending("iptm"), descending("ipsae_min")
    return [{**row, "rank": i} for i, row in enumerate(sorted(rows, key=key), 1)]


def write_rankings(rows: list[dict], run_dir: Path) -> None:
    columns = ["rank", "name", "batch_id", "pass", "ipsae_min", "ipsae_max", "iptm",
               "binder_plddt", "complex_plddt", "apo_binder_plddt", "binder_rmsd",
               "hotspot_contact_frac", "binder_len", "apo_status", "failure_reason"]
    validation = run_dir / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    for parent, stem in ((run_dir, "ranked_binders"), (validation, "validation_scores")):
        (parent / f"{stem}.json").write_text(json.dumps(rows, indent=2) + "\n")
        with (parent / f"{stem}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def rank_saved_scores(source: Path, output: Path) -> dict:
    data = json.loads(source.read_text())
    if data.get("evidence_kind") not in ("synthetic", "saved_metrics"):
        raise ValueError("evidence_kind must be synthetic or saved_metrics")
    conditioned = data.get("hotspot_conditioned")
    if not isinstance(conditioned, bool):
        raise ValueError("hotspot_conditioned must be a boolean")
    requested = bounded_int(data.get("requested"), 1, 10000, "requested")
    records = data.get("scores")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("scores must be a list of metric records")
    names = [identifier(row.get("name")) for row in records]
    if len(set(names)) != len(names):
        raise ValueError("candidate names must be unique")
    rows = []
    for record in records:
        passed, gate_reason = evaluate_gate(record, conditioned)
        # A recorded execution/scoring failure cannot be rescued by old numbers.
        original_reason = record.get("failure_reason")
        if original_reason is not None and not isinstance(original_reason, str):
            raise ValueError("failure_reason must be text or null")
        reason = "; ".join(filter(None, [original_reason, gate_reason])) or None
        rows.append({**dict.fromkeys(GATE), **record, "pass": passed and not original_reason,
                     "failure_reason": reason})
    rows = rank_rows(rows)
    passed_count = sum(row["pass"] for row in rows)
    summary = {"evidence_kind": data["evidence_kind"], "live_inference": False,
               "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "hotspot_conditioned": conditioned, "gate": GATE,
               "requested": requested, "evaluated": len(rows), "passed": passed_count,
               "delivered": min(requested, len(rows)),
               "quota_met": passed_count >= requested,
               "decision": "GO" if passed_count >= requested else "NO-GO",
               "stop_reason": "saved_scores_exhausted"}
    # This standalone export never deletes or overwrites a previous campaign.
    output.mkdir(parents=True, exist_ok=False)
    write_rankings(rows, output)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    label = "Synthetic offline exercise" if data["evidence_kind"] == "synthetic" else "Saved metric review"
    lines = [f"# {label}", "", f"Decision using supplied metrics: **{summary['decision']}**.",
             f"Requested {requested}; evaluated {len(rows)}; passed {passed_count}; delivered {summary['delivered']}.",
             "Stop: saved_scores_exhausted. All attempted candidates remain in the audit.", "",
             "This command performed no generation or refolding and did not verify the source measurements.",
             "These outputs establish no new independent structural validation or experimental binding.", "",
             "| Rank | Candidate | ipTM | ipSAE_min | Complex pLDDT | Binder pLDDT | Apo pLDDT | RMSD | Hotspot fraction | Pass | Failure |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        reason = str(row["failure_reason"] or "").replace("|", "\\|").replace("\n", " ")
        values = [row.get(key) for key in ("iptm", "ipsae_min", "complex_plddt", "binder_plddt",
                                         "apo_binder_plddt", "binder_rmsd", "hotspot_contact_frac")]
        metrics = " | ".join(f"{value:.3f}" if numeric(value) else "N/A (missing/invalid)" for value in values)
        lines.append(f"| {row['rank']} | {row['name']} | {metrics} | {row['pass']} | {reason} |")
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(rank_saved_scores(args.scores, args.out), indent=2))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
