#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Record which refold invocation and candidates may contribute to a ranking.

Usage: import start_batch/load_batch/write_json; no CLI.
Arguments: run directory and unique candidate stems, or a JSON destination/data.
Output: batch JSON; start_batch logs/deletes stale derived score tables.
Exit codes: callers handle ValueError/OSError; this module has no exit status.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path


def write_json(path: Path, data: dict) -> None:
    """Publish a complete JSON document without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def start_batch(run_dir: Path, names: list[str]) -> dict:
    """Make a fresh invocation current before any prediction can start.

    Old raw evidence stays on disk. Deletes ranked_binders.json/.csv and
    validation/validation_scores.json/.csv, logging each removal to stderr.
    These derived rankings are invalid until the new batch is scored, including
    when prediction stops partway through the batch.
    """
    batch = {"version": 1, "batch_id": uuid.uuid4().hex, "candidates": names}
    write_json(run_dir / "validation" / "refold_batch.json", batch)
    for directory, stem in ((run_dir, "ranked_binders"), (run_dir / "validation", "validation_scores")):
        for suffix in (".json", ".csv"):
            path = directory / (stem + suffix)
            if path.exists() or path.is_symlink():
                print(f"[refold] removing stale derived scores: {path}", file=sys.stderr, flush=True)
                path.unlink()
    return batch


def load_batch(run_dir: Path) -> dict | None:
    """Read the current batch; malformed records must never fall back to a glob."""
    path = run_dir / "validation" / "refold_batch.json"
    if not path.exists():
        return None  # Legacy manually produced raw responses have no batch record.
    batch = json.loads(path.read_text())
    if not isinstance(batch, dict) or batch.get("version") != 1:
        raise ValueError("unsupported refold batch record")
    if not isinstance(batch.get("batch_id"), str) or not batch["batch_id"]:
        raise ValueError("refold batch record needs a batch_id")
    names = batch.get("candidates")
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name or name in (".", "..")
                   or Path(name).name != name for name in names)
            or len(names) != len(set(names))):
        raise ValueError("refold batch record needs unique candidate file stems")
    return batch
