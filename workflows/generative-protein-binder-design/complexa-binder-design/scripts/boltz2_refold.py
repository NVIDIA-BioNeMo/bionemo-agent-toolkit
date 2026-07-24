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

Reads the API key from $NVIDIA_API_KEY / $NGC_API_KEY (hosted only; local needs none).

Examples
  NVIDIA_API_KEY=nvapi-... python boltz2_refold.py \
      --run-dir outputs/pdl1 --pdbs inference/.../*.pdb \
      --validate scripts/validate_binders.py --hotspots outputs/pdl1/hotspots.json
  python boltz2_refold.py --run-dir outputs/pdl1 --pdbs *.pdb --endpoint local
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HOSTED_URL = "https://health.api.nvidia.com/v1/biology/mit/boltz2/predict"
# Local NIM: override host/port via $BOLTZ2_URL (e.g. a NIM on another container/host).
def _local_boltz2_url() -> str:
    """Resolve the local NIM endpoint (override via $BOLTZ2_URL). Kept in a helper so
    endpoint resolution is centralized and not threaded through the request layer."""
    return os.environ.get("BOLTZ2_URL", "http://localhost:8000/biology/mit/boltz2/predict")


LOCAL_URL = _local_boltz2_url()
THREE_TO_ONE = {
    "ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G",
    "HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S",
    "THR":"T","TRP":"W","TYR":"Y","VAL":"V",
}


def chain_seqs(pdb_path: str) -> dict[str, str]:
    chains: dict[str, list[str]] = {}
    for line in Path(pdb_path).read_text().splitlines():
        if line[:6].strip() in ("ATOM", "HETATM") and line[12:16].strip() == "CA":
            chains.setdefault(line[21], []).append(THREE_TO_ONE.get(line[17:20].strip(), "X"))
    return {c: "".join(r) for c, r in chains.items()}


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
                max_retries: int) -> dict:
    body = {
        "polymers": [
            {"id": "A", "molecule_type": "protein", "sequence": target_seq},
            {"id": "B", "molecule_type": "protein", "sequence": binder_seq},
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
    ap.add_argument("--target-chain", default="A")
    ap.add_argument("--binder-chain", default="B")
    ap.add_argument("--throttle", type=float, default=5.0,
                    help="seconds to wait between holo calls (avoid rate limits)")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--validate", default=None, help="path to validate_binders.py to chain after")
    ap.add_argument("--hotspots", default=None, help="hotspots.json passed to validate_binders.py")
    a = ap.parse_args()

    url = a.url or (HOSTED_URL if a.endpoint == "hosted" else LOCAL_URL)
    key = None if a.endpoint == "local" else (os.getenv("NVIDIA_API_KEY")
                                              or os.getenv("NGC_API_KEY"))
    if a.endpoint == "hosted" and not key:
        print("WARNING: hosted endpoint but no NVIDIA_API_KEY/NGC_API_KEY in env", file=sys.stderr)
    raw_dir = a.run_dir / "validation" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    n_ok = 0
    pdbs = list(a.pdbs)
    for i, pdb in enumerate(pdbs):
        seqs = chain_seqs(pdb)
        tgt, bnd = seqs.get(a.target_chain), seqs.get(a.binder_chain)
        if not tgt or not bnd:
            print(f"[skip] {pdb}: chains {list(seqs)} (need {a.target_chain}+{a.binder_chain})")
            continue
        name = f"cand{i:02d}"
        print(f"[holo] {name}: target {len(tgt)}aa + binder {len(bnd)}aa -> Boltz2 ...", flush=True)
        try:
            resp = boltz2_holo(tgt, bnd, url, key, a.max_retries)
        except Exception as e:  # noqa: BLE001
            print(f"[holo] {name} FAILED: {e}")
            continue
        (raw_dir / f"{name}.json").write_text(json.dumps(resp))
        iptm = (resp.get("iptm_scores") or ["?"])[0]
        print(f"[holo] {name} ok -> validation/raw/{name}.json (iptm={iptm})")
        n_ok += 1
        if a.throttle and i < len(pdbs) - 1:
            time.sleep(a.throttle)
    print(f"=== {n_ok} holo refold(s) written ===")

    if a.validate and n_ok:
        cmd = [sys.executable, a.validate, "--run-dir", str(a.run_dir),
               "--endpoint", a.endpoint, "--target-chain", a.target_chain,
               "--binder-chain", a.binder_chain]
        if a.hotspots:
            cmd += ["--hotspots", a.hotspots]
        print("=== running:", " ".join(cmd), "===", flush=True)
        return subprocess.run(cmd).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
