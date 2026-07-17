#!/usr/bin/env python3
"""Train a downstream CatBoost model on ZAO embeddings + user labels.

The ZAO Marketplace endpoint returns embeddings only; property/activity
prediction is a downstream step. This kernel takes an embeddings ``.npz`` (as
written by ``invoke_endpoint.py``) plus a labels file, aligns them by SMILES,
and trains a CatBoost model with the same defaults as the ZAO TDC ADMET
benchmark (catboost_default: ``random_strength=2``, ``random_seed=42``,
Logloss for classification / MAE for regression).

It saves the model as ``<out>`` (CatBoost binary) and a sidecar
``<out>.meta.json`` recording task type, label column, embedding dim, and the
applied hyperparameters -- ``predict_catboost.py`` reads the sidecar to load the
right model class. A structured JSON summary is printed to stdout.

Usage:
    python train_catboost.py --embeddings train_emb.npz --labels labels.csv \
        --label-col Y --out model.cbm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def _load_config(path: str | None) -> dict:
    default = Path(__file__).resolve().parent.parent / "config" / "defaults_predict.json"
    cfg_path = Path(path) if path else default
    if not cfg_path.exists():
        _fail(f"config not found: {cfg_path}")
    return json.loads(cfg_path.read_text())


def _infer_task(y) -> str:
    """Classification if the labels are a binary {0,1} set; else regression."""
    import numpy as np

    uniq = np.unique(y[~np.isnan(y)])
    if set(uniq.tolist()).issubset({0.0, 1.0}) and len(uniq) <= 2:
        return "classification"
    return "regression"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--embeddings", required=True, help="Embeddings .npz from invoke_endpoint.py")
    p.add_argument("--labels", required=True, help="CSV with a SMILES column + a label column")
    p.add_argument("--smiles-col", default="smiles", help="SMILES column in the labels CSV (default: smiles)")
    p.add_argument("--label-col", required=True, help="Label column to train on")
    p.add_argument("--task", choices=["auto", "classification", "regression"], default="auto")
    p.add_argument("--config", help="Path to defaults_predict.json (default: package config)")
    p.add_argument("--random-strength", type=float, help="Override CatBoost random_strength")
    p.add_argument("--random-seed", type=int, help="Override CatBoost random_seed")
    p.add_argument("--out", required=True, help="Output model path (e.g. model.cbm)")
    args = p.parse_args()

    try:
        import numpy as np
        import pandas as pd
    except ImportError as e:
        _fail(f"numpy + pandas required: {e}")

    emb_path = Path(args.embeddings)
    if not emb_path.exists():
        _fail(f"--embeddings not found: {emb_path}")
    npz = np.load(emb_path, allow_pickle=True)
    if "smiles" not in npz or "embeddings" not in npz:
        _fail("embeddings .npz must contain 'smiles' and 'embeddings' (use invoke_endpoint.py --out X.npz)")
    emb_smiles = [str(s) for s in npz["smiles"]]
    emb_matrix = npz["embeddings"]
    if getattr(emb_matrix, "ndim", 0) != 2:
        _fail("embeddings array is not 2-D; regenerate it with invoke_endpoint.py --out X.npz")
    smi_to_row = {s: i for i, s in enumerate(emb_smiles)}

    labels_path = Path(args.labels)
    if not labels_path.exists():
        _fail(f"--labels not found: {labels_path}")
    df = pd.read_csv(labels_path)
    for col in (args.smiles_col, args.label_col):
        if col not in df.columns:
            _fail(f"column '{col}' not in labels CSV; columns: {list(df.columns)}")
    # Non-numeric label values become NaN and are dropped below (with a count),
    # rather than crashing on float() mid-loop.
    df[args.label_col] = pd.to_numeric(df[args.label_col], errors="coerce")

    # Align labels to embeddings by SMILES; drop rows with no/failed embedding
    # (all-NaN row) or a missing label.
    X, y, dropped = [], [], 0
    for _, r in df.iterrows():
        smi = str(r[args.smiles_col])
        lab = r[args.label_col]
        row = smi_to_row.get(smi)
        if row is None or np.all(np.isnan(emb_matrix[row])) or pd.isna(lab):
            dropped += 1
            continue
        X.append(emb_matrix[row])
        y.append(float(lab))
    if not X:
        _fail("no rows left after aligning labels to embeddings (check SMILES match and failed embeddings)")
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)

    task = args.task if args.task != "auto" else _infer_task(y)

    cfg = _load_config(args.config)
    random_strength = args.random_strength if args.random_strength is not None else cfg["random_strength"]
    random_seed = args.random_seed if args.random_seed is not None else cfg["random_seed"]
    loss_function = cfg[task]["loss_function"]

    try:
        from catboost import CatBoostClassifier, CatBoostRegressor
    except ImportError:
        _fail("catboost required: pip install catboost")

    common = dict(
        loss_function=loss_function,
        random_strength=random_strength,
        random_seed=random_seed,
        verbose=0,
        allow_writing_files=False,  # don't litter cwd with catboost_info/
    )
    model = CatBoostClassifier(**common) if task == "classification" else CatBoostRegressor(**common)
    model.fit(X, y)

    out_path = Path(args.out)
    model.save_model(str(out_path))
    meta = {
        "task": task,
        "label_col": args.label_col,
        "embedding_dim": int(X.shape[1]),
        "n_train": int(X.shape[0]),
        "n_dropped": int(dropped),
        "loss_function": loss_function,
        "random_strength": random_strength,
        "random_seed": random_seed,
    }
    meta_path = Path(str(out_path) + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2))

    summary = {"ok": True, "model": str(out_path.resolve()), "meta": str(meta_path.resolve()), **meta}
    if task == "classification":
        summary["label_counts"] = {str(int(v)): int((y == v).sum()) for v in np.unique(y)}
    else:
        summary["label_stats"] = {"mean": float(y.mean()), "std": float(y.std()), "min": float(y.min()), "max": float(y.max())}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
