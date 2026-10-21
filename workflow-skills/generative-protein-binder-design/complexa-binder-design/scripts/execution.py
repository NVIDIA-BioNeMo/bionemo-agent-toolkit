#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Validate local execution boundaries for the Complexa drivers.

Usage: import from the drivers; this module has no CLI.
Arguments: trusted installation paths and explicit scalar run settings.
Output: resolved paths/validated values; ValueError on an invalid boundary.
Exit codes: handled by the calling CLI.

The checkout and active Python environment are operator-managed code. These
checks prevent accidental executable/config redirection; they cannot make a
compromised installation trustworthy.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ALGORITHMS = ("single-pass", "best-of-n", "beam-search", "fk-steering", "mcts")
MAX_TIMEOUT = 86400


def identifier(value: str) -> str:
    """A run/task name is one filename component and one Hydra scalar."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("run/task names must be 1-128 ASCII letters, digits, underscores or hyphens")
    return value


def bounded_int(value: int, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def contained(path: Path, root: Path) -> Path:
    """Reject traversal and symlinks escaping a designated read/write tree."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path must remain within {root}: {path}")
    return resolved


def complexa_repo() -> Path:
    value = os.environ.get("COMPLEXA_REPO")
    if not value:
        raise ValueError("set COMPLEXA_REPO to your trusted Proteina-Complexa checkout")
    root = Path(value).expanduser().resolve()
    if not root.is_dir() or not (root / "configs").is_dir():
        raise ValueError("COMPLEXA_REPO must be a Proteina-Complexa checkout containing configs/")
    return root


def complexa_executable(value: str, repo: Path) -> str:
    """Only accept complexa installed in the active env or checkout's .venv."""
    if value == "complexa":
        installed = shutil.which(value)
        if installed is None:
            raise ValueError("complexa is not installed; activate its Python environment")
        path = Path(installed)
    else:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("COMPLEXA_BIN/--cli-bin must be 'complexa' or an absolute installed path")
    resolved = path.resolve()
    # Do not resolve the allowed directories: a .venv/bin symlink must not
    # silently turn an unrelated executable tree into an approved installation.
    allowed = (Path(sys.prefix).absolute() / "bin", repo.resolve() / ".venv" / "bin")
    if (resolved.name != "complexa" or resolved.parent not in allowed
            or not resolved.is_file() or not os.access(resolved, os.X_OK)):
        raise ValueError("complexa must be installed in the active Python environment or COMPLEXA_REPO/.venv/bin")
    return str(resolved)


def complexa_config(value: str, repo: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo / path
    # Check both boundaries so even a configs/ symlink cannot escape the repo.
    resolved = contained(path, repo)
    contained(resolved, repo / "configs")
    if resolved.suffix not in (".yaml", ".yml") or not resolved.is_file():
        raise ValueError("Complexa config must be an existing YAML file under COMPLEXA_REPO/configs")
    return str(resolved)


def algorithm(value: str) -> str:
    if value not in ALGORITHMS:
        raise ValueError(f"algorithm must be one of {', '.join(ALGORITHMS)}")
    return value


def hydra_path(value: str, repo: Path) -> str:
    """Quote literal paths for Hydra (not for a shell); reject interpolations."""
    if not value or any(c in value for c in ("$", "\x00", "\n", "\r", '"', "\\")):
        raise ValueError("checkpoint paths must be literal paths without interpolation or control characters")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo / path
    return '"' + str(path.resolve()) + '"'


def scalar_override(override: str, repo: Path) -> str:
    """Expose only the documented scalar knobs, never Hydra object creation."""
    match = re.fullmatch(r"\+\+([A-Za-z0-9_.]+)=(.+)", override)
    if not match:
        raise ValueError("override must be a documented ++key=value scalar")
    key, value = match.groups()
    if key in ("run_name", "generation.task_name"):
        value = identifier(value)
    elif key == "generation.search.algorithm":
        value = algorithm(value)
    elif key in ("seed", "gen_njobs", "eval_njobs", "generation.dataloader.dataset.nres.nsamples"):
        maximum = 2**32 - 1 if key == "seed" else (128 if key.endswith("njobs") else 10000)
        value = str(bounded_int(int(value), 0 if key == "seed" else 1, maximum, key))
    elif key in ("ckpt_path", "autoencoder_ckpt_path"):
        value = hydra_path(value, repo)
    elif key == "ckpt_name":
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.ckpt", value):
            raise ValueError("ckpt_name must be a simple .ckpt filename")
    else:
        raise ValueError(f"unsupported override key: {key}; edit a reviewed config in COMPLEXA_REPO/configs instead")
    return f"++{key}={value}"
