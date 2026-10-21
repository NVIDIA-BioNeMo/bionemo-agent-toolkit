#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Benchmark target registry loader (default: the empty assets/targets.json template).

Usage: Import load_registry or get_target; no command-line API.
Arguments: Optional registry JSON path; get_target also takes a target name or alias.
Output: Parsed registry or matching target dictionary; no files are written.
Exit codes: Not applicable to this library; missing targets raise KeyError,
    malformed JSON and unreadable paths raise their standard Python exceptions.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "assets" / "targets.json"


def load_registry(path=None):
    return json.loads(Path(path or _DEFAULT).read_text())


def get_target(name, path=None):
    reg = load_registry(path)
    needle = name.lower()
    for t in reg["targets"]:
        names = [t["name"].lower()] + [a.lower() for a in t.get("aliases", [])]
        if needle in names:
            return t
    available = [t["name"] for t in reg["targets"]]
    raise KeyError(f"target {name!r} not in registry; available: {available}")
