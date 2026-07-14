#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Orchestrator for the Complexa protein-binder-design pipeline (public release).

`run(...)` is a GENERATOR that yields `Event`s so a caller can stream stage-by-stage
progress. Modes:

  * mode="score_existing"  — score/explore an already-produced run directory: runs
      validate_binders.py on existing holo + apo refolds and returns ranked binders.
      No GPU, fully self-contained.

  * mode="full"            — live run from a target: resolve structure + hotspots
      (Stage 1), register the target and run generation via the OPEN `complexa`
      CLI in $COMPLEXA_REPO (Stage 2: generate→filter→evaluate→analyze, AF2-reward
      gated), build the target MSA, then emit a Stage-3 handoff for the INDEPENDENT
      Boltz2/OpenFold3 NIM refold (driven by the agent / boltz2-nim skill); once the
      refolds exist it scores them. Requires a GPU host for Complexa + a Boltz2/OF3
      endpoint for validation.

This module shells out to separately-tested pieces rather than re-implementing them:
scripts/validate_binders.py, scripts/fetch_target_msa_colabfold.py,
vendor/science-skills/.../fetch_structure.py, and the `complexa` CLI. There is no
Slurm/sbatch or private-NIM dependency.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# UniProt accession + PDB-ID shapes, for classifying a free-text target.
_UNIPROT_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$")
_PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")

# ---------------------------------------------------------------------------
# Public layout: this module lives in <skill>/scripts/. Stage-1 tooling is
# vendored under <skill>/vendor/; Stage-2 drives the OPEN `complexa` CLI in the
# user's Proteina-Complexa checkout ($COMPLEXA_REPO) — no Slurm, no demo NIM.
import os

SCRIPTS = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS.parent
VENDOR = SKILL_DIR / "vendor"
OUTPUTS = Path(os.environ.get("COMPLEXA_OUTPUTS", "outputs"))  # cwd-relative by default

FETCH_STRUCTURE = VENDOR / "science-skills" / "alphafold_database_fetch_and_analyze" / "scripts" / "fetch_structure.py"
UNIPROT_TOOLS = VENDOR / "science-skills" / "uniprot_database" / "scripts" / "uniprot_tools.py"
FETCH_MSA = SCRIPTS / "fetch_target_msa_colabfold.py"
PDB_TO_TEMPLATE = SCRIPTS / "pdb_to_boltz_template_cif.py"
VALIDATE_BINDERS = SCRIPTS / "validate_binders.py"

# Open Proteina-Complexa release (https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa).
# Set COMPLEXA_REPO to your local checkout; Stage 2 runs the `complexa` CLI there.
COMPLEXA_BIN = os.environ.get("COMPLEXA_BIN", "complexa")
COMPLEXA_CONFIG = os.environ.get("COMPLEXA_CONFIG", "configs/search_binder_local_pipeline.yaml")


def _complexa_repo() -> Path:
    """Resolve $COMPLEXA_REPO lazily (only Stage 2 needs it; Stage 1 / scoring don't)."""
    r = os.environ.get("COMPLEXA_REPO")
    if not r:
        raise RuntimeError(
            "Set COMPLEXA_REPO to your Proteina-Complexa checkout "
            "(https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa) to run generation.")
    p = Path(r).expanduser()
    if not p.is_dir():
        raise RuntimeError(f"COMPLEXA_REPO is not a directory: {p}")
    return p


# Back-compat alias used by the extraction/discovery helpers below; resolves to the
# user's open checkout instead of the old Slurm run-root.
def _targets_dict() -> Path:
    return _complexa_repo() / "configs" / "targets" / "targets_dict.yaml"

# Complexa builds O(n^2) pairwise features over the FULL (target + binder) complex,
# and the JAX AF2-Multimer reward model (beam search) preallocates a big slice of
# the GPU, so the whole complex must stay small or generate OOMs. GLOBAL RULE: the
# combined binder + target must total <= MAX_COMPLEX_RESIDUES. The binder length
# range is BINDER_LENGTH; the target is cropped (around the epitope) so that
# target + the LONGEST binder still fits the budget.
BINDER_LENGTH = (64, 155)        # (min, max) designed binder length
MAX_COMPLEX_RESIDUES = 500       # hard cap on target + binder residues, total

# GPU fan-out (gen/eval njobs for `complexa design`). Each GPU evaluates a pool of
# candidates, AF2/RF3-reward-scored, written to the binder_results CSV with
# self_complex_i_pTM / self_complex_pLDDT. Public default is 1 GPU; raise to your
# GPU count for more parallelism/diversity.
N_DEVICES_DEFAULT = 1            # gen/eval njobs — set to your available GPU count
# No per-device cap: the AF2 gate is the SOLE selector — EVERY AF2-passing design
# is Boltz2-validated. MAX_VALIDATE_CEILING is only a runaway guard (a single
# freak run can't submit tens of thousands of Boltz2 folds). Set high enough to
# never bite in practice (the largest observed AF2-pass pool was PIN1 at 381).
MAX_VALIDATE_CEILING = 2000

# AF2 quality gate (PRIMARY selector). Rather than blindly Boltz2-validating a
# fixed top-N, we forward to Boltz2 ONLY the designs the generator's own
# AF2-Multimer is already confident in: interface pTM AND pLDDT both above
# threshold. Both columns are 0-1 scaled in the Complexa results CSV. A design
# that AF2 itself scores poorly (e.g. the collapsed v1/v2-mismatch backbones had
# i_pTM~0.08, pLDDT~0.56) is not worth an independent Boltz2 re-prediction.
AF2_IPTM_MIN = 0.70              # self_complex_i_pTM must exceed this
AF2_PLDDT_MIN = 0.70             # self_complex_pLDDT must exceed this


def validation_count(n_devices: int, n_validated: int = 0) -> int:
    """How many AF2-passing designs go to Boltz2. The AF2 gate (``AF2_IPTM_MIN`` /
    ``AF2_PLDDT_MIN``) is the SOLE selector — EVERY design that clears it is
    validated (no per-device cap). ``n_validated <= 0`` => MAX_VALIDATE_CEILING
    (effectively unlimited, runaway guard only); a positive value is an explicit
    user cap. NOTE: validation refolds the whole set, so a very large AF2-pass pool
    can be slow; cap it with an explicit n_validated if needed."""
    return int(n_validated) if int(n_validated) > 0 else MAX_VALIDATE_CEILING


def _max_target_residues(binder_max: int = BINDER_LENGTH[1]) -> int:
    """Largest target that keeps (target + longest binder) <= MAX_COMPLEX_RESIDUES.
    With the default 155-residue max binder this is 345."""
    return max(1, MAX_COMPLEX_RESIDUES - binder_max)


# Hotspot sanity (bindclaw convention): a binder grips ONE local epitope, so the
# hotspot set must be small and spatially compact — not scattered across domains.
HOTSPOT_MIN_RESIDUES = 1         # >=1 is acceptable (a single anchor hotspot is OK)
HOTSPOT_MAX_RESIDUES = 15        # bindclaw DEFAULT_MAX_HOTSPOT_RESIDUES
HOTSPOT_MAX_SPREAD_A = 30.0      # drop hotspots > this far (Å) from the epitope cluster


@dataclass
class Event:
    """A streamed progress event."""
    stage: str
    status: str          # "start" | "info" | "ok" | "error"
    message: str
    data: dict = field(default_factory=dict)

    def line(self) -> str:
        icon = {"start": "▶", "info": "·", "ok": "✓", "error": "✗"}.get(self.status, "·")
        return f"{icon} [{self.stage}] {self.message}"


# --------------------------------------------------------------------------- helpers
def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], cwd=(str(cwd) if cwd else None),
                          capture_output=True, text=True, timeout=timeout)


def list_run_dirs() -> list[str]:
    """Existing run directories under OUTPUTS that have a validation/ folder."""
    if not OUTPUTS.is_dir():
        return []
    return sorted(str(p) for p in OUTPUTS.iterdir() if (p / "validation").is_dir())


# --------------------------------------------------------------------------- target resolution
def resolve_target_spec(text: str, organism_id: str = "9606") -> dict:
    """Turn a free-text target NAME into a structure spec — the only thing the user
    types. Resolves across ALL organisms (not just human) so allergens, viral, and
    other non-human targets work (e.g. an allergen common name → its UniProt accession).

    Strategy: human+reviewed first (so a common human protein name stays human),
    then any reviewed organism, then any entry; raw text first, then an auto-spaced
    variant ('DerF21' → 'Der F 21') for allergen-style names. A UniProt accession or
    a 4-char PDB ID typed directly is still accepted, but the user need not know one."""
    t = text.strip()
    if _UNIPROT_RE.match(t.upper()):
        return {"uniprot": t.upper(), "resolved_from": f"{t} (UniProt accession)"}
    if _PDB_RE.match(t):
        return {"pdb": t.upper(), "resolved_from": f"{t} (PDB ID)"}

    # Match on protein NAME / gene exactly (not fuzzy full-text relevance, which
    # confidently returns the WRONG protein — e.g. freeform 'DerF21' matched human
    # RhoA). Build name variants: raw, a generic case/digit-spaced form
    # ('DerF21'→'Der F 21'), and an allergen-nomenclature form for 'Genus-species-num'
    # names ('derf21'/'DerF21'→'der f 21', 'Blag2'→'Bla g 2').
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)", " ", t)
    m_all = re.match(r"^([A-Za-z]{3})([A-Za-z])(\d+)$", t)
    allergen = f"{m_all.group(1)} {m_all.group(2)} {m_all.group(3)}" if m_all else None
    forms: list[str] = []
    for f in (t, spaced, allergen):
        if f and f not in forms:
            forms.append(f)
    # PREFER REVIEWED (Swiss-Prot) across ALL forms before any unreviewed entry —
    # reviewed entries are the ones with AFDB models; unreviewed TrEMBL hits (e.g.
    # A0A922HUI2) often have no AlphaFold structure. Within reviewed, human first.
    queries: list[str] = []
    for scope in (f" AND organism_id:{organism_id} AND reviewed:true", " AND reviewed:true"):
        for f in forms:
            queries.append(f'(protein_name:"{f}" OR gene:"{f}"){scope}')
    for f in forms:  # unreviewed fallback, last resort
        queries.append(f'(protein_name:"{f}" OR gene:"{f}")')

    def _search(q: str) -> dict | None:
        p = _run([sys.executable, UNIPROT_TOOLS, "search", q, "--limit", "1",
                  "--fields", "accession,id,protein_name,organism_name"], timeout=120)
        try:
            res = json.loads(p.stdout)
            results = res.get("results", res if isinstance(res, list) else [])
            return results[0] if results else None
        except Exception:  # noqa: BLE001
            return None

    hit = next((h for h in (_search(q) for q in queries) if h), None)
    acc = hit.get("primaryAccession") if hit else None
    if not acc:
        raise RuntimeError(
            f"could not find a UniProt entry for '{text}'. Check the spelling, or try "
            "the protein's common gene/protein name or UniProt accession, or upload a structure.")
    org = (hit.get("organism", {}) or {}).get("scientificName", "")
    return {"uniprot": acc, "resolved_from": f"{t} → UniProt {acc}" + (f" ({org})" if org else "")}


# --------------------------------------------------------------------------- Stage 1
def resolve_target(spec: dict, run_dir: Path) -> Iterator[Event]:
    """Resolve a target structure (Stage 1). spec one of:
       {"uniprot": "P00533"} | {"pdb": "1WWW"} | {"pdb_path": "/path.pdb"}.
       Writes run_dir/target.pdb (or .cif). Hotspots are best-effort from UniProt
       features when a UniProt id is given (numbering == AFDB numbering)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    if spec.get("uniprot"):
        acc = spec["uniprot"]
        yield Event("stage1", "start", f"fetching AFDB model for UniProt {acc}")
        p = _run([sys.executable, FETCH_STRUCTURE, acc, "-o", run_dir], timeout=600)
        cif = next(iter(sorted(run_dir.glob(f"AF-{acc}-*model*.cif"))), None)
        if cif is None:
            # fetch_structure.py prints "not found in the AlphaFold Database" to
            # STDOUT (returncode 0), so surface stdout+stderr, not just stderr.
            detail = " ".join((p.stdout + " " + p.stderr).split())[-400:]
            raise RuntimeError(
                f"no AlphaFold model for UniProt {acc} — {detail or 'AFDB has no entry for this accession.'} "
                "(Unreviewed/TrEMBL entries often lack an AFDB model; try the reviewed "
                "Swiss-Prot accession, a PDB ID, or upload a structure.)")
        (run_dir / "target.cif").write_text(cif.read_text())
        yield Event("stage1", "ok", f"AFDB model saved ({cif.name}); numbering = UniProt")
        yield from _uniprot_hotspots(acc, run_dir)
    elif spec.get("pdb"):
        pid = spec["pdb"]
        yield Event("stage1", "start", f"fetching RCSB {pid}")
        p = _run([sys.executable, FETCH_STRUCTURE, "--pdb", pid, "-o", run_dir], timeout=300) \
            if "--pdb" in FETCH_STRUCTURE.read_text() else None
        # fetch_structure.py (vendored) is AFDB-only; RCSB is a plain download
        import urllib.request
        data = urllib.request.urlopen(f"https://files.rcsb.org/download/{pid.lower()}.pdb", timeout=120).read()
        (run_dir / "target.pdb").write_bytes(data)
        yield Event("stage1", "ok", f"RCSB {pid} saved ({len(data)} bytes); "
                                    "verify hotspot numbering against this file (auth numbering may be offset)")
    elif spec.get("pdb_path"):
        src = Path(spec["pdb_path"])
        (run_dir / "target.pdb").write_text(src.read_text())
        yield Event("stage1", "ok", f"using uploaded file {src.name} (verify hotspot numbering)")
    elif spec.get("cif_path"):
        src = Path(spec["cif_path"])
        (run_dir / "target.cif").write_text(src.read_text())
        yield Event("stage1", "ok", f"using uploaded file {src.name} (verify hotspot numbering)")
    else:
        raise ValueError("target spec needs one of: uniprot, pdb, pdb_path, cif_path")


def _uniprot_hotspots(acc: str, run_dir: Path) -> Iterator[Event]:
    """Best-effort hotspot candidates from UniProt Active/Binding-site features."""
    # Never clobber an existing richer hotspots.json (e.g. Paperclip-derived) on a
    # re-run — preserve it so the run stays conditioned.
    existing = run_dir / "hotspots.json"
    if existing.exists():
        try:
            prev = json.loads(existing.read_text())
            prev_hs = prev.get("hotspot_residues") if isinstance(prev, dict) else prev
            if prev_hs:
                yield Event("stage1", "ok",
                            f"keeping existing hotspots.json ({len(prev_hs)} residues) — not overwriting",
                            {"hotspots": prev_hs[:20]})
                return
        except Exception:  # noqa: BLE001
            pass
    yield Event("stage1", "info", f"reading UniProt features for {acc}")
    p = _run([sys.executable, UNIPROT_TOOLS, "get", acc], timeout=300)
    if p.returncode != 0:
        yield Event("stage1", "info", "UniProt features unavailable; leaving hotspots empty")
        return
    try:
        entry = json.loads(p.stdout)
        entry = entry if "features" in entry else entry.get("results", [entry])[0]
    except Exception:
        yield Event("stage1", "info", "could not parse UniProt entry; hotspots empty")
        return
    # Evidence-based strategy (hotspot_strategy.resolve_hotspots): the
    # PROTEIN-PROTEIN INTERFACE residues from a co-complex PDB (gold standard) ->
    # UniProt functional residues (mutagenesis + accessible sites), all restricted
    # to the EXTRACELLULAR/accessible range. Replaces 'Active/Binding site first',
    # which annotates catalytic/intracellular pockets — the wrong surface for a
    # binder epitope (verified: IL1R1 470 = cytoplasmic TIR; HER2 = kinase ATP site).
    try:
        import hotspot_strategy as _HS
        hs, segs, provenance, hmsgs = _HS.resolve_hotspots(entry)
    except Exception as e:  # noqa: BLE001
        yield Event("stage1", "info", f"hotspot strategy error ({type(e).__name__}); hotspots empty")
        hs, segs, provenance, hmsgs = [], None, "none", []
    for m in hmsgs:
        yield Event("stage1", "info", m)
    out = {"target": acc, "uniprot": acc,
           "numbering": "AFDB == UniProt numbering; verify residue identity in the cif",
           "source": provenance, "accessible_segments": segs,
           "hotspot_residues": hs}
    (run_dir / "hotspots.json").write_text(json.dumps(out, indent=2))
    if hs:
        yield Event("stage1", "ok",
                    f"{len(hs)} hotspot candidate(s) [{provenance}] "
                    "(downstream pruning enforces compactness + count)",
                    {"hotspots": hs[:20]})
    else:
        # Nothing from PDB interface or UniProt — escalate to the Paperclip
        # full-text literature fallback rather than silently going unconditioned.
        yield Event("stage1", "info",
                    f"no PDB-interface or UniProt functional hotspots for {acc} — fall back to the "
                    "Paperclip literature search (prompts/hotspot_paperclip.md), then re-run with "
                    "--hotspots. Proceeding as-is would design UNCONDITIONED.",
                    {"needs_paperclip": True, "hotspots": []})


# --------------------------------------------------------------------------- structure alignment
def _structure_residue_index(structure_path: Path) -> dict[tuple[str, int], str]:
    """Map (chain_id, residue_number) -> 3-letter residue name from a pdb/cif."""
    import gemmi
    st = gemmi.read_structure(str(structure_path))
    idx: dict[tuple[str, int], str] = {}
    if len(st) == 0:
        return idx
    for chain in st[0]:
        for res in chain:
            idx[(chain.name, res.seqid.num)] = res.name
    return idx


def align_hotspots_to_structure(
        hotspots: list[dict], structure_path: Path) -> tuple[list[dict], list[dict]]:
    """Keep only hotspots whose (chain, position) exist in the structure coords.

    This is the deterministic 'ordering' guard: UniProt/literature residue
    numbers (UniProt-canonical) are validated against the structure the designer
    actually consumes (AFDB == UniProt numbering; experimental/cropped PDBs are
    often offset). Returns (kept, dropped). Each kept hotspot gets `residue` set
    to the actual 3-letter name read from coordinates, plus `identity_match` when
    the caller supplied an expected residue. Dropped hotspots get `drop_reason`.
    If the structure can't be read, hotspots pass through unchanged (fail open).
    """
    try:
        idx = _structure_residue_index(Path(structure_path))
    except Exception:  # noqa: BLE001 — never let alignment crash the run
        return list(hotspots), []
    if not idx:
        return list(hotspots), []
    kept: list[dict] = []
    dropped: list[dict] = []
    for hs in hotspots:
        chain = str(hs.get("chain", "A"))
        pos = hs.get("position")
        actual = idx.get((chain, pos))
        if actual is None:
            dropped.append({**hs, "drop_reason": f"{chain}{pos} not in structure coordinates"})
            continue
        expected = str(hs.get("residue") or "").upper()
        rec = {**hs, "residue": actual}
        if expected and expected != actual:
            rec["identity_match"] = False
            rec["expected_residue"] = expected
        elif expected:
            rec["identity_match"] = True
        kept.append(rec)
    return kept, dropped


# --------------------------------------------------------------------------- Paperclip hotspot fallback
_AA3_NAMES = ("Ala", "Arg", "Asn", "Asp", "Cys", "Gln", "Glu", "Gly", "His", "Ile",
              "Leu", "Lys", "Met", "Phe", "Pro", "Ser", "Thr", "Trp", "Tyr", "Val")
_AA3_RE = re.compile(r"\b(" + "|".join(_AA3_NAMES) + r")\s*-?\s*(\d{1,4})\b", re.I)


def _paperclip_available() -> bool:
    import shutil
    return shutil.which("paperclip") is not None


def _uniprot_name(acc: str) -> list[str]:
    """Common protein name(s) + gene for an accession — Paperclip search terms.

    Includes UniProt SHORT names (the protein's common short name) which is what the
    binding/epitope literature actually uses; the verbose recommendedName is poor for search."""
    p = _run([sys.executable, UNIPROT_TOOLS, "get", acc], timeout=120)
    shorts: list[str] = []
    longs: list[str] = []
    try:
        e = json.loads(p.stdout)
        e = e if "proteinDescription" in e else e.get("results", [e])[0]
        pd = e.get("proteinDescription", {})
        for blk in [pd.get("recommendedName", {})] + pd.get("alternativeNames", []):
            fv = blk.get("fullName", {}).get("value")
            if fv:
                longs.append(fv)
            for sn in blk.get("shortNames", []):
                sv = sn.get("value")
                if sv:
                    shorts.append(sv)
        for g in e.get("genes", []):
            gv = g.get("geneName", {}).get("value")
            if gv:
                shorts.append(gv)
    except Exception:  # noqa: BLE001
        pass
    # short names first (best for literature search), then full names
    return shorts + longs


def paperclip_hotspots(acc: str, structure_path: Path, run_dir: Path) -> Iterator[Event]:
    """Agent-free Paperclip literature fallback (runs when UniProt has no hotspots).

    Drives the `paperclip` CLI (search → map) to pull residue-level epitope/binding
    evidence from full-text papers, then keeps ONLY residues whose 3-letter identity
    matches the resolved structure — auto-correcting a literature↔structure numbering
    offset (e.g. mature vs full-length). The structure is the ground-truth filter, so
    fuzzy/wrong residue mentions are discarded. Writes hotspots.json on success."""
    if not _paperclip_available():
        yield Event("stage1", "info",
                    "paperclip CLI not found in PATH — cannot run literature fallback; "
                    "proceeding UNCONDITIONED.")
        return
    names = _uniprot_name(acc)
    # Prefer a clean, searchable designation (strip isoform '.0101' / verbose
    # prefixes): pull a short allergen-style name if present, else the first name.
    short = None
    for n in names:
        m = re.search(r"\b([A-Z][a-z]{2} [a-z] \d+)\b", n)
        if m:
            short = m.group(1)
            break
    name = short or (names[0] if names else acc)
    yield Event("stage1", "start", f"Paperclip literature search for '{name}' hotspots")
    sid = None
    # paperclip (>=0.1.4) REQUIRES a source: `-s pmc` = full-text PubMed Central, the
    # richest source for residue-level mutagenesis / binding / interface evidence.
    for q in (f"{name} binding epitope residues", f"{name} mutagenesis hot spot",
              f"{name} interface contact residues"):
        r = _run(["paperclip", "search", "-s", "pmc", q, "-n", "6"], timeout=120)
        m = re.search(r"\[(s_[0-9a-f]+)\]", r.stdout or "")
        if m:
            sid = m.group(1)
            break
    if not sid:
        yield Event("stage1", "info", f"Paperclip found no papers for '{name}' — UNCONDITIONED.")
        return
    yield Event("stage1", "info", f"Paperclip result set {sid}; extracting residue numbers")
    mp = _run(["paperclip", "map", "--from", sid,
               f"Extract ALL specific {name} residue numbers that are antibody/IgE epitope, "
               "binding, interface, or mutagenesis hot spots. Output each as 3-letter code + "
               "number, e.g. Tyr56."], timeout=200)
    text = mp.stdout or ""
    fm = re.search(r"(/\S*map_\S+\.txt)", text)
    if fm:
        c = _run(["paperclip", "cat", fm.group(1)], timeout=60)
        text += "\n" + (c.stdout or "")
    from collections import Counter
    mentions = Counter((aa.upper(), int(pos)) for aa, pos in _AA3_RE.findall(text))
    cand = sorted(mentions)
    if not cand:
        yield Event("stage1", "info",
                    f"Paperclip returned no parseable residue numbers for '{name}' — UNCONDITIONED.")
        return
    try:
        idx = _structure_residue_index(Path(structure_path))
    except Exception:  # noqa: BLE001
        idx = {}
    # Find the literature→structure numbering offset that confirms the most residues.
    best_off, best_n = 0, 0
    for off in range(-30, 31):
        n = sum(1 for aa, pos in cand if idx.get(("A", pos + off)) == aa)
        if n > best_n:
            best_n, best_off = n, off
    if best_n < 3:
        yield Event("stage1", "info",
                    f"Paperclip proposed {len(cand)} residue(s) but only {best_n} match the "
                    f"structure ({structure_path.name}) — numbering mismatch, proceeding "
                    "UNCONDITIONED (verify manually).")
        return
    # Rank by how often each residue is discussed (proxy for importance) and keep a
    # focused epitope — conditioning Complexa on dozens of scattered residues is bad.
    _CAP = 10
    seen: set[int] = set()
    confirmed: list[dict] = []
    for aa, pos in sorted(cand, key=lambda k: mentions[k], reverse=True):
        sp = pos + best_off
        if idx.get(("A", sp)) == aa and sp not in seen:
            seen.add(sp)
            confirmed.append({"chain": "A", "position": sp, "residue": aa,
                              "source": "paperclip", "lit_position": pos,
                              "mentions": mentions[(aa, pos)]})
        if len(confirmed) >= _CAP:
            break
    confirmed.sort(key=lambda h: h["position"])
    wrapper = {"target": acc, "source": "paperclip",
               "numbering": f"aligned to {structure_path.name} (offset {best_off:+d} from literature)",
               "hotspot_residues": confirmed}
    (run_dir / "hotspots.json").write_text(json.dumps(wrapper, indent=2))
    (run_dir / "hotspots.txt").write_text(
        f"{name} ({acc}) hot spots — derived from full-text literature via Paperclip.\n"
        f"Numbering aligned to {structure_path.name} (literature offset {best_off:+d}).\n\n"
        + "\n".join(f"  {h['residue']}{h['position']} (chain A; lit {h['lit_position']})"
                    for h in confirmed) + "\n")
    yield Event("stage1", "ok",
                f"{len(confirmed)} structure-confirmed hotspot(s) from Paperclip "
                f"(offset {best_off:+d})", {"hotspots": confirmed[:20]})


# --------------------------------------------------------------------------- Stage 2 (Complexa, live)
def _ensure_pdb(structure_path: Path, run_dir: Path) -> Path:
    """Complexa consumes a PDB target. Convert a .cif to run_dir/target.pdb if needed."""
    structure_path = Path(structure_path)
    if structure_path.suffix.lower() == ".pdb":
        return structure_path
    import gemmi
    st = gemmi.read_structure(str(structure_path))
    st.setup_entities()
    out = run_dir / "target.pdb"
    out.write_text(st.make_pdb_string())
    return out


def _target_input_segments(structure_path: Path, chain_default: str = "A") -> str:
    """Per-chain contiguous residue segments in Complexa 'A1-115, B5-90' form."""
    try:
        idx = _structure_residue_index(Path(structure_path))
    except Exception:  # noqa: BLE001
        idx = {}
    by_chain: dict[str, list[int]] = {}
    for (ch, pos) in idx:
        by_chain.setdefault(ch, []).append(pos)
    segs: list[str] = []
    for ch, positions in sorted(by_chain.items()):
        s = sorted(set(positions))
        if not s:
            continue
        start = prev = s[0]
        for r in s[1:]:
            if r == prev + 1:
                prev = r
            else:
                segs.append(f"{ch}{start}-{prev}")
                start = prev = r
        segs.append(f"{ch}{start}-{prev}")
    return ", ".join(segs)


def _prune_hotspots(hotspots: list[dict], structure_path: Path,
                    max_residues: int = HOTSPOT_MAX_RESIDUES,
                    max_dist: float = HOTSPOT_MAX_SPREAD_A) -> tuple[list[dict], list[dict], list[str]]:
    """Enforce epitope sanity (bindclaw convention): a binder grips ONE local patch.

    1. **Compactness** — drop hotspots whose Cβ (Cα fallback) is > ``max_dist`` Å from
       the densest hotspot cluster's centroid (removes distal outliers on other
       domains, e.g. CD45 A1169 sitting ~270 residues from the A821-A897 cluster).
    2. **Count cap** — keep at most ``max_residues`` (the ones closest to the centroid).

    Returns (kept, dropped, messages). Reads coords from ``structure_path``; if they
    can't be read, or there are <=1 hotspots, returns the input unchanged (fail open).
    Hotspots whose residue isn't found in the structure are kept (not penalised)."""
    import math
    hs = list(hotspots or [])
    if len(hs) <= 1:
        return hs, [], []
    try:
        import gemmi
        st = gemmi.read_structure(str(structure_path))
        st.setup_entities()
        model = st[0]
    except Exception:  # noqa: BLE001 — never let a coord read break the run
        return hs, [], []

    def _coord(h):
        ch, pos = str(h.get("chain", "A")), int(h["position"])
        for chain in model:
            if chain.name != ch:
                continue
            for res in chain:
                if res.seqid.num == pos:
                    a = res.find_atom("CB", "*") or res.find_atom("CA", "*")
                    return (a.pos.x, a.pos.y, a.pos.z) if a else None
        return None

    coords = []
    for h in hs:
        try:
            coords.append(_coord(h))
        except (KeyError, TypeError, ValueError):
            coords.append(None)
    idx = [i for i, c in enumerate(coords) if c is not None]
    if len(idx) <= 1:
        return hs, [], []

    def d(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    # densest anchor → cluster centroid
    anchor = max(idx, key=lambda i: sum(1 for j in idx if d(coords[i], coords[j]) <= max_dist))
    cluster = [j for j in idx if d(coords[anchor], coords[j]) <= max_dist]
    cx = tuple(sum(coords[j][k] for j in cluster) / len(cluster) for k in range(3))
    within = sorted((j for j in idx if d(coords[j], cx) <= max_dist),
                    key=lambda j: d(coords[j], cx))
    capped = within[:max_residues]
    keep = set(capped) | {i for i in range(len(hs)) if coords[i] is None}  # fail-open on no-coord
    kept = [hs[i] for i in range(len(hs)) if i in keep]
    dropped = [hs[i] for i in range(len(hs)) if i not in keep]
    msgs: list[str] = []
    if dropped:
        dd = sorted({f"{x.get('chain', 'A')}{x.get('position')}" for x in dropped})
        msgs.append(
            f"hotspot sanity: kept {len(kept)}, dropped {len(dropped)} residue(s) outside the "
            f"epitope (> {max_dist:.0f} Å from the cluster centroid, or beyond the "
            f"{max_residues}-residue cap): {dd} — a binder targets one local patch")
    return kept, dropped, msgs


def _crop_target_to_epitope(structure_path: Path, hotspots: list[dict], run_dir: Path,
                            max_residues: int | None = None) -> tuple[Path, list[str]]:
    """Enforce the target-size budget so (target + binder) <= MAX_COMPLEX_RESIDUES.
    ``max_residues`` defaults to ``_max_target_residues()`` (= 500 - longest binder
    = 345). If the target is within budget, return it unchanged with no messages.
    Otherwise crop to a contiguous window centered on the epitope (hotspot residues),
    preserving ORIGINAL residue numbering so hotspot ids and downstream
    (Boltz2/OpenFold3) numbering stay valid, write it to ``run_dir/target_cropped.pdb``,
    and return that path plus human-readable messages describing the crop.

    Chains with no hotspots are dropped when cropping. With no hotspots at all there
    is no epitope to center on, so the target is truncated to the first
    ``max_residues`` residues and a warning is emitted (an unconditioned design on a
    truncated target is rarely what you want — supply hotspots)."""
    import gemmi
    from collections import defaultdict
    if max_residues is None:
        max_residues = _max_target_residues()
    st = gemmi.read_structure(str(structure_path))
    st.setup_entities()
    if len(st) == 0:
        return structure_path, []
    model = st[0]
    total = sum(len(ch) for ch in model)
    if total <= max_residues:
        return structure_path, []

    hot_by_chain: dict[str, list[int]] = defaultdict(list)
    for h in hotspots or []:
        try:
            hot_by_chain[str(h.get("chain", "A"))].append(int(h["position"]))
        except (KeyError, TypeError, ValueError):
            continue

    new_st = gemmi.Structure()
    new_st.cell = st.cell
    new_st.spacegroup_hm = st.spacegroup_hm
    new_model = gemmi.Model("1")
    half = max_residues // 2
    dropped_hot: list[int] = []
    kept_windows: list[str] = []
    for chain in model:
        new_chain = gemmi.Chain(chain.name)
        if hot_by_chain:
            if chain.name not in hot_by_chain:
                continue  # no epitope on this chain — drop it
            hs = sorted(hot_by_chain[chain.name])
            center = (hs[0] + hs[-1]) // 2
            lo, hi = center - half, center + half
            for res in chain:
                if lo <= res.seqid.num <= hi:
                    new_chain.add_residue(res)
            dropped_hot += [p for p in hs if not (lo <= p <= hi)]
        else:
            for res in chain:  # no hotspots: keep the first max_residues, in order
                if len(new_chain) >= max_residues:
                    break
                new_chain.add_residue(res)
        if len(new_chain):
            new_model.add_chain(new_chain)
            nums = [r.seqid.num for r in new_chain]
            kept_windows.append(f"{new_chain.name}{min(nums)}-{max(nums)}")
    new_st.add_model(new_model)
    new_st.setup_entities()
    out = run_dir / "target_cropped.pdb"
    out.write_text(new_st.make_pdb_string())

    kept_n = sum(len(ch) for ch in new_model)
    budget = f"{max_residues}-residue target cap (binder+target <= {MAX_COMPLEX_RESIDUES})"
    msgs: list[str] = []
    if hot_by_chain:
        msgs.append(
            f"target has {total} residues (> {budget}); cropped to the "
            f"epitope window {', '.join(kept_windows)} ({kept_n} residues, original numbering kept)")
        if dropped_hot:
            msgs.append(
                f"WARNING: {len(dropped_hot)} hotspot(s) lay outside the {max_residues}-residue "
                f"window and were dropped: {sorted(set(dropped_hot))} — they are too far from the "
                "main epitope to share one binder; design a separate binder for them if needed")
    else:
        msgs.append(
            f"WARNING: target has {total} residues (> {budget}) and NO "
            f"hotspots to center on; truncated to the first {kept_n} residues. Provide hotspots so "
            "the crop covers the real epitope")
    return out, msgs


def register_complexa_target(task_name: str, structure_path: Path, hotspots: list[dict],
                             binder_length: tuple[int, int] = BINDER_LENGTH,
                             chain: str = "A") -> dict:
    """Append/overwrite a Complexa targets_dict.yaml entry in the OPEN checkout
    ($COMPLEXA_REPO). gemmi-based so it handles .cif and .pdb; flock-guarded with an
    atomic temp-file rename so parallel runs can't shred the YAML. Empty `hotspots`
    => unconditioned design. Returns the written entry.

    (Equivalent to `complexa target add <task_name> --pdb <pdb> --chain <c>
    --span <lo-hi> --hotspots ... --binder-length <lo-hi>`; we write the YAML
    directly so a custom target PDB can be staged into the repo's asset tree.)"""
    import fcntl
    import os
    import shutil
    import tempfile
    import yaml
    targets_dict = _targets_dict()
    targets_dict.parent.mkdir(parents=True, exist_ok=True)
    lock_path = targets_dict.with_suffix(targets_dict.suffix + ".lock")
    # Stage the target PDB inside the repo's asset tree so the CLI/container resolves
    # it regardless of cwd (no host/container path remapping needed on the open CLI).
    tgt_dir = _complexa_repo() / "assets" / "target_data" / "binder_pipeline"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    tgt_pdb = tgt_dir / f"{task_name}.pdb"  # name by task so targets never collide
    if Path(structure_path).resolve() != tgt_pdb.resolve():
        shutil.copy2(structure_path, tgt_pdb)
    entry = {
        "target_path": str(tgt_pdb),
        "target_input": _target_input_segments(structure_path, chain) or f"{chain}1-500",
        "hotspot_residues": [f"{h.get('chain', 'A')}{h.get('position')}" for h in (hotspots or [])],
        "binder_length": [int(binder_length[0]), int(binder_length[1])],
        "pdb_id": None,
        "source": "binder-pipeline-runtime",
        "target_filename": task_name,
    }
    with open(lock_path, "a+") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        try:
            data = (yaml.safe_load(targets_dict.read_text()) or {}) if targets_dict.exists() else {}
            data.setdefault("target_dict_cfg", {})[task_name] = entry
            fd, tmp = tempfile.mkstemp(dir=str(targets_dict.parent), prefix=".td.", suffix=".yaml.tmp")
            with os.fdopen(fd, "w") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            os.replace(tmp, targets_dict)
        finally:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
    return entry


def submit_complexa(task_name: str, run_name: str, n_devices: int = 1,
                    algorithm: str = "best-of-n", seed: int = 0,
                    num_samples: int | None = None) -> Iterator[Event]:
    """Run the FULL Complexa binder pipeline via the open `complexa design` CLI.

    Runs generate→filter→evaluate→analyze in the user's checkout ($COMPLEXA_REPO),
    so the co-designed `self` sequence + AF2 reward metrics (self_complex_i_pTM /
    pLDDT) land in the results CSVs. `n_devices` maps to gen/eval GPU parallelism
    (one GPU per job). Synchronous — the CLI blocks until the run completes."""
    repo = _complexa_repo()
    cmd = [COMPLEXA_BIN, "design", COMPLEXA_CONFIG,
           f"++run_name={run_name}",
           f"++generation.task_name={task_name}",
           f"++generation.search.algorithm={algorithm}",
           f"++seed={seed}",
           f"++gen_njobs={n_devices}", f"++eval_njobs={n_devices}"]
    if num_samples is not None:
        cmd.append(f"++generation.dataloader.dataset.nres.nsamples={num_samples}")
    yield Event("stage2", "start",
                f"running `complexa design` for {task_name} "
                f"(algorithm={algorithm}, seed={seed}, gen/eval njobs={n_devices}); "
                "AF2 reward gate selects which designs go to Boltz2")
    yield Event("stage2", "info", "cmd: " + " ".join(cmd) + f"  (cwd={repo})")
    p = _run(cmd, cwd=repo, timeout=int(os.environ.get("COMPLEXA_TIMEOUT_S", "21600")))
    if p.returncode != 0:
        raise RuntimeError(
            "`complexa design` failed (rc="
            f"{p.returncode}): {(p.stderr or p.stdout)[-600:]}")
    yield Event("stage2", "ok", f"complexa design finished for run '{run_name}'")


_AA20 = set("ACDEFGHIKLMNPQRSTVWY")


def _looks_like_sequence(v: str) -> bool:
    """A string that IS an amino-acid sequence: ≥20 standard residues, ≥2 types.
    (Quality/complexity is judged separately by _max_aa_fraction.)"""
    v = (v or "").strip().upper()
    return len(v) >= 20 and set(v) <= _AA20 and len(set(v)) >= 2


MAX_AA_FRACTION = 0.20   # reject a binder if any single amino acid exceeds this fraction


def _max_aa_fraction(v: str) -> float:
    """Largest single-amino-acid fraction in the sequence (0..1). Complexa's `self`
    sequences are often degenerate poly-X (e.g. poly-Lys/Thr) that cannot fold — a
    high value flags those so we DON'T waste Boltz2 validation on them."""
    from collections import Counter
    s = (v or "").strip().upper()
    if not s:
        return 1.0
    return max(Counter(s).values()) / len(s)


def _find_inference_dir(task_name: str, run_name: str) -> Path | None:
    """Most-recently-modified Complexa inference dir for this run/task."""
    root = _complexa_repo() / "inference"
    if not root.exists():
        return None
    cands = sorted([d for d in root.iterdir()
                    if d.is_dir() and (run_name in d.name or task_name in d.name)],
                   key=lambda d: d.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _find_combined_csvs(task_name: str, run_name: str) -> list[Path]:
    """The clean per-design binder-results CSVs for THIS run (one per device).

    Complexa's evaluate writes many CSVs per run; only ``binder_results_*.csv``
    carries per-design sequences (``self_sequence``) + interface scores
    (``self_complex_i_pTM``). The RAW/transposed/aggregated/timing/all_successes
    files have incompatible schemas or no sequences — globbing ``*.csv`` pulls
    those (and other runs of the same target), which breaks column detection.
    So: match only ``binder_results_*.csv`` and scope strictly to ``run_name``;
    only widen to ``task_name`` if the strict match finds nothing."""
    def _scan(match: str) -> list[Path]:
        hits: list[Path] = []
        repo = _complexa_repo()
        for root in (repo / "evaluation_results", repo / "inference", repo / "results"):
            if root.exists():
                hits += [p for p in root.rglob("binder_results_*.csv")
                         if match in str(p) and "transposed" not in p.name]
        return hits
    cands = _scan(run_name) or _scan(task_name)
    # dedup, newest first
    seen, out = set(), []
    for p in sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def extract_complexa_designs(run_dir: Path, task_name: str, run_name: str,
                             n_top: int = 50) -> Iterator[Event]:
    """Pull REAL (inverse-folded) binder sequences + refolded PDBs from the
    Complexa results CSV into design/ + sequences/binders_complexa_native.fasta.

    Schema-tolerant: the sequence column is detected by CONTENT (values that are
    20-letter amino-acid strings), the score column by name. Fails LOUD if no
    usable (non-poly-Gly) sequence is found, rather than feeding a placeholder
    into validation. NOTE: the exact Complexa results-CSV schema is confirmed on
    the first real GPU run; this parser is content-based to tolerate it."""
    import csv
    yield Event("stage2", "start",
                f"extracting designs (real sequences) from Complexa results, keeping top {n_top}")
    csv_paths = _find_combined_csvs(task_name, run_name)
    if not csv_paths:
        yield Event("stage2", "error",
                    "Complexa finished but no per-design results CSV was found under "
                    f"{_complexa_repo()}/(evaluation_results|inference|results) for run '{run_name}'. "
                    "The pipeline may have stopped before evaluate/analyze — check the Slurm log.")
        return
    rows: list[dict] = []
    for cp in csv_paths:
        try:
            with open(cp, newline="") as fh:
                rows += list(csv.DictReader(fh))
        except OSError:
            continue
    csv_path = csv_paths[0]  # representative (newest) for column detection + provenance
    if not rows:
        yield Event("stage2", "error", f"results CSVs ({len(csv_paths)}) were all empty")
        return
    yield Event("stage2", "info",
                f"aggregated {len(rows)} design rows from {len(csv_paths)} results CSV(s)")
    cols = list(rows[0].keys())
    # Prefer the co-designed `self` sequence column explicitly (we generate with
    # sequence_types=[self]); NEVER pick `target_sequence` (that's the receptor,
    # not the binder). Only fall back to content detection if no self column.
    seq_col = next((c for c in cols if c.lower() in ("self_sequence", "self_seq", "self")), None)
    if seq_col is None:
        seq_col = next((c for c in cols if "self" in c.lower() and "seq" in c.lower()), None)
    if seq_col is None:
        seq_col = next((c for c in cols
                        if "target" not in c.lower()
                        and any(_looks_like_sequence(r.get(c, "")) for r in rows[:10])), None)
    if seq_col is None:
        yield Event("stage2", "error",
                    f"results CSV {csv_path.name} has no amino-acid sequence column "
                    f"(columns: {cols}).")
        return

    def _find_col(subs: list[str]) -> str | None:
        return next((c for c in cols if any(s in c.lower() for s in subs)), None)

    # AF2-Multimer metrics from the beam-search reward model (0-1 scaled):
    # self_complex_i_pTM (interface pTM) and self_complex_pLDDT. Prefer the
    # `self_complex_` columns; fall back to any i_ptm/plddt column.
    iptm_col = next((c for c in cols if c.lower() == "self_complex_i_ptm"), None) \
        or _find_col(["i_ptm", "iptm"])
    plddt_col = next((c for c in cols if c.lower() == "self_complex_plddt"), None) \
        or _find_col(["plddt"])
    score_col = iptm_col or plddt_col          # ranking key (AF2 i_pTM)
    pdb_col = _find_col(["pdb_path", "sample_path", "pdb_filename", "pdb", "structure"])

    def _num(r: dict, col: str | None) -> float:
        try:
            return float(r.get(col, "") or 0) if col else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _score(r: dict) -> float:
        return _num(r, score_col)

    usable = [r for r in rows if _looks_like_sequence(r.get(seq_col, ""))]
    if not usable:
        yield Event("stage2", "error",
                    f"{csv_path.name} had {len(rows)} rows but none carry a usable amino-acid "
                    f"sequence in column '{seq_col}' — the evaluate step produced no sequences.")
        return
    # Complexity filter: DO NOT validate degenerate poly-X sequences (Complexa `self`
    # is often poly-Lys/Thr/Ile that cannot fold). Drop any design where a single
    # amino acid exceeds MAX_AA_FRACTION (20%) — they only waste Boltz2 validation.
    n_before = len(usable)
    diverse = [r for r in usable if _max_aa_fraction(r.get(seq_col, "")) <= MAX_AA_FRACTION]
    n_dropped = n_before - len(diverse)
    if n_dropped:
        yield Event("stage2", "info",
                    f"complexity filter: dropped {n_dropped}/{n_before} low-complexity design(s) "
                    f"(a single amino acid > {int(MAX_AA_FRACTION * 100)}%) — not validating those")
    usable = diverse
    if not usable:
        yield Event("stage2", "error",
                    f"all {n_before} designs are low-complexity (single AA > {int(MAX_AA_FRACTION * 100)}%) "
                    "— nothing worth validating. Switch to MPNN sequences (cx_beam_search_mpnn) for "
                    "foldable designs, then re-run.")
        return
    # AF2 QUALITY GATE (primary selector). Forward to Boltz2 only the designs the
    # generator's own AF2-Multimer is already confident in: self_complex_i_pTM AND
    # self_complex_pLDDT both > 0.70. We validate ALL designs that pass (not a fixed
    # top-N); n_top is only a safety cap. This avoids Boltz2-re-predicting collapsed
    # / low-confidence backbones (which scored i_pTM~0.08, pLDDT~0.56).
    n_pre_gate = len(usable)
    if iptm_col or plddt_col:
        passed = [r for r in usable
                  if (not iptm_col or _num(r, iptm_col) > AF2_IPTM_MIN)
                  and (not plddt_col or _num(r, plddt_col) > AF2_PLDDT_MIN)]
        _gate_parts = []
        if iptm_col:
            _gate_parts.append(f"AF2 i_pTM>{AF2_IPTM_MIN:.2f}")
        if plddt_col:
            _gate_parts.append(f"pLDDT>{AF2_PLDDT_MIN:.2f}")
        gate_desc = " & ".join(_gate_parts)
        yield Event("stage2", "info",
                    f"AF2 gate ({gate_desc}): {len(passed)}/{n_pre_gate} design(s) pass "
                    "→ Boltz2-validating all of them")
        if not passed:
            best_iptm = max((_num(r, iptm_col) for r in usable), default=0.0) if iptm_col else None
            best_plddt = max((_num(r, plddt_col) for r in usable), default=0.0) if plddt_col else None
            yield Event("stage2", "error",
                        f"NO design cleared the AF2 gate ({gate_desc}) — best AF2 "
                        f"i_pTM={best_iptm}, pLDDT={best_plddt}. The generator is not confident in "
                        "any binder, so nothing is worth an independent Boltz2 re-prediction. "
                        "Likely causes: collapsed/low-quality backbones, wrong hotspots, or use MPNN "
                        "sequences (cx_beam_search_mpnn). Not submitting Boltz2.")
            return
        usable = passed
    else:
        yield Event("stage2", "info",
                    "no AF2 i_pTM/pLDDT column found in results CSV — skipping AF2 gate, "
                    f"falling back to top-{max(1, n_top)} by available score")
    usable.sort(key=_score, reverse=True)
    # No per-target cap: validate EVERY AF2-passing design. n_top is only the
    # runaway ceiling (MAX_VALIDATE_CEILING) unless the user set an explicit cap.
    if len(usable) > max(1, n_top):
        yield Event("stage2", "info",
                    f"AF2-passing pool ({len(usable)}) exceeds the runaway ceiling {max(1, n_top)}; "
                    f"keeping the top {max(1, n_top)} by AF2 i_pTM for Boltz2")
        usable = usable[:max(1, n_top)]
    else:
        yield Event("stage2", "info",
                    f"validating ALL {len(usable)} AF2-passing design(s) with Boltz2 (no cap)")
    design = run_dir / "design"
    seqs = run_dir / "sequences"
    design.mkdir(parents=True, exist_ok=True)
    seqs.mkdir(parents=True, exist_ok=True)
    # Save the raw Complexa results into the run's output dir (co-located).
    import shutil
    cdir = run_dir / "complexa"
    cdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csv_path, cdir / csv_path.name)
    inf = _find_inference_dir(task_name, run_name)
    if inf is not None and inf.exists():
        (cdir / "backbones").mkdir(exist_ok=True)
        for bb in inf.rglob("*.pdb"):
            try:
                shutil.copy2(bb, cdir / "backbones" / bb.name)
            except OSError:
                pass
    fasta = []
    for i, r in enumerate(usable, 1):
        name = f"rank{i:02d}_{task_name}"
        fasta.append(f">{name}\n{r[seq_col].strip().upper()}")
        if pdb_col and r.get(pdb_col):
            raw = Path(r[pdb_col])
            # Complexa writes pdb_path RELATIVE TO THE REPO ROOT ($COMPLEXA_REPO),
            # e.g. "./evaluation_results/.../job_.../*.pdb" — NOT relative to the CSV
            # file. Try the repo root first, then csv_path.parent.
            if raw.is_absolute():
                src = raw
            else:
                src = _complexa_repo() / raw
                if not src.exists():
                    src = csv_path.parent / raw
            if src.exists():
                (design / f"{name}.pdb").write_text(src.read_text())
    (seqs / "binders_complexa_native.fasta").write_text("\n".join(fasta) + "\n")
    yield Event("stage2", "ok",
                f"extracted {len(usable)} binder sequence(s) → sequences/binders_complexa_native.fasta "
                f"(source {csv_path.name}, seq col '{seq_col}'"
                + (f", ranked by '{score_col}'" if score_col else "") + ")",
                {"n_designs": len(usable)})


def fetch_target_msa(run_dir: Path) -> Iterator[Event]:
    yield Event("stage3", "start", "building target MSA (ColabFold)")
    out = run_dir / "target.a3m"
    p = _run([sys.executable, FETCH_MSA, "--seq-from-pdb", run_dir / "target.pdb", "-o", out], timeout=1200)
    if p.returncode != 0:
        raise RuntimeError(f"MSA fetch failed: {p.stderr[-400:]}")
    yield Event("stage3", "ok", f"target MSA written ({out.name})")


def validation_handoff(run_dir: Path, conditioning: str) -> Iterator[Event]:
    """Stage-3 is an INDEPENDENT refold via the Boltz2/OpenFold3 NIM (a different
    model family than Complexa's AF2/RF3 reward+evaluate). Generation is automated
    above; the NIM calls are driven by the agent (boltz2-nim / openfold3-nim skill).
    This emits the exact handoff so the agent knows what to produce, after which
    `score()` / `validate_binders.py` reads it and applies the gate.

    For each binder in sequences/binders_complexa_native.fasta, the agent runs:
      * HOLO: binder (single-seq) + target (MSA default / template optional),
              write_full_pae=true  → validation/raw/<name>.json (+ cif)
      * APO:  binder alone         → validation/apo/<name>.apo.cif
    """
    binders = run_dir / "sequences" / "binders_complexa_native.fasta"
    yield Event("stage3", "start",
                f"independent validation handoff ({conditioning}) — drive Boltz2/OF3 via the NIM skill")
    yield Event("stage3", "info",
                f"binders: {binders}; target: {run_dir / 'target.pdb'}; "
                f"target conditioning: {conditioning} "
                f"({'target.a3m' if conditioning == 'msa' else 'target.cif template'}). "
                "Write holo Boltz2 responses to validation/raw/*.json and apo cifs to "
                "validation/apo/*.apo.cif, then run validate_binders.py (or score()).")


# --------------------------------------------------------------------------- scoring
def score(run_dir: Path, hotspots: Path | None, apo_dir: Path | None = None) -> Iterator[Event]:
    yield Event("gate", "start", "scoring designs against the validation gate")
    cmd = [sys.executable, VALIDATE_BINDERS, "--run-dir", run_dir, "--no-apo"]
    if hotspots and Path(hotspots).exists():
        cmd += ["--hotspots", hotspots]
    if apo_dir:
        cmd += ["--apo-dir", apo_dir]
    p = _run(cmd, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"scoring failed: {p.stderr[-500:]}")
    ranked_path = run_dir / "ranked_binders.json"
    ranked = json.loads(ranked_path.read_text()) if ranked_path.exists() else []
    n_pass = sum(1 for r in ranked if r.get("pass"))
    yield Event("gate", "ok", f"scored {len(ranked)} designs; {n_pass} pass the gate",
                {"ranked": ranked, "n_pass": n_pass, "ranked_path": str(ranked_path)})


# --------------------------------------------------------------------------- top-level
def run(mode: str = "score_existing", *, run_dir: str | None = None,
        target: dict | None = None, target_text: str | None = None,
        target_file: str | None = None, target_key: str | None = None,
        conditioning: str = "msa", n_validated: int = 0,
        n_devices: int = N_DEVICES_DEFAULT,
        hotspots: str | None = None, apo_dir: str | None = None) -> Iterator[Event]:
    """Stream the pipeline. See module docstring for modes.

    ``n_validated <= 0`` auto-couples to ``n_devices x VALIDATED_PER_DEVICE`` (the
    number of AF2-ranked designs forwarded to Boltz2): 16 GPUs -> 64 validated."""
    n_validated = validation_count(n_devices, n_validated)
    try:
        if mode == "score_existing":
            if not run_dir:
                raise ValueError("score_existing needs run_dir")
            rd = Path(run_dir).expanduser()
            if not rd.is_absolute() and not rd.exists():
                rd = OUTPUTS / run_dir
            yield Event("init", "ok", f"scoring existing run {rd.name}")
            hs = hotspots or (rd / "hotspots.json" if (rd / "hotspots.json").exists() else None)
            ad = apo_dir or (rd / "validation" / "apo" if (rd / "validation" / "apo").exists() else None)
            yield from score(rd, hs, ad)
            return

        if mode == "full":
            # Resolve the target from: an uploaded file, free text (name/UniProt/
            # PDB), or an explicit spec dict.
            if target_file:
                ext = Path(target_file).suffix.lower()
                spec = {"cif_path": target_file} if ext == ".cif" else {"pdb_path": target_file}
                label = Path(target_file).stem
            elif target_text:
                spec = resolve_target_spec(target_text)
                label = spec.get("uniprot") or spec.get("pdb") or "target"
            elif target:
                spec = target
                label = target.get("uniprot") or target.get("pdb") or "target"
            else:
                raise ValueError("full mode needs target_text, target_file, or target spec")
            rd = OUTPUTS / f"{label}_app"
            yield Event("init", "start",
                        f"full run → {rd.name} (N={n_validated}, {conditioning})")
            if spec.get("resolved_from"):
                yield Event("init", "info", f"resolved target: {spec['resolved_from']}")
            yield from resolve_target(spec, rd)
            # Resolve final hotspots: an explicitly provided file (e.g. the
            # Paperclip fallback output) wins over the UniProt-derived set. Either
            # way, align to the resolved structure so Stage 2 never conditions on a
            # residue absent from the coordinates (the 'ordering' guarantee).
            structure = rd / "target.cif" if (rd / "target.cif").exists() else rd / "target.pdb"
            if hotspots and Path(hotspots).exists():
                yield Event("stage1", "info", f"using provided hotspots file: {Path(hotspots).name}")
                hsrc = json.loads(Path(hotspots).read_text())
            elif (rd / "hotspots.json").exists():
                hsrc = json.loads((rd / "hotspots.json").read_text())
            else:
                hsrc = []
            hs_in = hsrc.get("hotspot_residues", []) if isinstance(hsrc, dict) else hsrc
            # UniProt gave nothing → run the Paperclip literature fallback automatically.
            if not hs_in and structure.exists() and spec.get("uniprot"):
                yield from paperclip_hotspots(spec["uniprot"], structure, rd)
                if (rd / "hotspots.json").exists():
                    hj = json.loads((rd / "hotspots.json").read_text())
                    hs_in = hj.get("hotspot_residues", []) if isinstance(hj, dict) else hj
            if hs_in and structure.exists():
                kept, dropped = align_hotspots_to_structure(hs_in, structure)
                if dropped:
                    yield Event("stage1", "info",
                                f"aligned hotspots to {structure.name}: dropped {len(dropped)} "
                                "off-structure residue(s) — "
                                + "; ".join(d.get("drop_reason", "") for d in dropped[:6]))
                wrapper = hsrc if isinstance(hsrc, dict) else {}
                wrapper["hotspot_residues"] = kept
                wrapper["numbering"] = f"aligned to {structure.name} coordinates"
                (rd / "hotspots.json").write_text(json.dumps(wrapper, indent=2))
                yield Event("stage1", "ok", f"{len(kept)} structure-aligned hotspot(s) ready",
                            {"hotspots": kept[:20]})
            elif not hs_in:
                yield Event("stage1", "info",
                            "no hotspots (UniProt empty and none provided) — run the Paperclip "
                            "fallback (prompts/hotspot_paperclip.md) and re-run with --hotspots, "
                            "or proceed UNCONDITIONED.")
            # Stage 2 — register the target + run the FULL Complexa pipeline, then
            # extract real (inverse-folded) binder sequences. A pre-staged FASTA or
            # an explicit target_key short-circuits parts of this.
            binders = rd / "sequences" / "binders_complexa_native.fasta"
            if binders.exists():
                yield Event("stage2", "info", f"reusing pre-staged {binders}")
            else:
                pdb_for_complexa = _ensure_pdb(structure, rd)
                task = target_key or ("app_" + re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_"))
                final_hs: list = []
                if (rd / "hotspots.json").exists():
                    hj = json.loads((rd / "hotspots.json").read_text())
                    final_hs = hj.get("hotspot_residues", hj) if isinstance(hj, dict) else hj
                # Hotspot sanity: a binder targets ONE compact epitope. Drop distal
                # outliers (> HOTSPOT_MAX_SPREAD_A from the cluster) and cap at
                # HOTSPOT_MAX_RESIDUES, so generation + the crop center on a real patch.
                if final_hs and not target_key:
                    final_hs, _dropped_hs, _hs_msgs = _prune_hotspots(final_hs, pdb_for_complexa)
                    for m in _hs_msgs:
                        yield Event("stage1", "info", m)
                    # A binder needs >=2 hotspots to define an epitope; 1 is too weak.
                    if 0 < len(final_hs) < HOTSPOT_MIN_RESIDUES:
                        yield Event("stage1", "info",
                                    f"WARNING: only {len(final_hs)} hotspot residue after sanity "
                                    f"pruning (need >= {HOTSPOT_MIN_RESIDUES}). A single residue is "
                                    "too weak to define an epitope — add hotspots (Paperclip/"
                                    "literature) or this design is effectively unconditioned.")
                already_registered = False
                _td_path = _targets_dict()
                if _td_path.exists():
                    try:
                        import yaml
                        td = yaml.safe_load(_td_path.read_text()) or {}
                        already_registered = task in td.get("target_dict_cfg", {})
                    except Exception:  # noqa: BLE001
                        pass
                if target_key:
                    # User-managed, pre-registered target — trust it as-is.
                    yield Event("stage2", "info",
                                f"target '{task}' supplied explicitly — reusing existing entry "
                                "(not overwriting)")
                else:
                    # Enforce the target-size cap; crop oversized targets to the
                    # epitope so Complexa's O(n^2) pair features don't OOM.
                    pdb_for_complexa, crop_msgs = _crop_target_to_epitope(
                        pdb_for_complexa, final_hs, rd)
                    for m in crop_msgs:
                        yield Event("stage1", "info", m)
                    # A full run just freshly resolved the structure + hotspots, so
                    # ALWAYS (re)register with the current result rather than reusing a
                    # possibly-stale entry (e.g. an earlier unconditioned 0-hotspot run).
                    if already_registered:
                        yield Event("stage2", "info",
                                    f"refreshing registration for '{task}' with current structure "
                                    f"+ {len(final_hs)} hotspot(s)")
                    entry = register_complexa_target(task, pdb_for_complexa, final_hs)
                    yield Event("stage2", "info",
                                f"registered Complexa target '{task}' "
                                f"(target_input={entry['target_input']}, "
                                f"{len(entry['hotspot_residues'])} hotspot(s), "
                                f"binder_length={entry['binder_length']})")
                run_name = f"{task}_{time.strftime('%Y%m%d_%H%M%S')}"
                yield from submit_complexa(task, run_name, n_devices=n_devices)
                # Apply the AF2-reward gate + complexity filter; forward passers to
                # independent Boltz2 validation (n_validated caps the pool).
                yield from extract_complexa_designs(rd, task, run_name,
                                                    n_top=max(1, int(n_validated)))
                if not binders.exists():
                    return  # extract_complexa_designs already emitted a specific error
            if conditioning == "msa":
                yield from fetch_target_msa(rd)
            # Stage 3 is an independent NIM refold driven by the agent; emit the handoff.
            yield from validation_handoff(rd, conditioning)
            # If holo/apo refolds already exist (agent produced them, or a prior run),
            # score immediately; otherwise stop after the handoff.
            if (rd / "validation" / "raw").is_dir():
                apo_dir = (rd / "validation" / "apo") if (rd / "validation" / "apo").exists() else None
                yield from score(rd, rd / "hotspots.json" if (rd / "hotspots.json").exists() else None,
                                 apo_dir)
            return

        raise ValueError(f"unknown mode {mode}")
    except Exception as e:  # noqa: BLE001
        yield Event("error", "error", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    # tiny CLI for testing without the UI: score an existing run
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="score_existing")
    ap.add_argument("--run-dir")
    ap.add_argument("--apo-dir")
    a = ap.parse_args()
    for ev in run(mode=a.mode, run_dir=a.run_dir, apo_dir=a.apo_dir):
        print(ev.line())
        if ev.stage == "gate" and ev.status == "ok":
            for r in ev.data.get("ranked", [])[:10]:
                print(f"    #{r.get('rank')} {r.get('name','')[:46]:46} pass={r.get('pass')} "
                      f"ipSAEmin={r.get('ipsae_min')} rmsd={r.get('binder_rmsd')}")
