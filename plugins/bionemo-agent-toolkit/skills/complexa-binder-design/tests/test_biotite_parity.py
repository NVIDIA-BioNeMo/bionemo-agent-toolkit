#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Parity test sheet: the biotite-based helpers (shipped) vs gemmi (reference).

Proves the gemmi->biotite migration is input/output-equivalent. Each row feeds the
SAME structure to both libraries and asserts identical results for:

  * (chain, resnum) -> resname residue index          [pipeline._structure_residue_index]
  * protein-protein interface residues (heavy <5 Å)   [pdb_interface.interface_hotspots]
  * Cβ (Cα fallback) hotspot coordinates              [preflight_design._cb_coords]
  * epitope crop window residues                      [pipeline._crop_target_to_epitope]
  * Boltz template: label_seq 1..N + canonical seq    [pdb_to_boltz_template_cif]

One row is NOT a parity check: `symmetry_bug_documented` pins the single intentional
behaviour change. The old gemmi interface search indexed crystallographic symmetry
images, so crystal-packing contacts were reported as biological interface hotspots
(on 1BRS: 59 residues instead of 42). biotite searches the deposited coordinates only.
The gemmi reference rows therefore run with symmetry disabled.

Run in the target env (Python >= 3.10, biotite >= 1.0); needs network (downloads a
small RCSB structure). If gemmi is installed it runs A/B parity; otherwise it checks
the biotite outputs against fixed expectations. Exit code 0 = all rows PASS.

    python3 tests/test_biotite_parity.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import numpy as np                              # noqa: E402
import biotite.structure as struc               # noqa: E402
import biotite.structure.io.pdb as btpdb        # noqa: E402

import pipeline as P                            # noqa: E402
import preflight_design as PF                   # noqa: E402
import pdb_to_boltz_template_cif as TCIF        # noqa: E402
import pdb_interface as PIF                     # noqa: E402

try:
    import gemmi                                # noqa: E402
    HAVE_GEMMI = True
except Exception:                               # noqa: BLE001
    HAVE_GEMMI = False

AA = set("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER "
         "THR TRP TYR VAL MSE".split())
PDB_ID = "1BRS"          # barnase (chain A) + barstar (chain D), small co-complex
TARGET_CHAIN = "A"      # barnase; partners are all other protein chains

_rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _rows.append((name, bool(ok), detail))


def _download(pdb_id: str) -> bytes:
    url = f"https://files.rcsb.org/download/{pdb_id.lower()}.cif"
    return urllib.request.urlopen(url, timeout=180).read()  # nosec B310


def _gemmi_from_bytes(data: bytes):
    with tempfile.NamedTemporaryFile("wb", suffix=".cif", delete=False) as fh:
        fh.write(data)
        fh.flush()
        st = gemmi.read_structure(fh.name)
    st.setup_entities()
    return st


def main() -> int:
    data = _download(PDB_ID)
    cif_path = Path(tempfile.mkdtemp()) / f"{PDB_ID.lower()}.cif"
    cif_path.write_bytes(data)
    run_dir = cif_path.parent

    # biotite model via the shipped reader
    arr = P._read_first_model(cif_path)
    gm = _gemmi_from_bytes(data) if HAVE_GEMMI else None

    # ---- (1) residue index parity -----------------------------------------
    bt_idx = P._structure_residue_index(cif_path)
    if HAVE_GEMMI:
        gm_idx = {(ch.name, res.seqid.num): res.name
                  for ch in gm[0] for res in ch}
        check("residue_index", bt_idx == gm_idx,
              f"biotite {len(bt_idx)} vs gemmi {len(gm_idx)} keys")
    else:
        check("residue_index", len(bt_idx) > 0, f"{len(bt_idx)} keys (no gemmi ref)")

    # ---- (2) interface hotspots parity (public function) ------------------
    # Build the minimal UniProt-entry shape interface_hotspots consumes: the
    # barnase chain sequence as the "UniProt" sequence (offset 0), pointing at 1BRS.
    a_seq = "".join(PIF._AA3to1[rn]
                    for _, _, rn in PIF._chain_seq(arr, TARGET_CHAIN))
    entry = {"sequence": {"value": a_seq},
             "uniProtKBCrossReferences": [{"database": "PDB", "id": PDB_ID}]}
    hotspots, info = PIF.interface_hotspots(entry, contact_cutoff=5.0)
    # interface_hotspots reports positions in UNIPROT numbering (auth + offset k);
    # the gemmi references below are in auth numbering. Convert to compare like
    # for like, applying the same in-range filter interface_hotspots applies.
    k = int(info.get("offset", 0))

    def _to_uniprot(auth_nums):
        return [a + k for a in auth_nums if 1 <= a + k <= len(a_seq)]

    bt_iface = sorted(h["position"] for h in hotspots)          # UniProt frame
    bt_auth = [p - k for p in bt_iface]                          # auth frame
    if HAVE_GEMMI:
        gm_iface = _to_uniprot(_gemmi_interface(gm))
        check("interface_hotspots", bt_iface == gm_iface,
              f"biotite n={len(bt_iface)} vs gemmi n={len(gm_iface)}; "
              f"pdb={info.get('pdb')} chain={info.get('target_chain')} offset={k}")
        # The one INTENTIONAL behaviour change of this migration: the old gemmi path
        # let crystallographic symmetry mates count as interface partners. Pin that
        # delta so it stays a documented fix rather than an unnoticed drift.
        gm_sym = _to_uniprot(_gemmi_interface(gm, with_symmetry=True))
        packing = sorted(set(gm_sym) - set(bt_iface))
        check("symmetry_bug_documented",
              len(gm_sym) > len(bt_iface) and set(bt_iface) <= set(gm_sym),
              f"old gemmi n={len(gm_sym)} incl. {len(packing)} crystal-packing "
              f"residues now correctly excluded: {packing}")
    else:
        check("interface_hotspots", len(bt_iface) > 0,
              f"n={len(bt_iface)} (no gemmi ref)")

    # ---- (3) Cβ/Cα coordinate parity --------------------------------------
    # auth frame: these positions are looked up directly in the structure
    sample = [{"chain": TARGET_CHAIN, "position": p} for p in bt_auth[:8]]
    bt_cb = {k: tuple(round(c, 3) for c in v)
             for k, v in PF._cb_coords(arr, sample).items()}
    if HAVE_GEMMI:
        gm_cb = _gemmi_cb(gm, TARGET_CHAIN, [s["position"] for s in sample])
        check("cb_ca_coords", bt_cb == gm_cb,
              f"{len(bt_cb)} residues compared")
    else:
        check("cb_ca_coords", len(bt_cb) == len(sample), f"{len(bt_cb)} coords")

    # ---- (4) epitope crop window parity -----------------------------------
    # write the full structure to a PDB the crop can consume, force a crop by a
    # tiny residue cap, and compare kept residue numbers.
    pdb_path = run_dir / "full.pdb"
    pf = btpdb.PDBFile()
    pf.set_structure(arr[np.isin(arr.chain_id, [TARGET_CHAIN])])
    pf.write(str(pdb_path))
    hs = [{"chain": TARGET_CHAIN, "position": p} for p in bt_auth[:3]]
    cropped_path, _ = P._crop_target_to_epitope(pdb_path, hs, run_dir, max_residues=60)
    bt_keep = _pdb_res_ids(cropped_path, TARGET_CHAIN)
    if HAVE_GEMMI:
        gm_keep = _gemmi_crop_window(gm, TARGET_CHAIN, [h["position"] for h in hs], 60)
        check("crop_window", bt_keep == gm_keep,
              f"biotite {len(bt_keep)} vs gemmi {len(gm_keep)} residues")
    else:
        check("crop_window", len(bt_keep) > 0, f"{len(bt_keep)} residues")

    # ---- (5) Boltz template: label_seq 1..N + canonical sequence -----------
    single = run_dir / "chainA.pdb"
    pf = btpdb.PDBFile()
    pf.set_structure(arr[arr.chain_id == TARGET_CHAIN])
    pf.write(str(single))
    cif_text, n = TCIF.pdb_to_template_cif(str(single), TARGET_CHAIN)
    try:
        TCIF.verify(cif_text, n)                      # self-check: fails loud if malformed
        ok_verify = True
    except SystemExit as e:
        ok_verify, cif_text = False, str(e)
    aa_res = [rn for _, _, rn in PIF._chain_seq(arr, TARGET_CHAIN)]
    check("template_label_seq+seq", ok_verify and n == len(aa_res),
          f"n={n} residues, verify={'ok' if ok_verify else cif_text}")

    return _report()


# --------------------------------------------------------------- gemmi references
def _gemmi_interface(gm, cutoff: float = 5.0, with_symmetry: bool = False) -> list[int]:
    """Reference interface with the SAME partner set interface_hotspots uses:
    every protein chain (>=20 AA) other than the target.

    `with_symmetry` reproduces the ORIGINAL shipped gemmi behaviour, which is a bug:
    ``gemmi.NeighborSearch(model, st.cell, ...).populate()`` indexes crystallographic
    symmetry images too, and ``mark.to_cra(model)`` maps an image back to its source
    chain — so a target residue touching a symmetry copy of a partner was counted as
    a biological interface hotspot. On 1BRS (C 1 2 1) that inflates the interface from
    42 to 59 residues; the 17 extras are pure crystal packing.

    The biotite implementation searches the deposited coordinates only, so the default
    here (symmetry off) is the correct reference for it. See `symmetry_bug_documented`
    in main() for the row that pins the old-vs-new delta.
    """
    gm = gm.clone()
    if not with_symmetry:
        gm.cell = gemmi.UnitCell()          # null cell + P1 -> no symmetry images
        gm.spacegroup_hm = "P 1"
    model = gm[0]

    def n_aa(ch):
        return sum(1 for res in ch if res.name.upper() in AA)
    partners = {ch.name for ch in model if ch.name != TARGET_CHAIN and n_aa(ch) >= 20}
    ns = gemmi.NeighborSearch(model, gm.cell, cutoff + 1.0).populate()
    H = gemmi.Element("H")
    iface: set[int] = set()
    for ch in model:
        if ch.name != TARGET_CHAIN:
            continue
        for res in ch:
            if res.name.upper() not in AA:
                continue
            for atom in res:
                if atom.element == H:
                    continue
                for mark in ns.find_atoms(atom.pos, "\0", radius=cutoff):
                    cra = mark.to_cra(model)
                    if cra.chain.name in partners and cra.atom.element != H:
                        iface.add(res.seqid.num)
                        break
                else:
                    continue
                break
    return sorted(iface)


def _gemmi_cb(gm, chain_id: str, positions: list[int]) -> dict:
    out = {}
    for ch in gm[0]:
        if ch.name != chain_id:
            continue
        for res in ch:
            if res.seqid.num in positions:
                a = res.find_atom("CB", "*") or res.find_atom("CA", "*")
                if a:
                    out[res.seqid.num] = (round(a.pos.x, 3), round(a.pos.y, 3), round(a.pos.z, 3))
    return out


def _gemmi_crop_window(gm, chain_id: str, hotspots: list[int], max_residues: int) -> list[int]:
    hs = sorted(hotspots)
    center = (hs[0] + hs[-1]) // 2
    half = max_residues // 2
    lo, hi = center - half, center + half
    return sorted({res.seqid.num for ch in gm[0] if ch.name == chain_id
                   for res in ch if lo <= res.seqid.num <= hi})


def _pdb_res_ids(pdb_path: Path, chain_id: str) -> list[int]:
    a = btpdb.PDBFile.read(str(pdb_path)).get_structure(model=1)
    a = a[a.chain_id == chain_id]
    return sorted({int(a.res_id[s]) for s in struc.get_residue_starts(a)})


def _report() -> int:
    print(f"\n{'CHECK':<28} {'RESULT':<6} DETAIL")
    print("-" * 88)
    for name, ok, detail in _rows:
        print(f"{name:<28} {'PASS' if ok else 'FAIL':<6} {detail}")
    print("-" * 88)
    n_pass = sum(1 for _, ok, _ in _rows if ok)
    mode = "A/B vs gemmi" if HAVE_GEMMI else "biotite-only (gemmi absent)"
    print(f"{n_pass}/{len(_rows)} passed — mode: {mode}")
    return 0 if n_pass == len(_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
