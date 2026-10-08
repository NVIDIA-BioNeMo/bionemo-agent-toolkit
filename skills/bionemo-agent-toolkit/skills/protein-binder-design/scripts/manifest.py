#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Run manifest for protein-binder-design campaigns.

A campaign manifest is a single JSON file that records every candidate's
lineage, scores, artifacts, and filter status. It is the backbone for ranking,
resumability, validation, and the final report. No third-party dependencies.

Usage: Import Manifest and call create(run_dir, target) or load(path).
Arguments: Campaign paths, target/parameter/filter dictionaries, candidate IDs and scores.
Output: Mutation methods save manifest.json; to_csv writes the selected candidate table.
Exit codes: Not applicable to this library; invalid data and I/O errors raise exceptions.
"""
from __future__ import annotations

import csv
import json
import math
import operator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

DEFAULT_FILTERS = {
    "iptm_min": 0.8,
    "binder_plddt_min": 80.0,
    "self_consistency_rmsd_max": 2.0,
}

FILTER_METRICS = (
    ("iptm_min", "iptm", operator.ge),
    ("boltz2_confidence_min", "boltz2_confidence", operator.ge),
    ("binder_plddt_min", "binder_plddt", operator.ge),
    ("self_consistency_rmsd_max", "self_consistency_rmsd", operator.le),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_score(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Manifest:
    """Read/write wrapper around a campaign ``manifest.json``."""

    def __init__(self, data: dict[str, Any], path: Path):
        self.data = data
        self.path = Path(path)

    # ---- lifecycle -------------------------------------------------------
    @classmethod
    def create(
        cls,
        run_dir: str | Path,
        target: dict[str, Any],
        mode: str = "hosted",
        params: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> "Manifest":
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": SCHEMA_VERSION,
            "campaign": "protein-binder-design",
            "created": _now(),
            "run_dir": str(run_dir),
            "target": target,
            "mode": mode,
            "params": params or {},
            "filters": dict(filters) if filters is not None else dict(DEFAULT_FILTERS),
            "stages": [],
            "candidates": [],
        }
        m = cls(data, run_dir / "manifest.json")
        m.save()
        return m

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        path = Path(path)
        if path.is_dir():
            path = path / "manifest.json"
        return cls(json.loads(path.read_text()), path)

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))
        return self.path

    # ---- mutation --------------------------------------------------------
    def log_stage(self, name: str, **info: Any) -> None:
        self.data["stages"].append({"stage": name, "ts": _now(), **info})
        self.save()

    def _find(self, cid: str) -> dict[str, Any] | None:
        for c in self.data["candidates"]:
            if c["id"] == cid:
                return c
        return None

    def upsert_candidate(self, cid: str, **fields: Any) -> dict[str, Any]:
        c = self._find(cid)
        if c is None:
            c = {
                "id": cid,
                "backbone_id": None,
                "sequence": None,
                "scores": {},
                "artifacts": {},
                "passed_filter": None,
                "is_control": False,
                "control_type": None,
                "created": _now(),
            }
            self.data["candidates"].append(c)
        c.update({k: v for k, v in fields.items() if v is not None})
        self.save()
        return c

    def set_scores(self, cid: str, **scores: Any) -> dict[str, Any]:
        c = self.upsert_candidate(cid)
        c["scores"].update({k: v for k, v in scores.items() if v is not None})
        self.save()
        return c

    def add_artifact(self, cid: str, key: str, path: str | Path) -> dict[str, Any]:
        c = self.upsert_candidate(cid)
        c["artifacts"][key] = str(path)
        self.save()
        return c

    # ---- analysis --------------------------------------------------------
    def required_metrics(self, cid: str) -> list[str]:
        """Enabled metrics applicable to a candidate, including on resume.

        Sequence-only controls have no designed backbone to compare against.
        Their interface confidence and pLDDT still use the campaign thresholds.
        """
        candidate = self._find(cid)
        if candidate is None:
            raise KeyError(cid)
        sequence_control = candidate.get("is_control") and not candidate.get("artifacts", {}).get("backbone_pdb")
        return [metric for threshold, metric, _ in FILTER_METRICS
                if self.data["filters"].get(threshold) is not None
                and not (sequence_control and metric == "self_consistency_rmsd")]

    def missing_scores(self, cid: str) -> list[str]:
        """Return absent or invalid required scores; low finite scores are complete."""
        required = self.required_metrics(cid)
        scores = self._find(cid).get("scores", {})
        return [metric for metric in required if not _finite_score(scores.get(metric))]

    def apply_filters(self) -> None:
        """Require all applicable metrics; record control-only RMSD exemptions."""
        f = self.data["filters"]
        for c in self.data["candidates"]:
            s = c.get("scores", {})
            checks = []
            required = self.required_metrics(c["id"])
            c["filter_metrics"] = required
            c["filter_exemptions"] = {}
            for threshold, metric, compare in FILTER_METRICS:
                if f.get(threshold) is None:
                    continue
                if metric not in required:
                    c["filter_exemptions"][metric] = "sequence-only control: no designed backbone"
                    continue
                score = s.get(metric)
                checks.append(
                    _finite_score(score) and compare(score, f[threshold])
                )
            c["passed_filter"] = bool(checks) and all(checks)
        self.save()

    def rank(
        self,
        by: str = "iptm",
        descending: bool = True,
        passed_only: bool = False,
        include_controls: bool = False,
    ) -> list[dict[str, Any]]:
        cands = self.data["candidates"]
        if not include_controls:
            cands = [c for c in cands if not c.get("is_control")]
        if passed_only:
            cands = [c for c in cands if c.get("passed_filter")]
        cands = [c for c in cands if _finite_score(c.get("scores", {}).get(by))]
        return sorted(cands, key=lambda c: c["scores"][by], reverse=descending)

    def to_csv(
        self,
        path: str | Path | None = None,
        *,
        candidates: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Export all candidates, or a supplied ranked list in its given order."""
        path = Path(path) if path else Path(self.data["run_dir"]) / "candidates.csv"
        candidates = self.data["candidates"] if candidates is None else candidates
        score_keys = sorted({k for c in self.data["candidates"] for k in c.get("scores", {})})
        cols = ["id", "backbone_id", "is_control", "control_type", "passed_filter"] + score_keys
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for c in candidates:
                row = [
                    c.get("id"),
                    c.get("backbone_id"),
                    c.get("is_control"),
                    c.get("control_type"),
                    c.get("passed_filter"),
                ]
                row += [c.get("scores", {}).get(k) for k in score_keys]
                w.writerow(row)
        return path

    def summary(self) -> dict[str, int]:
        cands = [c for c in self.data["candidates"] if not c.get("is_control")]
        passed = [c for c in cands if c.get("passed_filter")]
        controls = [c for c in self.data["candidates"] if c.get("is_control")]
        return {
            "n_candidates": len(cands),
            "n_passed": len(passed),
            "n_controls": len(controls),
        }
