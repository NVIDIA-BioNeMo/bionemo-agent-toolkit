#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Stage-3 holo refold: independent Boltz2 prediction of each binder-target complex.

This is the bridge between Complexa generation and `validate_binders.py`:
`validate_binders.py` scores from the **holo** Boltz2 responses under
`<run-dir>/validation/raw/*.json` (and runs the **apo** call itself), but does not
produce the holo responses. This script makes the holo Boltz2 calls — with
retry/backoff + throttling so a batch doesn't trip the hosted endpoint's rate limit
(HTTP 429) — writes them in the shape `validate_binders.py` expects, then (optionally)
chains `validate_binders.py` for apo + ipSAE + apo/holo RMSD + gate + rank.
Each invocation records its exact shortlist in validation/refold_batch.json;
older responses cannot contribute to the new batch's ranking.

Reads the API key from $NVIDIA_API_KEY / $NGC_API_KEY (hosted only; local needs none).

Examples
  NVIDIA_API_KEY=nvapi-... python boltz2_refold.py \
      --run-dir outputs/pdl1 --pdbs inference/.../*.pdb --target-chain A --binder-chain B \
      --validate scripts/validate_binders.py --hotspots outputs/pdl1/hotspots.json
  python boltz2_refold.py --run-dir outputs/pdl1 --pdbs *.pdb --target-chain A --binder-chain B --endpoint local
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

from boltz2_endpoint import HOSTED_URL, LOCAL_URL
from refold_batch import start_batch, write_json
THREE_TO_ONE = {
    "ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G",
    "HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S",
    "THR":"T","TRP":"W","TYR":"Y","VAL":"V",
}


def chain_residues(pdb_path: str) -> dict[str, list[tuple[str, str]]]:
    """First-model CA residues, deduplicated by author number + insertion code."""
    chains: dict[str, dict[str, str]] = {}
    for line in Path(pdb_path).read_text().splitlines():
        if line.startswith("ENDMDL"):
            break
        if line[:6].strip() in ("ATOM", "HETATM") and line[12:16].strip() == "CA":
            if len(line) < 54:
                raise ValueError("incomplete PDB CA record")
            residue = line[22:26].strip() + line[26].strip()
            chains.setdefault(line[21], {}).setdefault(residue, THREE_TO_ONE.get(line[17:20].strip(), "X"))
    return {c: list(residues.items()) for c, residues in chains.items()}


def chain_seqs(pdb_path: str) -> dict[str, str]:
    return {c: "".join(aa for _, aa in residues) for c, residues in chain_residues(pdb_path).items()}


def remap_hotspots(hotspots: list[dict], residues: list[tuple[str, str]], chain: str) -> list[dict]:
    """Map input PDB author residue IDs to Boltz2's 1-based sequence positions."""
    index = {author: i for i, (author, _) in enumerate(residues, 1)}
    mapped = []
    for hotspot in hotspots:
        author = str(hotspot["position"])
        if hotspot.get("chain", chain) != chain or author not in index:
            raise ValueError(f"hotspot {hotspot} does not identify a residue in target chain {chain}")
        mapped.append({**hotspot, "chain": chain, "position": index[author], "author_position": author})
    return mapped


def _validate_endpoint(url: str) -> str:
    """Allow only http(s) Boltz2 endpoints (hosted=https, local NIM=http localhost).
    Rejects any other scheme so a mis-set URL/env can't redirect the request."""
    if urllib.parse.urlparse(url).scheme not in ("https", "http"):
        raise ValueError(f"refusing non-http(s) Boltz2 endpoint: {url!r}")
    return url


def post_with_retry(url: str, body: dict, headers: dict, max_retries: int = 5,
                    base_delay: float = 10.0, timeout: int = 1200) -> dict:
    """POST JSON with exponential backoff on 429 / 5xx / transient network errors.
    Honors a Retry-After header when present."""
    url = _validate_endpoint(url)
    data = json.dumps(body).encode()
    last = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 - scheme validated above
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504) or attempt == max_retries:
                raise
            ra = e.headers.get("Retry-After") if e.headers else None
            delay = float(ra) if (ra and str(ra).isdigit()) else base_delay * (2 ** attempt)
            print(f"    [retry] HTTP {e.code}; waiting {delay:.0f}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr, flush=True)
            time.sleep(min(delay, 120))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"    [retry] {type(e).__name__}; waiting {delay:.0f}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr, flush=True)
            time.sleep(min(delay, 120))
    raise last if last else RuntimeError("post_with_retry exhausted")


def boltz2_holo(target_seq: str, binder_seq: str, url: str, api_key: str | None,
                max_retries: int, *, target_chain: str, binder_chain: str) -> dict:
    body = {
        "polymers": [
            {"id": target_chain, "molecule_type": "protein", "sequence": target_seq},
            {"id": binder_chain, "molecule_type": "protein", "sequence": binder_seq},
        ],
        "recycling_steps": 3, "sampling_steps": 50, "diffusion_samples": 1,
        "step_scale": 1.638, "output_format": "mmcif", "write_full_pae": True,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return post_with_retry(url, body, headers, max_retries=max_retries)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--pdbs", nargs="+", required=True, help="Complexa complex PDB(s)")
    ap.add_argument("--endpoint", choices=["hosted", "local"], default="hosted")
    ap.add_argument("--url", default=None, help="override the Boltz2 URL")
    ap.add_argument("--target-chain", required=True, help="verified target chain in the input PDBs")
    ap.add_argument("--binder-chain", required=True, help="verified binder chain in the input PDBs")
    ap.add_argument("--max-designs", type=int, default=20,
                    help="explicit shortlist budget (default: 2 x the default requested count of 10)")
    ap.add_argument("--throttle", type=float, default=5.0,
                    help="seconds to wait between holo calls (avoid rate limits)")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--validate", default=None, help="path to validate_binders.py to chain after")
    ap.add_argument("--hotspots", default=None, help="hotspots.json passed to validate_binders.py")
    a = ap.parse_args()

    if a.target_chain == a.binder_chain:
        ap.error("target and binder chains must be distinct")
    if a.max_designs < 1 or len(a.pdbs) > a.max_designs:
        ap.error("supply a ranked shortlist within --max-designs before submitting predictions")
    names = [Path(pdb).stem for pdb in a.pdbs]
    if len(set(names)) != len(names):
        ap.error("input PDB filenames must have unique stems within a run")
    if a.max_retries < 0 or a.throttle < 0:
        ap.error("max-retries and throttle must be nonnegative")
    hotspots = []
    if a.hotspots:
        hdata = json.loads(Path(a.hotspots).read_text())
        hotspots = hdata if isinstance(hdata, list) else hdata["hotspot_residues"]

    url = a.url or (HOSTED_URL if a.endpoint == "hosted" else LOCAL_URL)
    key = None if a.endpoint == "local" else (os.getenv("NVIDIA_API_KEY")
                                              or os.getenv("NGC_API_KEY"))
    raw_dir = a.run_dir / "validation" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    batch = start_batch(a.run_dir, names)

    n_ok = 0
    pdbs = list(a.pdbs)
    for i, pdb in enumerate(pdbs):
        name = names[i]
        metadata = {"source_pdb": str(Path(pdb).resolve()),
                    "target_chain": a.target_chain, "binder_chain": a.binder_chain,
                    "batch_id": batch["batch_id"]}
        try:
            residues = chain_residues(pdb)
            tgt = "".join(aa for _, aa in residues.get(a.target_chain, []))
            bnd = "".join(aa for _, aa in residues.get(a.binder_chain, []))
            if not tgt or not bnd:
                raise ValueError(f"chains {list(residues)} do not contain target {a.target_chain} and binder {a.binder_chain}")
            metadata["hotspots"] = remap_hotspots(hotspots, residues[a.target_chain], a.target_chain)
            if a.endpoint == "hosted" and not key:
                raise ValueError("set NVIDIA_API_KEY or NGC_API_KEY for hosted predictions")
            print(f"[holo] {name}: target {len(tgt)}aa + binder {len(bnd)}aa -> Boltz2 ...", flush=True)
            resp = boltz2_holo(tgt, bnd, url, key, a.max_retries,
                               target_chain=a.target_chain, binder_chain=a.binder_chain)
            if not isinstance(resp, dict) or not resp.get("structures"):
                raise ValueError("Boltz2 response contains no predicted structures")
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[holo] {name} FAILED: {e}")
            resp = {"pass": False, "failure_reason": f"holo prediction failed: {type(e).__name__}: {e}"}
        resp["_refold"] = metadata
        # Record failures too, replacing stale responses for the same design.
        write_json(raw_dir / f"{name}.json", resp)
        if a.throttle and i < len(pdbs) - 1:
            time.sleep(a.throttle)
    print(f"=== {n_ok} holo refold(s) written ===")

    validation_status = 0
    if a.validate:
        cmd = [sys.executable, a.validate, "--run-dir", str(a.run_dir),
               "--endpoint", a.endpoint, "--target-chain", a.target_chain,
               "--binder-chain", a.binder_chain, "--url", url]
        if a.hotspots:
            cmd += ["--hotspots", a.hotspots]
        print("=== running:", " ".join(cmd), "===", flush=True)
        validation_status = subprocess.run(cmd).returncode
    return validation_status or (1 if n_ok != len(pdbs) else 0)


if __name__ == "__main__":
    sys.exit(main())
