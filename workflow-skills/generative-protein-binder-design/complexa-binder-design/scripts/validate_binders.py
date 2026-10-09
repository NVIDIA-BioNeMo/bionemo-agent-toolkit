#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Validate Proteina-Complexa binders against the pipeline gate (Stage 3).

For each designed binder this computes, on an *independent* Boltz2 refold:

  * ipTM                - from the holo Boltz2 response (``iptm_scores``)
  * complex pLDDT       - holo ``complex_plddt_scores`` (0-1)
  * binder pLDDT        - mean CA pLDDT of the binder chain in the holo complex
  * ipSAE (min)         - canonical Dunbrack ipsae.py on the holo PAE matrix,
                          min over the two asymmetric interface directions
  * apo binder pLDDT    - a *new* Boltz2 prediction of the binder ALONE
  * binder apo<->holo RMSD- CA RMSD after Kabsch superposition (binder stability)
  * hotspot contact %   - fraction of conditioned hotspots with a binder
                          CB-CB contact < 13 Angstrom (CA for GLY)

Gate (all must hold): ipsae_min>=0.45 AND iptm>=0.65 AND binder_plddt>=0.70 AND
complex_plddt>=0.70 AND apo_binder_plddt>=0.70 AND binder_rmsd<=2.5 AND
(hotspot_contact_frac>=0.20 when the design was hotspot-conditioned).

Every design - pass AND fail - is written to validation_scores.json/.csv and
ranked_binders.json/.csv, each with a ``pass`` flag and a ``failure_reason``
listing *all* gates missed (or the verbatim error if a design could not be scored).
When validation/refold_batch.json exists, only its current candidates are scored;
missing or stale responses remain failed rows rather than disappearing.

Validation is always UNCONDITIONED: the refold sees only sequences, never the
hotspot list; the hotspot check is an independent geometric test on the result.

Usage:
  python validate_binders.py --run-dir outputs/<target>_<run> --hotspots <hotspots.json>
  # recompute-only (no live apo predictions):
  python validate_binders.py --run-dir <dir> --hotspots <h.json> --no-apo

Arguments: run directory; optional hotspots, endpoint, cached apo directory and
  scoring cutoffs (see --help).
Output: JSON/CSV ranked binders and validation scores, retaining failed rows.
Exit codes: 0 tables written (including failed designs), 2 invalid/missing inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------- gate defaults
GATE = {
    "ipsae_min": ("min", 0.45),
    "iptm": ("min", 0.65),
    "binder_plddt": ("min", 0.70),
    "complex_plddt": ("min", 0.70),
    "apo_binder_plddt": ("min", 0.70),
    "binder_rmsd": ("max", 2.50),
    "hotspot_contact_frac": ("min", 0.20),
}

from boltz2_endpoint import HOSTED_URL, LOCAL_URL, open_prediction, validate_endpoint
from execution import bounded_int
from refold_batch import load_batch

# Keep in sync with the reviewed download pin in fetch_ipsae.sh and VENDOR.md.
IPSAE_SHA256 = "10cf9b08c68c91e06cb28526cf2026f47a3980c9048fd3226d13e3304eaf1c27"

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


# ----------------------------------------------------------------------------- env / auth
def load_api_key(env_files: list[Path] | None = None) -> str | None:
    """Shell env first, then optional dotenv files; NVIDIA_API_KEY -> NGC_API_KEY."""
    for var in ("NVIDIA_API_KEY", "NGC_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    for env_path in (env_files or []):
        if not env_path or not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in ("NVIDIA_API_KEY", "NGC_API_KEY") and v:
                return v
    return None


# ----------------------------------------------------------------------------- mmCIF parsing
def parse_cif_atoms(cif_text: str) -> list[dict]:
    """Minimal _atom_site loop parser for Boltz2 mmCIF. Returns ATOM rows."""
    cols: list[str] = []
    atoms: list[dict] = []
    for line in cif_text.splitlines():
        s = line.strip()
        if s.startswith("_atom_site."):
            cols.append(s.split(".", 1)[1])
            continue
        if cols and (s.startswith("ATOM") or s.startswith("HETATM")):
            f = s.split()
            if len(f) < len(cols):
                continue
            idx = {c: i for i, c in enumerate(cols)}
            chain = f[idx["label_asym_id"]]
            resnum = f[idx["label_seq_id"]]
            if resnum == ".":
                continue  # ligand
            atoms.append({
                "chain": chain,
                "resnum": int(resnum),
                "resname": f[idx["label_comp_id"]],
                "atom": f[idx["label_atom_id"]],
                "xyz": np.array([float(f[idx["Cartn_x"]]),
                                 float(f[idx["Cartn_y"]]),
                                 float(f[idx["Cartn_z"]])]),
                "bfac": float(f[idx["B_iso_or_equiv"]]),
            })
        elif cols and atoms and (s.startswith("loop_") or (s.startswith("_") and not s.startswith("_atom_site."))):
            break
    return atoms


def chain_ca(atoms: list[dict], chain: str) -> list[dict]:
    """CA atoms of a chain, ordered by residue number."""
    cas = [a for a in atoms if a["chain"] == chain and a["atom"] == "CA"]
    return sorted(cas, key=lambda a: a["resnum"])


def chain_sequence(atoms: list[dict], chain: str) -> str:
    return "".join(THREE_TO_ONE.get(a["resname"], "X") for a in chain_ca(atoms, chain))


def chain_mean_ca_plddt(atoms: list[dict], chain: str) -> float:
    """Mean CA B-factor (=pLDDT) of a chain, normalised to 0-1 (B-factor is 0-100)."""
    bf = [a["bfac"] for a in chain_ca(atoms, chain)]
    return float(np.mean(bf) / 100.0) if bf else float("nan")


def residue_cb(atoms: list[dict], chain: str, resnum: int) -> np.ndarray | None:
    """CB coord of a residue (CA for glycine / missing CB)."""
    res = [a for a in atoms if a["chain"] == chain and a["resnum"] == resnum]
    if not res:
        return None
    for a in res:
        if a["atom"] == "CB":
            return a["xyz"]
    for a in res:
        if a["atom"] == "CA":
            return a["xyz"]
    return None


def chain_cb_coords(atoms: list[dict], chain: str) -> np.ndarray:
    coords = []
    seen = set()
    for a in sorted([x for x in atoms if x["chain"] == chain], key=lambda x: x["resnum"]):
        if a["resnum"] in seen:
            continue
        cb = residue_cb(atoms, chain, a["resnum"])
        if cb is not None:
            coords.append(cb)
            seen.add(a["resnum"])
    return np.array(coords)


# ----------------------------------------------------------------------------- geometry
def kabsch_rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    """CA RMSD of P onto Q after optimal superposition. P,Q are (N,3), aligned 1:1."""
    if P.shape != Q.shape or len(P) == 0:
        return float("nan")
    Pc = P - P.mean(axis=0)
    Qc = Q - Q.mean(axis=0)
    H = Pc.T @ Qc
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    P_rot = Pc @ R.T
    return float(np.sqrt(np.mean(np.sum((P_rot - Qc) ** 2, axis=1))))


def hotspot_contacts(atoms: list[dict], target_chain: str, binder_chain: str,
                     hotspots: list[dict], cutoff: float = 13.0) -> dict:
    """Fraction of hotspots with a binder CB within `cutoff` Angstrom of the hotspot CB."""
    binder_cb = chain_cb_coords(atoms, binder_chain)
    details = []
    n_contact = 0
    for hs in hotspots:
        pos = hs.get("position")
        cb = residue_cb(atoms, target_chain, pos)
        if cb is None or len(binder_cb) == 0:
            details.append({"position": pos, "contacted": False, "min_cb_dist": None})
            continue
        dmin = float(np.min(np.linalg.norm(binder_cb - cb, axis=1)))
        contacted = dmin < cutoff
        n_contact += int(contacted)
        details.append({"position": pos, "contacted": contacted, "min_cb_dist": round(dmin, 2)})
    frac = n_contact / len(hotspots) if hotspots else None
    return {"n_hotspots": len(hotspots), "n_contacted": n_contact,
            "contact_frac": frac, "cutoff": cutoff, "per_hotspot": details}


# ----------------------------------------------------------------------------- ipSAE
def run_ipsae(ipsae_py: Path, cif_text: str, pae: np.ndarray,
              pair_chains_iptm: dict | None, workdir: Path,
              pae_cutoff: int = 10, dist_cutoff: int = 10) -> dict:
    """Run canonical ipsae.py in Boltz mode; return ipsae_min/max + iptm_af."""
    if not ipsae_py.is_file():
        raise FileNotFoundError("ipSAE script missing; run bash scripts/fetch_ipsae.sh before scoring")
    expected = Path(__file__).resolve().parents[1] / "vendor" / "ipsae" / "ipsae.py"
    if ipsae_py.resolve() != expected or hashlib.sha256(ipsae_py.read_bytes()).hexdigest() != IPSAE_SHA256:
        raise ValueError("ipSAE must be the pinned script installed by scripts/fetch_ipsae.sh")
    bounded_int(pae_cutoff, 1, 100, "pae_cutoff")
    bounded_int(dist_cutoff, 1, 100, "dist_cutoff")
    workdir = workdir.resolve()
    stem = "model"
    cif_path = workdir / f"{stem}.cif"
    cif_path.write_text(cif_text)
    np.savez(workdir / f"pae_{stem}.npz", pae=pae)
    if pair_chains_iptm is not None:
        (workdir / f"confidence_{stem}.json").write_text(
            json.dumps({"pair_chains_iptm": pair_chains_iptm}))
    cmd = [sys.executable, str(ipsae_py), str(workdir / f"pae_{stem}.npz"),
           str(cif_path), str(pae_cutoff), str(dist_cutoff)]
    proc = subprocess.run(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    out_txt = workdir / f"{stem}_{pae_cutoff:02d}_{dist_cutoff:02d}.txt"
    if proc.returncode != 0 or not out_txt.exists():
        raise RuntimeError(f"ipsae.py produced no output: {proc.stdout}\n{proc.stderr}")
    asym = {}
    iptm_af = None
    for line in out_txt.read_text().splitlines():
        f = line.split()
        if len(f) < 6 or f[0] == "Chn1":
            continue
        if f[4] == "asym":
            asym[(f[0], f[1])] = float(f[5])  # ipSAE (d0res) column
            try:
                iptm_af = float(f[8])
            except (IndexError, ValueError):
                pass
    vals = list(asym.values())
    return {
        "ipsae_min": min(vals) if vals else None,
        "ipsae_max": max(vals) if vals else None,
        "ipsae_asym": {f"{a}->{b}": v for (a, b), v in asym.items()},
        "iptm_af_ipsae": iptm_af,
    }


# ----------------------------------------------------------------------------- Boltz2 apo call
def boltz2_predict_apo(seq: str, url: str, api_key: str | None,
                       recycling_steps: int = 3, sampling_steps: int = 50,
                       max_retries: int = 5, base_delay: float = 10.0) -> dict:
    """Single-chain (apo) Boltz2 prediction with exponential backoff on rate limits
    (HTTP 429) / 5xx / transient network errors, honoring Retry-After when present."""
    body = {
        "polymers": [{"id": "A", "molecule_type": "protein", "sequence": seq}],
        "recycling_steps": recycling_steps,
        "sampling_steps": sampling_steps,
        "diffusion_samples": 1,
        "step_scale": 1.638,
        "output_format": "mmcif",
    }
    headers = {"Content-Type": "application/json"}
    if api_key:  # hosted needs Bearer auth; local NIM needs none
        headers["Authorization"] = f"Bearer {api_key}"
    validate_endpoint(url, hosted=bool(api_key))
    data = json.dumps(body).encode()
    last = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with open_prediction(req, timeout=900) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504) or attempt == max_retries:
                raise
            ra = e.headers.get("Retry-After") if e.headers else None
            delay = float(ra) if (ra and str(ra).isdigit()) else base_delay * (2 ** attempt)
            print(f"    [retry] apo HTTP {e.code}; waiting {min(delay,120):.0f}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr, flush=True)
            time.sleep(min(delay, 120))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt == max_retries:
                raise
            time.sleep(min(base_delay * (2 ** attempt), 120))
    raise last if last else RuntimeError("apo prediction retries exhausted")


# ----------------------------------------------------------------------------- gating
def evaluate_gate(metrics: dict, hotspot_conditioned: bool) -> tuple[bool, str | None]:
    reasons = []
    for key, (mode, thr) in GATE.items():
        if key == "hotspot_contact_frac" and not hotspot_conditioned:
            continue
        val = metrics.get(key)
        if isinstance(val, (bool, np.bool_)) or not isinstance(val, (int, float, np.integer, np.floating)) or not np.isfinite(val):
            reasons.append(f"{key}=NA (not measured)")
            continue
        if mode == "min" and val < thr:
            reasons.append(f"{key}={val:.3f} < {thr}")
        elif mode == "max" and val > thr:
            reasons.append(f"{key}={val:.3f} > {thr}")
    return (len(reasons) == 0), ("; ".join(reasons) if reasons else None)


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--hotspots", type=Path, help="hotspots.json (default: unconditioned)")
    ap.add_argument("--target-chain", default="A")
    ap.add_argument("--binder-chain", default="B")
    ap.add_argument("--endpoint", choices=["hosted", "local"], default="hosted")
    ap.add_argument("--url", default=None, help="override the Boltz2 URL for apo predictions")
    ap.add_argument("--env-file", default=None,
                    help="optional dotenv file to read NVIDIA_API_KEY/NGC_API_KEY from "
                         "(shell env always takes precedence)")
    ap.add_argument("--no-apo", action="store_true",
                    help="skip live apo predictions; record apo/RMSD as not-run")
    ap.add_argument("--apo-dir", type=Path, default=None,
                    help="reuse apo predictions from this dir (default: <run-dir>/validation/apo). "
                         "apo is binder-only so it is identical across target-conditioning modes.")
    ap.add_argument("--pae-cutoff", type=int, default=10)
    ap.add_argument("--dist-cutoff", type=int, default=10)
    ap.add_argument("--contact-cutoff", type=float, default=13.0)
    args = ap.parse_args()
    try:
        bounded_int(args.pae_cutoff, 1, 100, "pae-cutoff")
        bounded_int(args.dist_cutoff, 1, 100, "dist-cutoff")
        if not np.isfinite(args.contact_cutoff) or not 0 < args.contact_cutoff <= 100:
            raise ValueError("contact-cutoff must be greater than 0 and at most 100 Angstrom")
        url = validate_endpoint(args.url or (HOSTED_URL if args.endpoint == "hosted" else LOCAL_URL),
                                hosted=args.endpoint == "hosted")
    except ValueError as error:
        ap.error(str(error))

    skill_root = Path(__file__).resolve().parents[1]
    ipsae_py = skill_root / "vendor" / "ipsae" / "ipsae.py"

    run_dir = args.run_dir
    raw_dir = run_dir / "validation" / "raw"
    try:
        batch = load_batch(run_dir)
    except (OSError, ValueError) as error:
        print(f"ERROR: cannot read current refold batch: {error}", file=sys.stderr)
        return 2
    # A current batch is authoritative, including candidates whose calls were
    # interrupted before writing a response. Older files are retained as evidence.
    raws = ([raw_dir / f"{name}.json" for name in batch["candidates"]]
            if batch is not None else sorted(raw_dir.glob("*.json")))
    if not raws:
        print(f"ERROR: no holo Boltz2 raw JSONs under {raw_dir}", file=sys.stderr)
        return 2

    hotspots = []
    hotspot_conditioned = False
    if args.hotspots and args.hotspots.exists():
        hdata = json.loads(args.hotspots.read_text())
        hotspots = hdata if isinstance(hdata, list) else hdata.get("hotspot_residues", [])
        hotspot_conditioned = len(hotspots) > 0

    env_files: list[Path] = []
    if args.env_file:
        env_files.append(Path(args.env_file))
    if os.environ.get("COMPLEXA_SKILL_ENV"):
        env_files.append(Path(os.environ["COMPLEXA_SKILL_ENV"]))
    # Fall back to a dotenv file at the skill root (os.extsep + "env" == ".env").
    env_files.append(skill_root / (os.extsep + "env"))
    api_key = None if args.endpoint == "local" else load_api_key(env_files)

    apo_dir = args.apo_dir if args.apo_dir is not None else (run_dir / "validation" / "apo")
    apo_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for raw_path in raws:
        name = raw_path.name[:-5]  # strip .json
        rec: dict = {**dict.fromkeys(GATE), "name": name, "failure_reason": None,
                     "batch_id": batch["batch_id"] if batch else None}
        try:
            if batch is not None and not raw_path.exists():
                raise ValueError("holo response missing for current refold batch")
            raw = json.loads(raw_path.read_text())
            metadata = raw.get("_refold", {})
            if batch is not None and metadata.get("batch_id") != batch["batch_id"]:
                raise ValueError("holo response does not belong to current refold batch")
            if batch is None and metadata.get("batch_id"):
                raise ValueError("refold batch record is missing; cannot identify current candidates")
            rec["source_pdb"] = metadata.get("source_pdb")
            if raw.get("failure_reason"):
                rec.update({"pass": False, "failure_reason": raw["failure_reason"]})
                rows.append(rec)
                continue
            target_chain = metadata.get("target_chain", args.target_chain)
            binder_chain = metadata.get("binder_chain", args.binder_chain)
            candidate_hotspots = metadata.get("hotspots", hotspots)
            conditioned = bool(candidate_hotspots)
            hotspot_conditioned = hotspot_conditioned or conditioned
            holo_cif = raw["structures"][0]["structure"]
            atoms = parse_cif_atoms(holo_cif)
            if target_chain == binder_chain or not chain_ca(atoms, target_chain) or not chain_ca(atoms, binder_chain):
                raise ValueError(f"prediction is missing distinct target/binder chains {target_chain}/{binder_chain}")
            pae = np.array(raw["pae"][0])
            pair_iptm = raw.get("pair_chains_iptm_scores", [None])[0]

            rec["iptm"] = float(raw["iptm_scores"][0])
            rec["complex_plddt"] = float(raw["complex_plddt_scores"][0])
            rec["binder_plddt"] = chain_mean_ca_plddt(atoms, binder_chain)
            rec["binder_len"] = len(chain_ca(atoms, binder_chain))
            binder_seq = chain_sequence(atoms, binder_chain)
            rec["binder_seq"] = binder_seq

            with tempfile.TemporaryDirectory() as td:
                ips = run_ipsae(ipsae_py, holo_cif, pae, pair_iptm, Path(td),
                                args.pae_cutoff, args.dist_cutoff)
            rec.update({"ipsae_min": ips["ipsae_min"], "ipsae_max": ips["ipsae_max"],
                        "ipsae_asym": ips["ipsae_asym"]})

            if conditioned:
                hc = hotspot_contacts(atoms, target_chain, binder_chain,
                                      candidate_hotspots, args.contact_cutoff)
                rec["hotspot_contact_frac"] = hc["contact_frac"]
                rec["hotspot_detail"] = hc
            else:
                rec["hotspot_contact_frac"] = None

            # ---- apo prediction + RMSD ----
            # Prefer a pre-computed apo cif (from slurm/run_boltz2_apo_batch.slurm);
            # fall back to a live call only when no precomputed apo exists.
            rec["apo_binder_plddt"] = None
            rec["binder_rmsd"] = None
            apo_cif_path = apo_dir / f"{name}.apo.cif"
            apo_raw_path = apo_dir / "raw" / f"{name}.json"
            apo_cif = None
            apo_plddt = None
            if apo_cif_path.exists():
                apo_cif = apo_cif_path.read_text()
                if apo_raw_path.exists():
                    apo_raw = json.loads(apo_raw_path.read_text())
                    cps = apo_raw.get("complex_plddt_scores") or apo_raw.get("confidence_scores")
                    apo_plddt = float(cps[0]) if cps else None
                rec["apo_status"] = "precomputed"
            elif args.no_apo:
                rec["apo_status"] = "skipped (--no-apo, no precomputed apo)"
            else:
                try:
                    apo = boltz2_predict_apo(binder_seq, url, api_key)
                    apo_cif = apo["structures"][0]["structure"]
                    apo_cif_path.write_text(apo_cif)
                    cps = apo.get("complex_plddt_scores") or apo.get("confidence_scores")
                    apo_plddt = float(cps[0]) if cps else None
                    rec["apo_status"] = f"live ({args.endpoint})"
                except Exception as e:  # noqa: BLE001
                    rec["apo_status"] = f"apo prediction failed: {e}"

            if apo_cif is not None:
                apo_atoms = parse_cif_atoms(apo_cif)
                apo_chain = sorted({a["chain"] for a in apo_atoms})[0]
                if chain_sequence(apo_atoms, apo_chain) != binder_seq:
                    raise ValueError("apo sequence differs from current holo binder; regenerate the apo refold")
                rec["apo_binder_plddt"] = apo_plddt if apo_plddt is not None \
                    else chain_mean_ca_plddt(apo_atoms, apo_chain)
                holo_ca = np.array([a["xyz"] for a in chain_ca(atoms, binder_chain)])
                apo_ca = np.array([a["xyz"] for a in chain_ca(apo_atoms, apo_chain)])
                if holo_ca.shape != apo_ca.shape or len(holo_ca) == 0:
                    raise ValueError("apo/holo binder CA counts differ; full-chain RMSD is unavailable")
                rec["binder_rmsd"] = kabsch_rmsd(holo_ca, apo_ca)

            passed, reason = evaluate_gate(rec, conditioned)
            rec["pass"] = passed
            if rec.get("apo_status", "").startswith("apo prediction failed:"):
                reason = "; ".join(filter(None, [reason, rec["apo_status"]]))
            rec["failure_reason"] = reason
        except Exception as e:  # noqa: BLE001
            rec["pass"] = False
            rec["failure_reason"] = f"scoring error: {e}"
        rows.append(rec)

    # ---- rank: passers first, then ipTM and ipSAE_min (missing values last) ----
    def sort_key(r):
        def descending(key):
            value = r.get(key)
            return -value if isinstance(value, (int, float)) and np.isfinite(value) else float("inf")
        return (not r.get("pass", False),
                descending("iptm"), descending("ipsae_min"))
    rows.sort(key=sort_key)
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    val_dir = run_dir / "validation"
    (val_dir / "validation_scores.json").write_text(json.dumps(rows, indent=2))
    (run_dir / "ranked_binders.json").write_text(json.dumps(rows, indent=2))

    csv_cols = ["rank", "name", "batch_id", "pass", "ipsae_min", "ipsae_max", "iptm",
                "binder_plddt", "complex_plddt", "apo_binder_plddt", "binder_rmsd",
                "hotspot_contact_frac", "binder_len", "apo_status", "failure_reason"]
    for path in (val_dir / "validation_scores.csv", run_dir / "ranked_binders.csv"):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=csv_cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in csv_cols})

    n_pass = sum(1 for r in rows if r.get("pass"))
    print(f"Scored {len(rows)} designs; {n_pass} PASS the gate "
          f"({'hotspot-conditioned' if hotspot_conditioned else 'unconditioned'}).")
    print(f"Wrote: {val_dir/'validation_scores.json'}, {run_dir/'ranked_binders.json'} (+ .csv)")
    for r in rows:
        flag = "PASS" if r.get("pass") else "fail"
        print(f"  [{flag}] {r['name'][:48]:48} ipSAEmin={r.get('ipsae_min')} "
              f"iptm={r.get('iptm')} bplddt={_f(r.get('binder_plddt'))} "
              f"rmsd={_f(r.get('binder_rmsd'))} hs={r.get('hotspot_contact_frac')}")
    return 0


def _f(x):
    return f"{x:.3f}" if isinstance(x, float) else x


if __name__ == "__main__":
    sys.exit(main())
