#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Pre-flight design planner / validator — run BEFORE generation to see, per target,
exactly what would be conditioned on and whether it satisfies the design rules.
No GPU, no Slurm: just fetch the structure + UniProt, choose hotspots, re-align
them to the (possibly cropped) structure, and check every constraint.

For each target it reports and validates:
  * conditioned target LENGTH (after extracellular restriction + epitope crop)
  * hotspot POSITIONS, re-aligned to the structure (identity verified; numbering
    preserved through any truncation)
  * size budget:    target + longest binder  <=  MAX_COMPLEX_RESIDUES (500)
  * compactness:    hotspot pairwise diameter <=  30 Å  (else pick a compact subset)
  * count:          1 <= n_hotspots <= 15 (prefer at least 2)

Usage:
  python3 scripts/preflight_design.py IL1R1 HER2 PIN1 TNFL9 EFNB1 CEACAM1 AHSP
  python3 scripts/preflight_design.py P04626                 # by accession
  python3 scripts/preflight_design.py 1BRS --chain A --partner-chain D --out prepared
  python3 scripts/preflight_design.py target.pdb --chain A    # local structure
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # Stage-1 modules live alongside this script
import pipeline as P            # noqa: E402
import hotspot_strategy as HS   # noqa: E402


def plan(target: str, binder_max: int = None, *, chain: str | None = None,
         partner_chain: str | None = None, out_dir: str | Path | None = None,
         hotspots: str | Path | None = None) -> dict:
    """Resolve evidence, then run generation's shared preparation on real geometry.

    ``out_dir`` preserves target_prepared.pdb, hotspots.json and preflight.json for
    the generation handoff. Without it this is a preview; a direct full run uses
    the same preparation and requires the same chain/partner selection.
    """
    binder_max = binder_max if binder_max is not None else P.BINDER_LENGTH[1]
    rep = {"target": target}
    path = Path(target)
    if path.is_file() and path.suffix.lower() in (".pdb", ".cif", ".mmcif"):
        spec = {"pdb_path" if path.suffix.lower() == ".pdb" else "cif_path": str(path),
                "resolved_from": str(path)}
    else:
        spec = P.resolve_target_spec(target)
    acc = spec.get("uniprot")
    rep["uniprot"] = acc
    rep["resolved_from"] = spec.get("resolved_from")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        hotspot_data = None
        if acc:
            P._run([sys.executable, str(P.FETCH_STRUCTURE), acc, "-o", str(td)], timeout=600)
            structure = next(iter(sorted(td.glob(f"AF-{acc}-*model*.cif"))), None)
            if structure is None:
                rep["error"] = "no AFDB model"
                return rep
            result = P._run([sys.executable, str(P.UNIPROT_TOOLS), "get", acc], timeout=300)
            entry = json.loads(result.stdout)
            entry = entry if "features" in entry else entry.get("results", [entry])[0]
            hs, segs, provenance, messages = HS.resolve_hotspots(entry)
            hotspot_data = {"hotspot_residues": hs, "accessible_segments": segs,
                            "source": provenance, "uniprot": acc}
            rep["topology"] = HS.accessibility(entry)["note"]
            rep["uniprot_messages"] = messages
        else:
            for _ in P.resolve_target(spec, td):
                pass
            structure = td / ("target.cif" if spec.get("cif_path") else "target.pdb")
            rep["pdb"] = spec.get("pdb")
        if hotspots is not None:
            hotspot_data = json.loads(Path(hotspots).read_text())
        output = Path(out_dir).expanduser().resolve() if out_dir is not None else td / "prepared"
        rep.update(P.prepare_design_target(structure, output, chain=chain,
                                          partner_chain=partner_chain,
                                          hotspot_data=hotspot_data, binder_max=binder_max))
        if not acc:
            rep["topology"] = f"PDB author chain {rep['chain']}; accessibility not annotated"
            if rep["partner_chain"] is not None:
                rep["topology"] += f"; interface partner {rep['partner_chain']}"
            rep["uniprot_messages"] = [] if rep["n_hotspots"] else [
                "No protein partner contacts found; supply an evidence-based surface patch before generation."]
        if out_dir is not None:
            (output / "preflight.json").write_text(json.dumps(rep, indent=2) + "\n")
        else:
            # Preview paths would point into a deleted temporary directory.
            rep.pop("prepared_target")
            rep.pop("hotspots_path")
    return rep


def _fmt(rep: dict) -> str:
    L = []
    head = f"━━━ {rep['target']} ({rep.get('uniprot') or rep.get('pdb') or 'local structure'}) ━━━"
    L.append(head)
    if rep.get("error"):
        L.append(f"  ERROR: {rep['error']}")
        return "\n".join(L)
    L.append(f"  full length: {rep['full_length']} aa | {rep['topology']}")
    L.append(f"  conditioned on: {rep['conditioned_length']} aa  ({rep['conditioning']})")
    L.append(f"  hotspots ({rep['source']}): raw={rep['raw_hotspots']}")
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
    if rep.get("prepared_target"):
        L.append(f"  prepared target: {rep['prepared_target']}")
        L.append(f"  hotspots: {rep['hotspots_path']}")
    return "\n".join(L)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="protein names, UniProt accessions, PDB IDs, or local PDB/mmCIF paths")
    parser.add_argument("--chain", help="target author chain (required for multichain PDB structures)")
    parser.add_argument("--partner-chain", help="one protein partner defining the interface (required when ambiguous)")
    parser.add_argument("--hotspots", help="explicit hotspot JSON, overriding automatic interface selection")
    parser.add_argument("--out", help="preserve the prepared target, hotspots and report for one target")
    args = parser.parse_args(argv)
    targets = args.targets or ["IL1R1", "HER2", "PIN1", "TNFL9", "EFNB1", "CEACAM1", "AHSP"]
    if args.out and len(targets) != 1:
        parser.error("--out requires exactly one target")
    status = 0
    for t in targets:
        try:
            report = plan(t, chain=args.chain, partner_chain=args.partner_chain,
                          hotspots=args.hotspots, out_dir=args.out)
            print(_fmt(report))
            if report.get("error") or not all(passed for passed, _ in report["checks"].values()):
                status = 1
        except Exception as e:  # noqa: BLE001
            print(f"━━━ {t} ━━━\n  EXCEPTION: {type(e).__name__}: {e}")
            status = 1
        print()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
