#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Pre-flight design planner / validator — run BEFORE app.py to see, per target,
exactly what would be conditioned on and whether it satisfies the design rules.
No GPU, no Slurm: just fetch the structure + UniProt, choose hotspots, re-align
them to the (possibly cropped) structure, and check every constraint.

For each target it reports and validates:
  * conditioned target LENGTH (after extracellular restriction + epitope crop)
  * hotspot POSITIONS, re-aligned to the structure (identity verified; numbering
    preserved through any truncation)
  * size budget:    target + longest binder  <=  MAX_COMPLEX_RESIDUES (500)
  * compactness:    hotspot pairwise diameter <=  30 Å  (else pick a compact subset)
  * count:          2 <= n_hotspots <= 15

Usage:
  python3 scripts/preflight_design.py IL1R1 HER2 PIN1 TNFL9 EFNB1 CEACAM1 AHSP
  python3 scripts/preflight_design.py P04626                 # by accession
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # Stage-1 modules live alongside this script
import pipeline as P            # noqa: E402
import hotspot_strategy as HS   # noqa: E402

MAX_DIAMETER_A = 30.0           # hotspot epitope must fit within this pairwise diameter


# ----------------------------------------------------------------- structure helpers
def _model(structure_path: Path):
    import gemmi
    st = gemmi.read_structure(str(structure_path))
    st.setup_entities()
    return st[0] if len(st) else None


def _residue_index(model):
    """(chain, pos) -> 3-letter residue name, for alignment/identity checks."""
    idx = {}
    for ch in model:
        for res in ch:
            idx[(ch.name, res.seqid.num)] = res.name
    return idx


def _cb_coords(model, hotspots):
    """{position: (x,y,z)} using Cβ (Cα fallback) for the hotspot chain."""
    want = {(str(h.get("chain", "A")), int(h["position"])) for h in hotspots}
    out = {}
    for ch in model:
        for res in ch:
            key = (ch.name, res.seqid.num)
            if key in want:
                a = res.find_atom("CB", "*") or res.find_atom("CA", "*")
                if a:
                    out[res.seqid.num] = (a.pos.x, a.pos.y, a.pos.z)
    return out


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _pairwise_diameter(coords: dict):
    pts = list(coords.values())
    return max((_dist(p, q) for i, p in enumerate(pts) for q in pts[i + 1:]), default=0.0)


def _compact_subset(positions, coords, max_d=MAX_DIAMETER_A):
    """Largest spatially compact subset with pairwise diameter <= max_d.
    Greedy: seed the residue with the most neighbours within max_d, then add the
    nearest residue that keeps the whole set's diameter <= max_d."""
    pos = [p for p in positions if p in coords]
    if len(pos) <= 1:
        return pos
    nbr = {p: sum(1 for q in pos if _dist(coords[p], coords[q]) <= max_d) for p in pos}
    seed = max(pos, key=lambda p: nbr[p])
    chosen = [seed]
    while True:
        best, bestd = None, None
        for p in pos:
            if p in chosen:
                continue
            if all(_dist(coords[p], coords[c]) <= max_d for c in chosen):
                d = min(_dist(coords[p], coords[c]) for c in chosen)
                if bestd is None or d < bestd:
                    best, bestd = p, d
        if best is None:
            break
        chosen.append(best)
    return sorted(chosen)


def _accessible_residue_count(model, segs):
    """How many residues fall inside the accessible (extracellular) segments."""
    if not segs:
        return sum(len(ch) for ch in model)
    n = 0
    for ch in model:
        for res in ch:
            if any(s <= res.seqid.num <= e for s, e in segs):
                n += 1
    return n


# ----------------------------------------------------------------- per-target plan
def plan(target: str, binder_max: int = None) -> dict:
    binder_max = binder_max if binder_max is not None else P.BINDER_LENGTH[1]
    cap_target = P.MAX_COMPLEX_RESIDUES - binder_max
    rep = {"target": target, "checks": {}}
    spec = P.resolve_target_spec(target)
    acc = spec.get("uniprot")
    rep["uniprot"] = acc
    rep["resolved_from"] = spec.get("resolved_from")
    if not acc:
        rep["error"] = "could not resolve to a UniProt accession"
        return rep

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # fetch AFDB structure
        P._run([sys.executable, str(P.FETCH_STRUCTURE), acc, "-o", str(td)], timeout=600)
        cif = next(iter(sorted(td.glob(f"AF-{acc}-*model*.cif"))), None)
        if cif is None:
            rep["error"] = "no AFDB model"
            return rep
        model = _model(cif)
        full_len = sum(len(ch) for ch in model)
        rep["full_length"] = full_len

        # UniProt entry -> accessibility + functional hotspots
        p = P._run([sys.executable, str(P.UNIPROT_TOOLS), "get", acc], timeout=300)
        entry = json.loads(p.stdout)
        entry = entry if "features" in entry else entry.get("results", [entry])[0]
        # Same resolver the live pipeline uses: PDB co-complex interface (gold) ->
        # UniProt functional, restricted to the accessible/extracellular range.
        hs, segs, provenance, hmsgs = HS.resolve_hotspots(entry)
        acc_info = HS.accessibility(entry)
        rep["topology"] = acc_info["note"]
        rep["accessible_residues"] = _accessible_residue_count(model, segs)
        rep["source"] = provenance
        rep["uniprot_messages"] = hmsgs
        rep["raw_hotspots"] = [f"{h['chain']}{h['position']}({h.get('source', '?')})" for h in hs]

        # align to structure: keep only residues present, attach identity
        idx = _residue_index(model)
        aligned = []
        for h in hs:
            key = (str(h.get("chain", "A")), int(h["position"]))
            if key in idx:
                aligned.append({**h, "residue": idx[key]})
        rep["aligned_hotspots"] = [f"{h['chain']}{h['position']}({h['residue']})" for h in aligned]

        # compactness: pairwise diameter; subset if too sparse
        coords = _cb_coords(model, aligned)
        positions = [h["position"] for h in aligned if h["position"] in coords]
        diam = _pairwise_diameter(coords)
        rep["diameter_A_raw"] = round(diam, 1)
        if diam > MAX_DIAMETER_A and len(positions) > 1:
            keep = set(_compact_subset(positions, coords))
            dropped = [p for p in positions if p not in keep]
            aligned = [h for h in aligned if h["position"] in keep]
            rep["compaction"] = f"diameter {diam:.0f} Å > {MAX_DIAMETER_A:.0f} → kept {sorted(keep)}, dropped {sorted(dropped)}"
            coords = {p: coords[p] for p in keep}
            diam = _pairwise_diameter(coords)
        rep["diameter_A_final"] = round(diam, 1)

        # count: max 15 (closest to centroid), min 2
        if len(aligned) > P.HOTSPOT_MAX_RESIDUES and coords:
            cx = tuple(sum(coords[h["position"]][k] for h in aligned if h["position"] in coords) / len(coords) for k in range(3))
            aligned = sorted(aligned, key=lambda h: _dist(coords.get(h["position"], cx), cx))[:P.HOTSPOT_MAX_RESIDUES]
        rep["final_hotspots"] = [f"{h['chain']}{h['position']}({h.get('residue','?')})" for h in aligned]
        n = len(aligned)
        rep["n_hotspots"] = n

        # conditioning length: accessible region, then epitope crop to fit the cap
        cond_len = rep["accessible_residues"] if segs else full_len
        crop_note = (f"extracellular {segs}" if segs else "whole chain")
        if cond_len > cap_target and aligned:
            hot_pos = sorted(h["position"] for h in aligned)
            lo, hi = hot_pos[0], hot_pos[-1]
            pad = max(0, (cap_target - (hi - lo + 1)) // 2)
            w_lo, w_hi = lo - pad, hi + pad
            # count residues kept inside the window AND accessible segments
            kept = [res.seqid.num for ch in model for res in ch
                    if w_lo <= res.seqid.num <= w_hi and (not segs or any(s <= res.seqid.num <= e for s, e in segs))]
            cond_len = len(kept)
            crop_note = f"epitope crop A{min(kept)}-{max(kept)} within {('ECD ' if segs else '')}cap"
        rep["conditioned_length"] = cond_len
        rep["conditioning"] = crop_note

        # ---- validations ----
        rep["checks"]["size<=500"] = (cond_len + binder_max <= P.MAX_COMPLEX_RESIDUES,
                                      f"{cond_len}+{binder_max}={cond_len + binder_max}")
        rep["checks"]["compact<=30A"] = (diam <= MAX_DIAMETER_A, f"{diam:.0f} Å")
        rep["checks"][">=2_hotspots"] = (n >= P.HOTSPOT_MIN_RESIDUES, str(n))
        rep["checks"]["<=15_hotspots"] = (n <= P.HOTSPOT_MAX_RESIDUES, str(n))
    return rep


def _fmt(rep: dict) -> str:
    L = []
    head = f"━━━ {rep['target']} ({rep.get('uniprot','?')}) ━━━"
    L.append(head)
    if rep.get("error"):
        L.append(f"  ERROR: {rep['error']}")
        return "\n".join(L)
    L.append(f"  full length: {rep['full_length']} aa | {rep['topology']}")
    L.append(f"  conditioned on: {rep['conditioned_length']} aa  ({rep['conditioning']})")
    L.append(f"  hotspots (UniProt): raw={rep['raw_hotspots']}")
    if rep.get("compaction"):
        L.append(f"  compaction: {rep['compaction']}")
    L.append(f"  FINAL hotspots ({rep['n_hotspots']}): {rep['final_hotspots'] or '— NONE (needs PDB-interface/Paperclip)'}")
    for m in rep.get("uniprot_messages", []):
        L.append(f"    · {m}")
    ok = lambda b: "✓" if b else "✗"
    for name, (passed, detail) in rep["checks"].items():
        L.append(f"  [{ok(passed)}] {name}: {detail}")
    ready = all(p for p, _ in rep["checks"].values())
    L.append(f"  => {'READY' if ready else 'NEEDS ATTENTION'}")
    return "\n".join(L)


def main():
    targets = sys.argv[1:] or ["IL1R1", "HER2", "PIN1", "TNFL9", "EFNB1", "CEACAM1", "AHSP"]
    for t in targets:
        try:
            print(_fmt(plan(t)))
        except Exception as e:  # noqa: BLE001
            print(f"━━━ {t} ━━━\n  EXCEPTION: {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
