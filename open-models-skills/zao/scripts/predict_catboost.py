#!/usr/bin/env python3
"""Predict properties/activities with a downstream CatBoost model trained by
``train_catboost.py``, on ZAO embeddings for the query molecules.

Reads the model's sidecar ``<model>.meta.json`` to load the right CatBoost class
(classifier vs regressor) and writes a predictions CSV. Per the project's
evaluation-artifact rule, the output always keeps ``smiles`` and the prediction
column(s) so any metric can be recomputed later; classification also writes the
positive-class probability ``y_prob``.

Usage:
    python predict_catboost.py --model model.cbm --embeddings query_emb.npz \
        --out predictions.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, help="Model path from train_catboost.py (e.g. model.cbm)")
    p.add_argument("--embeddings", required=True, help="Query embeddings .npz from invoke_endpoint.py")
    p.add_argument("--out", required=True, help="Predictions CSV output path")
    args = p.parse_args()

    try:
        import numpy as np
        import pandas as pd
    except ImportError as e:
        _fail(f"numpy + pandas required: {e}")

    model_path = Path(args.model)
    if not model_path.exists():
        _fail(f"--model not found: {model_path}")
    meta_path = Path(str(model_path) + ".meta.json")
    if not meta_path.exists():
        _fail(f"model sidecar meta not found: {meta_path} (train with train_catboost.py)")
    meta = json.loads(meta_path.read_text())
    task = meta["task"]

    emb_path = Path(args.embeddings)
    if not emb_path.exists():
        _fail(f"--embeddings not found: {emb_path}")
    npz = np.load(emb_path, allow_pickle=True)
    if "smiles" not in npz or "embeddings" not in npz:
        _fail("embeddings .npz must contain 'smiles' and 'embeddings'")
    smiles = [str(s) for s in npz["smiles"]]
    matrix = npz["embeddings"]

    if getattr(matrix, "ndim", 0) != 2:
        _fail("embeddings array is not 2-D; regenerate it with invoke_endpoint.py --out X.npz")
    if matrix.shape[1] != meta["embedding_dim"]:
        _fail(f"embedding dim {matrix.shape[1]} != model's {meta['embedding_dim']}")

    # Rows whose embedding failed (all-NaN) cannot be predicted; mark them.
    valid = ~np.all(np.isnan(matrix), axis=1)

    try:
        from catboost import CatBoostClassifier, CatBoostRegressor
    except ImportError:
        _fail("catboost required: pip install catboost")

    model = CatBoostClassifier() if task == "classification" else CatBoostRegressor()
    model.load_model(str(model_path))

    n = len(smiles)
    out = {"smiles": smiles}
    if task == "classification":
        y_prob = np.full(n, np.nan, dtype=np.float64)
        y_pred = np.full(n, np.nan, dtype=np.float64)
        if valid.any():
            prob = model.predict_proba(matrix[valid])[:, 1]
            y_prob[valid] = prob
            y_pred[valid] = (prob >= 0.5).astype(float)
        out["y_pred"] = y_pred
        out["y_prob"] = y_prob
    else:
        y_pred = np.full(n, np.nan, dtype=np.float64)
        if valid.any():
            y_pred[valid] = model.predict(matrix[valid])
        out["y_pred"] = y_pred

    df = pd.DataFrame(out)
    out_path = Path(args.out)
    df.to_csv(out_path, index=False)

    summary = {
        "ok": True,
        "task": task,
        "label_col": meta["label_col"],
        "output": str(out_path.resolve()),
        "n_input": n,
        "n_predicted": int(valid.sum()),
        "n_skipped_failed_embedding": int((~valid).sum()),
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
