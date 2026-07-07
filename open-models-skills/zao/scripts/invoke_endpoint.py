#!/usr/bin/env python3
"""Client-side caller for a ZAO Marketplace endpoint (SageMaker or local).

This is the deterministic kernel the ``zao-embed`` skill invokes. It does NOT
create features or run the model: all of that (SMILES standardization, nvmolkit
GPU conformer generation, feature extraction, model forward pass) happens inside
the ZAO endpoint container. This script only:

  1. reads SMILES (CLI, file, or stdin),
  2. splits them into request-sized batches (SageMaker real-time endpoints cap
     the payload at 6 MB and the response at 60 s),
  3. sends each batch to the endpoint -- either AWS SageMaker
     (``sagemaker-runtime:InvokeEndpoint`` with SigV4 auth, the default) or, when
     ``--endpoint-url`` / ``ZAO_ENDPOINT_URL`` is set, a local container over
     plain HTTP (no AWS transport, no SigV4),
  4. parses the JSON Lines response into per-molecule embeddings, and
  5. writes an output file plus a structured JSON summary to stdout for the
     calling agent to parse.

The endpoint's response contract (see marketplace/serve.py) is JSON Lines:
    {"smiles": "CCO", "embedding": [..2048..], "dim": 2048}
    {"smiles": "BAD", "embedding": null, "error": "standardization failed"}

Usage examples:
    python invoke_endpoint.py --endpoint zao-endpoint --smiles CCO c1ccccc1
    python invoke_endpoint.py --endpoint zao-endpoint --smiles-file mols.txt \
        --out embeddings.npz
    cat mols.txt | python invoke_endpoint.py --endpoint zao-endpoint --out out.npz

Endpoint name and region default to the ZAO_SAGEMAKER_ENDPOINT and AWS_REGION
environment variables so an agent can register the endpoint once via the shell.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CONTENT_TYPE = "application/jsonlines"
ACCEPT = "application/jsonlines"
# SageMaker real-time endpoints cap the request payload at 6 MB. Batch by
# molecule count with a healthy margin; a JSON Lines SMILES line is small
# (tens of bytes), so 1000 SMILES/request stays well under the limit while
# keeping each request under the 60 s invocation timeout.
DEFAULT_BATCH = 1000


def _read_smiles(args) -> list[str]:
    """Collect SMILES from --smiles, --smiles-file, or stdin (in that order)."""
    if args.smiles:
        return list(args.smiles)

    if args.smiles_file:
        path = Path(args.smiles_file)
        if not path.exists():
            _fail(f"--smiles-file not found: {path}")
        smiles = []
        if path.suffix.lower() in (".csv", ".parquet"):
            _fail(
                f"{path.suffix} input is not supported by this caller; pass a "
                "plain-text file (one SMILES per line) or use --smiles."
            )
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                smiles.append(line)
        return smiles

    if not sys.stdin.isatty():
        return [
            line.strip()
            for line in sys.stdin.read().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    _fail("no SMILES provided: use --smiles, --smiles-file, or pipe via stdin")
    return []  # unreachable


def _batches(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _parse_jsonlines(text: str) -> list[dict]:
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results


def _invoke_sagemaker(client, endpoint: str, smiles_batch: list[str]) -> list[dict]:
    body = "\n".join(json.dumps({"smiles": s}) for s in smiles_batch)
    resp = client.invoke_endpoint(
        EndpointName=endpoint,
        ContentType=CONTENT_TYPE,
        Accept=ACCEPT,
        Body=body.encode("utf-8"),
    )
    return _parse_jsonlines(resp["Body"].read().decode("utf-8"))


def _invoke_local(url: str, smiles_batch: list[str]) -> list[dict]:
    """POST directly to a locally-served ZAO container (same /invocations
    contract as the SageMaker endpoint). Used for the local Docker deployment
    mode -- no AWS transport, no SigV4."""
    import requests

    body = "\n".join(json.dumps({"smiles": s}) for s in smiles_batch)
    resp = requests.post(
        url,
        data=body.encode("utf-8"),
        headers={"Content-Type": CONTENT_TYPE, "Accept": ACCEPT},
        timeout=600,
    )
    resp.raise_for_status()
    return _parse_jsonlines(resp.text)


def _write_output(results: list[dict], out_path: Path) -> None:
    suffix = out_path.suffix.lower()
    if suffix == ".jsonl":
        out_path.write_text("\n".join(json.dumps(r) for r in results))
        return

    # .npz / .npy / .csv all need numpy; import lazily so pure-JSONL runs have
    # no numpy dependency.
    import numpy as np

    smiles = [r["smiles"] for r in results]
    dim = next((r["dim"] for r in results if r.get("embedding") is not None), 0)
    # Always a real 2-D array (shape (N, dim); dim=0 if every molecule failed)
    # so downstream loaders never see a 0-d None.
    matrix = np.full((len(results), dim), np.nan, dtype=np.float32)
    for i, r in enumerate(results):
        if r.get("embedding") is not None:
            matrix[i] = np.asarray(r["embedding"], dtype=np.float32)

    if suffix == ".npz":
        np.savez_compressed(
            out_path, smiles=np.array(smiles, dtype=object), embeddings=matrix
        )
    elif suffix == ".npy":
        np.save(out_path, matrix)
    elif suffix == ".csv":
        import csv

        with out_path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            header = ["smiles"] + [f"e{i}" for i in range(dim)]
            writer.writerow(header)
            for i, s in enumerate(smiles):
                writer.writerow([s] + matrix[i].tolist())
    else:
        _fail(f"unsupported --out suffix '{suffix}' (use .npz/.npy/.csv/.jsonl)")


def _fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}), file=sys.stdout)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smiles", nargs="+", help="One or more SMILES strings")
    parser.add_argument(
        "--smiles-file", help="Text file with one SMILES per line (# comments ok)"
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("ZAO_SAGEMAKER_ENDPOINT"),
        help="Deployed SageMaker endpoint name (default: $ZAO_SAGEMAKER_ENDPOINT)",
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("ZAO_ENDPOINT_URL"),
        help="Local ZAO container /invocations URL, e.g. "
        "http://localhost:8080/invocations (default: $ZAO_ENDPOINT_URL). "
        "When set, calls this URL directly instead of AWS SageMaker.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION"),
        help="AWS region of the SageMaker endpoint. No built-in default: "
        "resolved from your AWS environment/profile ($AWS_REGION, "
        "$AWS_DEFAULT_REGION, or ~/.aws/config). Pass this to override.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH,
        help=f"SMILES per request (default: {DEFAULT_BATCH})",
    )
    parser.add_argument("--out", help="Output file (.npz/.npy/.csv/.jsonl)")
    args = parser.parse_args()

    local_mode = bool(args.endpoint_url)
    if not local_mode and not args.endpoint:
        _fail(
            "no endpoint: pass --endpoint / set ZAO_SAGEMAKER_ENDPOINT (AWS "
            "SageMaker), or pass --endpoint-url / set ZAO_ENDPOINT_URL (local "
            "container)"
        )

    smiles = _read_smiles(args)
    if not smiles:
        _fail("input contained no SMILES")

    region_used = None
    if local_mode:
        transport = "local"
        target = args.endpoint_url

        def call(batch):
            return _invoke_local(args.endpoint_url, batch)
    else:
        transport = "sagemaker"
        target = args.endpoint
        try:
            import boto3
            from botocore.exceptions import NoRegionError
        except ImportError:
            _fail("boto3 is required for SageMaker mode: pip install boto3")
        try:
            client = boto3.client("sagemaker-runtime", region_name=args.region)
        except NoRegionError:
            _fail(
                "no AWS region configured: set AWS_REGION, add a region to "
                "~/.aws/config, or pass --region <the endpoint's region>"
            )
        region_used = client.meta.region_name

        def call(batch):
            return _invoke_sagemaker(client, args.endpoint, batch)

    results: list[dict] = []
    n_batches = (len(smiles) + args.batch_size - 1) // args.batch_size
    try:
        for bi, batch in enumerate(_batches(smiles, args.batch_size)):
            print(
                f"[invoke] batch {bi + 1}/{n_batches} ({len(batch)} SMILES)",
                file=sys.stderr,
            )
            results.extend(call(batch))
    except Exception as exc:
        _fail(f"invoke failed ({transport}): {exc}")

    n_ok = sum(1 for r in results if r.get("embedding") is not None)
    n_fail = len(results) - n_ok
    dim = next((r["dim"] for r in results if r.get("embedding") is not None), None)

    summary = {
        "ok": True,
        "transport": transport,
        "endpoint": target,
        "region": region_used,
        "n_input": len(smiles),
        "n_embedded": n_ok,
        "n_failed": n_fail,
        "embedding_dim": dim,
        "failed_smiles": [
            {"smiles": r["smiles"], "error": r.get("error")}
            for r in results
            if r.get("embedding") is None
        ][:50],
    }

    if args.out:
        out_path = Path(args.out)
        _write_output(results, out_path)
        summary["output"] = str(out_path.resolve())
    else:
        summary["embeddings"] = results

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
