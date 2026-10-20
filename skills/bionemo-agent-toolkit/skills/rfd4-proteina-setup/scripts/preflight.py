"""Check the selected Python environment and released checkpoints without sampling."""

import os
from pathlib import Path

import atomworks
import torch
import yaml
from huggingface_hub import snapshot_download

import rfproteina.conditions

repo_root = Path(__file__).resolve().parents[3]
print(f"AtomWorks: {atomworks.__file__}")
print(f"RFProteina: {rfproteina.conditions.__file__}")
if not torch.cuda.is_available():
    raise SystemExit("FAIL: CUDA is unavailable in the selected environment.")
print(f"GPU: {torch.cuda.get_device_name(0)}")
config = yaml.safe_load((repo_root / "configs/inference.yaml").read_text())
model_path = config.get("hf_ckpt_path")
if model_path:
    directory = Path(model_path).expanduser()
    if not directory.is_dir():
        directory = Path(
            snapshot_download(
                model_path,
                revision=config.get("hf_ckpt_revision"),
                allow_patterns=["config.json", "model.safetensors"],
                local_files_only=True,
            )
        )
    checkpoints = [directory / "config.json", directory / "model.safetensors"]
else:
    if not os.environ.get("DATA_PATH"):
        raise SystemExit("FAIL: Set DATA_PATH for native checkpoint loading.")
    data = Path(os.environ["DATA_PATH"])
    checkpoints = [
        data / "flow_checkpoints" / config["ckpt_name"],
        data / "ae_checkpoints" / Path(config["autoencoder_ckpt_path"]).name,
    ]
for path in checkpoints:
    if not path.is_file():
        raise SystemExit(f"FAIL: Missing checkpoint: {path}")
    print(f"PASS: {path}")
print("PREFLIGHT PASSED")
