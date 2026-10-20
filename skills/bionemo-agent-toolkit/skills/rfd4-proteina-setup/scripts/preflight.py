#!/usr/bin/env python3
"""Check the selected model environment and released checkpoints without sampling.

Usage: python preflight.py [--repo-root /path/to/RFD4-Proteina] [--data-path /path/to/data]
Arguments: --repo-root defaults to RFPROTEINA_ROOT, then the working directory.
    --data-path overrides DATA_PATH from the process environment.
Output: dependency paths, GPU identity, checkpoint checks, and a pass/fail verdict.
Exit codes: 0 for success, 1 for failed checks, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path


def data_path(repo_root: Path, explicit_path: str | None = None) -> Path:
    """Resolve the supplied data directory relative to the model checkout."""
    setting = explicit_path if explicit_path is not None else os.environ.get("DATA_PATH")
    if not setting:
        raise RuntimeError("Set DATA_PATH in the process environment or pass --data-path.")
    path = Path(setting).expanduser()
    return path if path.is_absolute() else repo_root / path


def check_environment(repo_root: Path, explicit_data_path: str | None = None) -> None:
    """Validate the selected checkout, runtime, CUDA device, and checkpoint pair."""
    config_path = repo_root / "configs/inference.yaml"
    for required in (".project-root", "pyproject.toml", "configs/inference.yaml"):
        if not (repo_root / required).is_file():
            raise RuntimeError(f"Selected model checkout is missing {required}: {repo_root}")

    print(f"Model checkout: {repo_root}")
    print(f"Python: {sys.executable}")
    data = data_path(repo_root, explicit_data_path)
    # Native model imports see the same resolved setting as the file checks.
    os.environ["DATA_PATH"] = str(data)

    # Import only after CLI parsing, so --help works without model dependencies.
    import atomworks
    import torch
    import yaml
    import rfproteina.conditions

    print(f"AtomWorks: {atomworks.__file__}")
    print(f"RFProteina: {rfproteina.conditions.__file__}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in the selected environment.")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    config = yaml.safe_load(config_path.read_text())
    checkpoints = [
        data / "flow_checkpoints" / config["ckpt_name"],
        data / "ae_checkpoints" / Path(config["autoencoder_ckpt_path"]).name,
    ]
    for path in checkpoints:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty checkpoint: {path}")
        print(f"PASS: {path}")
    print("PREFLIGHT PASSED")


def main(argv: Sequence[str] | None = None) -> int:
    """Run preflight for the chosen model checkout and return a CLI status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(os.environ.get("RFPROTEINA_ROOT", ".")))
    parser.add_argument("--data-path", help="Data directory; overrides DATA_PATH and resolves relative to the model root.")
    args = parser.parse_args(argv)
    try:
        check_environment(args.repo_root.expanduser().resolve(), args.data_path)
    except (ImportError, OSError, RuntimeError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
