# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Import synthetic score fixtures and export audited, reloaded manifests offline."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from manifest import FILTER_METRICS, Manifest


def export_run(manifest: Manifest) -> dict:
    """Filter saved state and write both exports, including an empty ranked list."""
    manifest.save()
    manifest = Manifest.load(manifest.path)
    manifest.apply_filters()
    ranked = manifest.rank(by=manifest.data["params"]["rank_by"], passed_only=True)
    root = manifest.path.parent
    manifest.to_csv(root / "all_candidates.csv")
    manifest.to_csv(root / "candidates.csv", candidates=ranked)
    pending = {
        c["id"]: manifest.missing_scores(c["id"])
        for c in manifest.data["candidates"]
        if manifest.missing_scores(c["id"])
    }
    summary = {
        "label": "simulated offline bookkeeping",
        "live_inference": False,
        **manifest.summary(),
        "ranked_ids": [c["id"] for c in ranked],
        "missing_scores": pending,
        "passing_fraction_provisional": any(
            c["id"] in pending
            for c in manifest.data["candidates"]
            if not c.get("is_control")
        ),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_fixture(input_path: Path, output_dir: Path) -> dict:
    """One profile writes directly to output_dir; multiple profiles get subdirs.

    Refuse existing manifests: import is distinct from resuming a real campaign.
    All profiles are validated before creating outputs. Scores stay uncoerced.
    """
    fixture = json.loads(Path(input_path).read_text())
    profiles = fixture["profiles"]
    if not profiles:
        raise ValueError("fixture must contain at least one profile")
    plans, names = [], set()
    for profile in profiles:
        name = profile["name"]
        if (
            not isinstance(name, str)
            or name in {"", ".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise ValueError("profile names must be single directory names")
        if name in names:
            raise ValueError(f"duplicate profile: {name}")
        names.add(name)
        ids = [c["id"] for c in profile["candidates"]]
        if any(not isinstance(cid, str) or not cid for cid in ids) or len(ids) != len(
            set(ids)
        ):
            raise ValueError(f"candidate IDs must be unique nonempty strings in {name}")
        unknown = set(profile["filters"]) - {item[0] for item in FILTER_METRICS}
        if unknown:
            raise ValueError(f"unsupported filters: {sorted(unknown)}")
        if any(
            value is not None
            and (type(value) not in (int, float) or not math.isfinite(value))
            for value in profile["filters"].values()
        ):
            raise ValueError("filter thresholds must be finite numbers or null")
        if any(
            type(c.get("is_control", False)) is not bool for c in profile["candidates"]
        ):
            raise ValueError("is_control flags must be booleans")
        if not isinstance(profile["rank_by"], str) or not profile["rank_by"]:
            raise ValueError("rank_by must name a score")
        root = Path(output_dir) / name if len(profiles) > 1 else Path(output_dir)
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"output directory is not empty: {root}")
        plans.append((profile, root))
    results = {}
    for profile, root in plans:
        manifest = Manifest.create(
            root,
            copy.deepcopy(fixture["target"]),
            mode="offline-bookkeeping",
            params={"rank_by": profile["rank_by"]},
            filters=copy.deepcopy(profile["filters"]),
        )
        manifest.data["provenance"] = fixture.get("provenance")
        for candidate in profile["candidates"]:
            record = manifest.upsert_candidate(candidate["id"])
            record.update(
                copy.deepcopy(candidate)
            )  # Preserve explicit nulls and absent score keys.
        results[profile["name"]] = export_run(manifest)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="synthetic JSON fixture containing target and profiles"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_fixture(args.input, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
