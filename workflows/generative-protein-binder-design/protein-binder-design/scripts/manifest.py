# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Run manifest for protein-binder-design campaigns.

A campaign manifest is a single JSON file that records every candidate's
lineage, scores, artifacts, and filter status. It is the backbone for ranking,
resumability, validation, and the final report. No third-party dependencies.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

DEFAULT_FILTERS = {
    "iptm_min": 0.8,
    "binder_plddt_min": 80.0,
    "self_consistency_rmsd_max": 2.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            "filters": dict(filters) if filters else dict(DEFAULT_FILTERS),
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
    def apply_filters(self) -> None:
        f = self.data["filters"]
        for c in self.data["candidates"]:
            s = c.get("scores", {})
            checks = []
            if f.get("iptm_min") is not None and s.get("iptm") is not None:
                checks.append(s["iptm"] >= f["iptm_min"])
            if f.get("binder_plddt_min") is not None and s.get("binder_plddt") is not None:
                checks.append(s["binder_plddt"] >= f["binder_plddt_min"])
            if (
                f.get("self_consistency_rmsd_max") is not None
                and s.get("self_consistency_rmsd") is not None
            ):
                checks.append(s["self_consistency_rmsd"] <= f["self_consistency_rmsd_max"])
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
        cands = [c for c in cands if c.get("scores", {}).get(by) is not None]
        return sorted(cands, key=lambda c: c["scores"][by], reverse=descending)

    def to_csv(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else Path(self.data["run_dir"]) / "candidates.csv"
        score_keys = sorted({k for c in self.data["candidates"] for k in c.get("scores", {})})
        cols = ["id", "backbone_id", "is_control", "control_type", "passed_filter"] + score_keys
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for c in self.data["candidates"]:
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
