#!/usr/bin/env python3
"""Check the selected model environment and configured weights without sampling.

Usage: python preflight.py [--repo-root /path/to/RFD4-Proteina] [--data-path /path/to/data]
Arguments: --repo-root defaults to RFPROTEINA_ROOT, then the working directory.
    --data-path overrides DATA_PATH from the process environment.
Output: dependency paths, GPU identity, checkpoint checks, and a pass/fail verdict.
Exit codes: 0 for success, 1 for failed checks, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import argparse
import json
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


def check_weights(repo_root: Path, config: dict, data: Path) -> None:
    """Follow upstream's bundle-first selection without downloading during checks."""
    bundle = config.get("hf_ckpt_path")
    if bundle:
        directory = Path(bundle).expanduser()
        if not directory.is_absolute():
            directory = repo_root / directory
        if not directory.is_dir():
            if str(bundle).startswith(("/", ".", "~")):
                raise RuntimeError(f"Missing local model bundle: {directory}")
            from huggingface_hub import snapshot_download

            directory = Path(snapshot_download(
                repo_id=bundle, revision=config.get("hf_ckpt_revision"),
                allow_patterns=["config.json", "model.safetensors"], local_files_only=True,
            ))
        checkpoints = [directory / "config.json", directory / "model.safetensors"]
    else:
        checkpoints = [
            data / "flow_checkpoints" / config["ckpt_name"],
            data / "ae_checkpoints" / Path(config["autoencoder_ckpt_path"]).name,
        ]
    for path in checkpoints:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty model file: {path}")
        print(f"PASS: {path}")
    if bundle:
        payload = json.loads(checkpoints[0].read_text())
        if payload.get("model_type") != "rfd4_proteina" or payload.get("format_version") != 1:
            raise RuntimeError("Unsupported RFD4 model bundle type or format version.")
        if not isinstance(payload.get("config"), dict):
            raise RuntimeError("Model bundle is missing its model configuration.")


def check_environment(repo_root: Path, explicit_data_path: str | None = None) -> None:
    """Validate the selected checkout, runtime, CUDA device, and active weights."""
    config_path = repo_root / "configs/inference.yaml"
    for required in (".project-root", "pyproject.toml", "configs/inference.yaml"):
        if not (repo_root / required).is_file():
            raise RuntimeError(f"Selected model checkout is missing {required}: {repo_root}")

    print(f"Model checkout: {repo_root}")
    print(f"Python: {sys.executable}")
    # Read the active model selection before requiring legacy DATA_PATH weights.
    import yaml

    config = yaml.safe_load(config_path.read_text())
    if config.get("hf_ckpt_path") and explicit_data_path is None and not os.environ.get("DATA_PATH"):
        data = repo_root / "data_path"
    else:
        data = data_path(repo_root, explicit_data_path)
    # Native model imports see the same resolved setting as the file checks.
    os.environ["DATA_PATH"] = str(data)

    # Import only after CLI parsing, so --help works without model dependencies.
    import atomworks
    import torch
    import rfproteina.conditions

    print(f"AtomWorks: {atomworks.__file__}")
    print(f"RFProteina: {rfproteina.conditions.__file__}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in the selected environment.")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    check_weights(repo_root, config, data)
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
