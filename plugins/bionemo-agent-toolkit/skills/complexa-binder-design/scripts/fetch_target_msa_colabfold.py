#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Fetch a target MSA (a3m) from the public ColabFold MMseqs2 API.

Used to produce the **target** polymer's MSA for the Stage 3 holo refold when no
entitled MSA-Search NIM (hosted or local) is available. The binder stays
single-sequence; only the target gets an MSA. This hits the same UniRef30 +
environmental databases the ColabFold / MSA-Search NIM uses, via the public
api.colabfold.com server (rate-limited; for occasional single-target use).

Usage:
  python fetch_target_msa_colabfold.py --seq-from-pdb target.pdb --chain A -o target.a3m
  python fetch_target_msa_colabfold.py --seq MKT... -o target.a3m
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import time
import urllib.parse
import urllib.request

HOST = "https://api.colabfold.com"
UA = "bionemo-nim-skills-colabfold-client/1.0"
AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
       "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
       "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
       "TYR": "Y", "VAL": "V"}


def seq_from_pdb(pdb: str, chain: str) -> str:
    out, seen = [], set()
    for ln in open(pdb):
        if ln.startswith("ATOM") and ln[12:16].strip() == "CA" and ln[21] == chain:
            key = ln[22:26]
            if key in seen:
                continue
            seen.add(key)
            out.append(AA3.get(ln[17:20].strip(), "X"))
    return "".join(out)


_UP_OK = set("ACDEFGHIKLMNPQRSTVWYX")
_LO_OK = set("acdefghiklmnpqrstvwyx")


def sanitize_a3m(a3m: str) -> str:
    """Map non-standard residue letters (B/J/O/U/Z/*, etc.) to X, preserving
    case, gaps ('-'/'.'), and alignment columns. The Boltz2 NIM a3m validator
    only accepts ARNDCQEGHILKMFPSTWYVX (+ lowercase insertions, '-'/'.'); raw
    ColabFold hits can contain other letters and get rejected as
    'invalid characters in sequence N'."""
    out = []
    for ln in a3m.splitlines():
        if ln.startswith(">") or not ln:
            out.append(ln)
            continue
        fixed = []
        for c in ln:
            if c in _UP_OK or c in _LO_OK or c in "-.":
                fixed.append(c)
            elif c.islower():
                fixed.append("x")
            else:
                fixed.append("X")
        out.append("".join(fixed))
    return "\n".join(out) + "\n"


def _post(path: str, data: dict) -> dict:
    req = urllib.request.Request(f"{HOST}/{path}",
                                 data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": UA}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _get_json(path: str) -> dict:
    req = urllib.request.Request(f"{HOST}/{path}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _download(ticket: str) -> bytes:
    req = urllib.request.Request(f"{HOST}/result/download/{ticket}",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def fetch_a3m(seq: str, mode: str = "env", poll_seconds: int = 10,
              max_wait: int = 900) -> str:
    query = f">101\n{seq}\n"
    sub = _post("ticket/msa", {"q": query, "mode": mode})
    tid = sub.get("id")
    status = sub.get("status")
    if not tid:
        raise SystemExit(f"submission failed: {sub}")
    print(f"ticket {tid} status {status}", file=sys.stderr)
    waited = 0
    while status in ("PENDING", "RUNNING", "UNKNOWN", "MAINTENANCE", None):
        if status == "MAINTENANCE":
            raise SystemExit("ColabFold API in MAINTENANCE; retry later")
        time.sleep(poll_seconds)
        waited += poll_seconds
        if waited > max_wait:
            raise SystemExit(f"timed out after {max_wait}s (last status {status})")
        status = _get_json(f"ticket/{tid}").get("status")
        print(f"  ... {waited}s status {status}", file=sys.stderr)
    if status != "COMPLETE":
        raise SystemExit(f"ColabFold job ended with status {status}")
    tar_bytes = _download(tid)
    # Merge the a3m files in the result tar (uniref + env), keeping one query header.
    a3m_parts = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        for m in tf.getmembers():
            if m.name.endswith(".a3m"):
                a3m_parts.append((m.name, tf.extractfile(m).read().decode(errors="replace")))
    if not a3m_parts:
        raise SystemExit("no .a3m in ColabFold result tar")
    a3m_parts.sort()  # deterministic order
    return sanitize_a3m("\n".join(txt for _, txt in a3m_parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--seq")
    g.add_argument("--seq-from-pdb")
    ap.add_argument("--chain", default="A")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--mode", default="env", help="ColabFold MSA mode (default env = uniref+env)")
    args = ap.parse_args()

    seq = args.seq or seq_from_pdb(args.seq_from_pdb, args.chain)
    if not seq:
        raise SystemExit("empty target sequence")
    print(f"target sequence: {len(seq)} aa", file=sys.stderr)
    a3m = fetch_a3m(seq, mode=args.mode)
    n_seqs = a3m.count("\n>") + a3m.lstrip().startswith(">")
    with open(args.out, "w") as fh:
        fh.write(a3m)
    print(f"wrote {args.out} (~{a3m.count('>')} sequences, {len(a3m)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
