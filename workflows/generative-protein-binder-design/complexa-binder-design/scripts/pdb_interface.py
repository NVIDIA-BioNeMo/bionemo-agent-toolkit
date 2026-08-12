#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Gold-standard binder hotspots: the PROTEIN-PROTEIN INTERFACE residues from a
co-complex PDB structure, mapped to UniProt numbering.

Why (verified on our 7-target run): UniProt Active/Binding-site features annotate
catalytic/ligand pockets (often intracellular). The real binder epitope is where a
*protein partner* actually contacts the target — exactly what a co-complex
crystal/cryo-EM structure shows. This module:
  1. takes the target's PDB IDs (from its UniProt cross-references),
  2. finds a structure where the target chain contacts ANOTHER protein chain,
  3. computes the target's interface residues (heavy-atom contact, <= cutoff Å),
  4. maps them from PDB author numbering -> UniProt numbering by aligning the PDB
     chain sequence to the UniProt sequence (valid on the AFDB model, which uses
     UniProt numbering).

Network + biotite only; numbering solved by alignment (no SIFTS API needed).
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

_AA3to1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M",
}


def pdb_ids_from_uniprot_entry(entry: dict) -> list[str]:
    """PDB IDs listed in a UniProtKB entry JSON (cross-references)."""
    ids = []
    for xref in entry.get("uniProtKBCrossReferences", []) or []:
        if xref.get("database") == "PDB":
            pid = xref.get("id")
            if pid:
                ids.append(pid.upper())
    # dedup, keep order
    seen, out = set(), []
    for p in ids:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _read_cif(pdb_id: str, timeout: int = 120):
    """Download an mmCIF and parse the first model with biotite -> AtomArray.

    Author fields (auth_asym_id / auth_seq_id) are used so chain names and residue
    numbers match the PDB's published numbering."""
    import biotite.structure.io.pdbx as pdbx
    data = urllib.request.urlopen(  # nosec B310 - fixed https RCSB literal
        f"https://files.rcsb.org/download/{pdb_id.lower()}.cif", timeout=timeout
    ).read()
    cif = pdbx.CIFFile.read(io.StringIO(data.decode("utf-8", "replace")))
    return pdbx.get_structure(cif, model=1, use_author_fields=True)


def _chain_seq(arr, chain_id: str):
    """Ordered (auth_seqid, one_letter, resname) for amino-acid residues of a chain."""
    import biotite.structure as struc
    sub = arr[arr.chain_id == chain_id]
    out = []
    for s in struc.get_residue_starts(sub):
        name = str(sub.res_name[s]).upper()
        aa = _AA3to1.get(name)
        if aa:
            out.append((int(sub.res_id[s]), aa, name))
    return out


def _best_offset(chain_seq, uni_seq: str):
    """Integer k maximizing matches of uni_seq[auth_num + k - 1] == aa.
    Returns (k, identity_fraction). Tries k=0 (PDB already in UniProt numbering)
    first, then scans the feasible window."""
    if not chain_seq:
        return 0, 0.0
    nums = [n for n, _, _ in chain_seq]
    lo, hi = 1 - min(nums), len(uni_seq) - max(nums)
    order = [0] + [k for k in range(lo, hi + 1) if k != 0]   # try 0 first
    best_k, best_frac = 0, -1.0
    for k in order:
        m = tot = 0
        for n, aa, _ in chain_seq:
            i = n + k - 1
            if 0 <= i < len(uni_seq):
                tot += 1
                m += (uni_seq[i] == aa)
        if tot:
            frac = m / tot
            if frac > best_frac:
                best_frac, best_k = frac, k
            if frac >= 0.97:
                break
    return best_k, best_frac


def interface_hotspots(entry: dict, contact_cutoff: float = 5.0,
                       max_pdbs: int = 10) -> tuple[list[dict], dict]:
    """Interface hotspots (UniProt numbering) from the best available co-complex.

    Returns (hotspots, info). Each hotspot: {chain:'A', position:int, residue:3-letter,
    source:'pdb_interface'}. info records the chosen pdb/partner/identity. Empty list
    on no suitable complex or any failure (caller falls back to UniProt/Paperclip)."""
    try:
        import numpy as np
        import biotite.structure as struc
    except Exception:  # noqa: BLE001
        return [], {"note": "biotite unavailable"}
    uni_seq = (entry.get("sequence") or {}).get("value") or ""
    if not uni_seq:
        return [], {"note": "no UniProt sequence"}
    tried = []
    for pid in pdb_ids_from_uniprot_entry(entry)[:max_pdbs]:
        try:
            arr = _read_cif(pid)
            if arr.array_length() == 0:
                continue
            chain_ids = [c for c in dict.fromkeys(struc.get_chains(arr))
                         if len(_chain_seq(arr, c)) >= 20]
            if len(chain_ids) < 2:
                tried.append(f"{pid}:<2 chains")
                continue
            # target chain = best sequence match to our UniProt
            scored = sorted(
                ((_best_offset(_chain_seq(arr, c), uni_seq), c) for c in chain_ids),
                key=lambda x: x[0][1], reverse=True)
            (k, frac), tgt = scored[0]
            if frac < 0.80:
                tried.append(f"{pid}:no-uniprot-chain({frac:.2f})")
                continue
            partner_names = [c for c in chain_ids if c != tgt]
            if not partner_names:
                tried.append(f"{pid}:no-partner")
                continue

            # heavy-atom contact search: build a spatial index over partner heavy
            # atoms, query each target amino-acid heavy atom within the cutoff.
            heavy = arr[arr.element != "H"]
            tgt_aa = {int(n) for n, _, _ in _chain_seq(arr, tgt)}
            tgt_mask = (heavy.chain_id == tgt) & np.isin(heavy.res_id, list(tgt_aa))
            partner_mask = np.isin(heavy.chain_id, partner_names)
            partner_atoms = heavy[partner_mask]
            target_atoms = heavy[tgt_mask]
            if partner_atoms.array_length() == 0 or target_atoms.array_length() == 0:
                tried.append(f"{pid}:no-heavy-atoms")
                continue
            resname = {int(n): rn for n, _, rn in _chain_seq(arr, tgt)}
            cell_list = struc.CellList(partner_atoms, cell_size=contact_cutoff)
            hits = cell_list.get_atoms(target_atoms.coord, radius=contact_cutoff)
            has_contact = (hits != -1).any(axis=1)
            iface = {int(r) for r in target_atoms.res_id[has_contact]}
            if not iface:
                tried.append(f"{pid}:no-contacts")
                continue
            hotspots = []
            for auth in sorted(iface):
                uni = auth + k
                if 1 <= uni <= len(uni_seq):
                    hotspots.append({"chain": "A", "position": uni,
                                     "residue": resname.get(auth), "source": "pdb_interface"})
            return hotspots, {"pdb": pid, "target_chain": tgt,
                              "partner_chains": sorted(partner_names), "identity": round(frac, 2),
                              "offset": k, "n_interface": len(hotspots), "cutoff": contact_cutoff}
        except Exception as e:  # noqa: BLE001
            tried.append(f"{pid}:{type(e).__name__}")
            continue
    return [], {"note": "no co-complex interface found", "tried": tried[:12]}
