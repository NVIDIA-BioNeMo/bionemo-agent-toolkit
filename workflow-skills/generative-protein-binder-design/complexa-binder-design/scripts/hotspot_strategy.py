#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Evidence-based binder-hotspot strategy from a UniProt entry JSON.

WHY (verified on our 7-target run): UniProt ``Active site`` / ``Binding site``
features annotate CATALYTIC / small-molecule sites — frequently **intracellular**
or buried, i.e. the WRONG surface for a protein binder:
  * IL1R1 (P14778): the only ``Active site`` is residue 470 — the **cytoplasmic
    TIR** domain (topology: cytoplasmic 357-569). Unreachable by a binder.
  * HER2 (P04626): ``Binding``/``Active`` sites are the **cytoplasmic kinase**
    ATP pocket (726-734, 753, 845; topology: cytoplasmic 676-1255).
Leading with those steered both membrane targets intracellular.

NEW strategy (UniProt-only layer):
  1. ACCESSIBILITY — a binder can only reach the **extracellular topological
     domain** of a membrane protein; restrict everything to it. Soluble proteins
     (PIN1, AHSP) have no constraint.
  2. FUNCTIONAL EPITOPE candidates, filtered to the accessible range:
       a. ``Mutagenesis`` residues with a binding/interaction effect — these are
          experimentally validated functional residues, usually at interfaces
          (HER2 317-318 ERBB3-dimerization; IL1R1 K131 ligand binding;
          PIN1 K63/C113 catalysis; CEACAM1 N76/G81).
       b. annotated interaction/adhesion ``Region`` (e.g. CEACAM1 homophilic
          39-142) — used to focus the crop and boost nearby residues.
       c. ``Active site``/``Binding site``/``Site`` — kept ONLY when inside the
          accessible range (valid for soluble enzymes like PIN1; auto-dropped
          for the HER2 kinase / IL1R1 TIR).

The GOLD standard (interface residues from a co-complex PDB — 1ITB, 1S78/1N8Z,
6MGP, 6XO1, 1Z8U …) is a separate, heavier step; this module is the
UniProt-derived layer plus the extracellular-accessibility crop it enables.
"""
from __future__ import annotations

# Feature-type strings as they appear in the UniProtKB REST JSON `features` list.
_TOPO = "Topological domain"
_TM = "Transmembrane"
_SIGNAL = "Signal"
_MUTAGEN = "Mutagenesis"
_REGION = "Region"
_SITE_TYPES = ("Active site", "Binding site", "Site")

# Mutagenesis descriptions that signal an interface/binding/functional role.
_FUNC_HINT = ("interact", "bind", "affinit", "dimer", "adhesion", "receptor",
              "ligand", "signal", "reduc", "abolish", "impair", "loss", "decreas",
              "epitope", "complex", "associat")
# Region descriptions that mark an interaction surface worth focusing on.
_REGION_HINT = ("interact", "bind", "adhesion", "dimer", "homophilic",
                "heterophilic", "receptor", "epitope")


def _range(feat: dict):
    loc = feat.get("location", {}) or {}
    s = (loc.get("start") or {}).get("value")
    e = (loc.get("end") or {}).get("value")
    if s is None:
        return None
    return int(s), int(e if e is not None else s)


def accessibility(entry: dict) -> dict:
    """Where a binder can physically reach.

    Returns ``{is_membrane, extracellular, note}`` where ``extracellular`` is a
    list of ``(start, end)`` segments for a membrane protein, or ``None`` for a
    soluble protein (whole chain accessible)."""
    feats = entry.get("features", []) or []
    tms = [r for r in (_range(f) for f in feats if f.get("type") == _TM) if r]
    ecd = [r for r in (_range(f) for f in feats
                       if f.get("type") == _TOPO
                       and "extracellular" in (f.get("description", "") or "").lower()) if r]
    if not tms:
        return {"is_membrane": False, "extracellular": None,
                "note": "soluble — whole chain accessible"}
    return {"is_membrane": True, "extracellular": (ecd or None),
            "note": (f"membrane protein; extracellular segments {ecd}" if ecd
                     else "membrane protein but no extracellular TOPO_DOM — using whole chain")}


def _accessible(pos: int, segs) -> bool:
    return True if not segs else any(s <= pos <= e for s, e in segs)


def functional_hotspots(entry: dict, extracellular) -> tuple[list[dict], list[str]]:
    """UniProt-derived candidate hotspots, filtered to the accessible range.

    ``extracellular`` = list of ``(s,e)`` segments, or ``None`` (soluble → all
    accessible). Returns ``(hotspots, messages)`` where each hotspot is
    ``{chain, position, source, description}`` and ``source`` is one of
    ``mutagenesis`` | ``region`` | ``catalytic``."""
    feats = entry.get("features", []) or []
    msgs: list[str] = []
    interaction_regions = []  # (start, end, desc) — focus zones, not expanded wholesale
    points: list[tuple[int, str, str]] = []   # (pos, source, desc)

    for f in feats:
        ftype = f.get("type")
        rng = _range(f)
        if not rng:
            continue
        s, e = rng
        desc = f.get("description", "") or ""
        dlow = desc.lower()
        if ftype == _REGION and any(h in dlow for h in _REGION_HINT):
            interaction_regions.append((s, e, desc))
        elif ftype == _MUTAGEN and any(h in dlow for h in _FUNC_HINT):
            points.append((s, ftype, desc))                 # mutagenesis = single residue
        elif ftype in _SITE_TYPES:
            for pos in range(s, e + 1):
                points.append((pos, "catalytic", f"{ftype}: {desc}".strip(": ")))

    # Filter to the accessible (extracellular) range; drop the rest.
    n_dropped = 0
    kept: dict[int, dict] = {}
    for pos, ftype, desc in points:
        if not _accessible(pos, extracellular):
            n_dropped += 1
            continue
        src = "mutagenesis" if ftype == _MUTAGEN else "catalytic"
        # mutagenesis preferred over catalytic if both land on the same residue
        if pos not in kept or (src == "mutagenesis" and kept[pos]["source"] == "catalytic"):
            kept[pos] = {"chain": "A", "position": pos, "source": src, "description": desc[:80]}
    if n_dropped:
        msgs.append(f"dropped {n_dropped} UniProt functional residue(s) outside the "
                    "extracellular/accessible range (e.g. catalytic/cytoplasmic sites)")

    hotspots = [kept[p] for p in sorted(kept)]
    if interaction_regions:
        rdesc = "; ".join(f"{s}-{e} ({d})" for s, e, d in interaction_regions[:3])
        msgs.append(f"interaction region(s) annotated: {rdesc} — use to focus the epitope crop")
        # If we have no point residues but do have an interaction region, seed the
        # region midpoints so the design is at least centered on the right surface.
        if not hotspots:
            for s, e, d in interaction_regions:
                mid = (s + e) // 2
                if _accessible(mid, extracellular):
                    hotspots.append({"chain": "A", "position": mid, "source": "region",
                                     "description": d[:80]})
    return hotspots, msgs


def resolve_hotspots(entry: dict, pdb_fallback: bool = True) -> tuple[list[dict], list[int] | None, str, list[str]]:
    """Top-level hotspot resolver (consensus rule — fail loud, not silently wrong).

    Order: (1) **UniProt-functional + accessibility** — the trusted default; it is
    deterministic and was empirically correct where it fired, and when it finds
    nothing it fails LOUDLY (empty → preflight flags it). (2) **PDB co-complex
    interface** — only as a fallback WHEN UniProt is empty, and flagged for review
    (it can return crystal/non-biological contacts or the wrong partner for
    multi-domain crystal structures; the gold-standard slot is earned only once the
    extractor does biological-assembly + BSA scoring + partner matching).
    Returns ``(hotspots, accessible_segments, provenance, messages)``."""
    acc = accessibility(entry)
    segs = acc["extracellular"]
    msgs = [f"accessibility: {acc['note']}"]

    # 1. UniProt functional (trusted): mutagenesis + accessible sites, ECD-filtered.
    hs, hmsgs = functional_hotspots(entry, segs)
    msgs += hmsgs
    if hs:
        return hs, segs, "uniprot_functional", msgs

    # 2. PDB co-complex interface — fallback only, REVIEW required.
    if pdb_fallback:
        try:
            import pdb_interface as _PI
            iface, info = _PI.interface_hotspots(entry)
        except Exception as e:  # noqa: BLE001
            iface, info = [], {"note": f"pdb-interface error: {type(e).__name__}"}
        if segs:
            iface = [h for h in iface if _accessible(h["position"], segs)]
        if iface:
            msgs.append(f"UniProt empty → PDB interface fallback: {info.get('pdb')} "
                        f"(partner {info.get('partner_chains')}, id {info.get('identity')}, "
                        f"{len(iface)} accessible residue(s)) — REVIEW for crystal contacts/partner")
            return iface, segs, f"pdb_interface:{info.get('pdb')}(review)", msgs
        msgs.append(f"no usable PDB co-complex interface ({info.get('note', '')})")
    return [], segs, "none", msgs
