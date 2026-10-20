#!/usr/bin/env python
"""Validate an annotated CIF and report gotchas; never repairs.

Part 1: invariant pipeline + missing-atom/res_id-gap checks (coord-implies-seq is
pre-checked since the pipeline auto-fixes it). Part 2: gotcha scan (formal charges,
ligand bond orders, metal bonds, duplicate res_names, struct_conn). Exits nonzero on
any error (``--strict`` also fails on warnings).

Usage::

    export PYTHONPATH=$PWD/src
    export ALLOW_BIOTITE_CCD=True
    python skills/rfd4-proteina-annotated-cif/scripts/check_annotated_cif.py <file.cif> [--strict] [--quiet]
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import fire
import numpy as np
from atomworks.io.utils.ccd import get_standard_ccd_codes
from biotite.structure import AtomArray

# Must precede any CIF parse: registers rfproteina conditions, else they drop silently.
import rfproteina.conditions  # noqa: F401  (import for registry side-effect ONLY)
from rfproteina.conditions import C_IDXGRP

# Severity model

ERROR = "error"
WARN = "warn"
# NOTE: expected-but-worth-confirming. Never gates; --strict does not promote it.
NOTE = "note"

_TAGS = {ERROR: "ERROR", WARN: "WARN ", NOTE: "note "}

# Standard AAs + nucleotides; anything else uses component-level chemistry checks.
POLYMER_RES_NAMES = frozenset(
    "ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL " "A C G U DA DC DG DT DI".split()
)


@dataclass(frozen=True)
class Violation:
    severity: str
    check: str
    message: str

    def format(self) -> str:
        return f"  {_TAGS[self.severity]} [{self.check}] {self.message}"


# Metal-ligand coordination is ~1.9-2.5 A; tighter than atomworks' 3.6 A to avoid second-shell.
_METAL_COORD_MAX_DIST = 2.6
_COORDINATING_ELEMENTS = frozenset({"N", "O", "S", "SE", "CL", "BR"})


def _describe_metal_coordination(arr: AtomArray, metal_mask: np.ndarray) -> str:
    """Name the atoms geometrically coordinating each unbonded metal."""
    coords = arr.coord
    out = []
    for i in np.where(metal_mask)[0]:
        partners = []
        for j in range(arr.array_length()):
            if j == i or str(arr.element[j]).upper() not in _COORDINATING_ELEMENTS:
                continue
            d = float(np.linalg.norm(coords[j] - coords[i]))
            if d <= _METAL_COORD_MAX_DIST:
                partners.append(f"{_residue_label(arr, j)}:{arr.atom_name[j]} ({d:.2f}A)")
        if partners:
            out.append(f"{_residue_label(arr, i)}:{arr.atom_name[i]} -> {', '.join(sorted(partners))}")
    return "; ".join(out)


def _residue_label(arr: AtomArray, i: int) -> str:
    """``chain/res_name res_id`` label for atom *i*."""
    chain = arr.chain_id[i]
    ins = str(arr.ins_code[i]).strip() if "ins_code" in arr.get_annotation_categories() else ""
    return f"{chain}/{arr.res_name[i]}{arr.res_id[i]}{ins}"


def _truncate(items: Iterable[object], limit: int = 12) -> str:
    items = list(items)
    if len(items) <= limit:
        return ", ".join(str(x) for x in items)
    shown = ", ".join(str(x) for x in items[:limit])
    return f"{shown}, ... (+{len(items) - limit} more)"


# Loading


def check_entity_sequences(path: Path) -> list[Violation]:
    """Check raw polymer residue references before parsing can discard CIF metadata."""
    from atomworks.io.utils.io_utils import read_any

    block = read_any(path).block
    if "atom_site" not in block:
        return []
    if "entity_poly_seq" not in block:
        return (
            [
                Violation(
                    WARN, "entity_sequence_unavailable", "No _entity_poly_seq; polymer sequence references unchecked."
                )
            ]
            if "entity_poly" in block
            else []
        )
    nonpolymers = set()
    if "entity" in block:
        entities = block["entity"]
        nonpolymers = {
            entity
            for entity, kind in zip(entities["id"].as_array(str), entities["type"].as_array(str), strict=True)
            if kind in ("non-polymer", "water", "branched")
        }
    sequences = defaultdict(set)
    table = block["entity_poly_seq"]
    for entity, number, component in zip(
        *(table[key].as_array(str) for key in ("entity_id", "num", "mon_id")), strict=True
    ):
        sequences[entity, number].add(component)
    atoms = block["atom_site"]
    fields = ("label_asym_id", "label_entity_id", "label_seq_id", "label_comp_id")
    residues = set(
        zip(
            *(atoms[key].as_array(str) for key in fields),
            strict=True,
        )
    )
    mismatches = []
    for chain, entity, number, component in sorted(residues):
        if entity in nonpolymers or number in (".", "?", ""):
            continue  # Non-polymers have no entity_poly_seq position.
        expected = sequences[entity, number]
        if component not in expected:
            mismatches.append(
                f"{chain}/{component}{number} references entity {entity}: "
                f"{','.join(sorted(expected)) if expected else 'sequence position absent'}"
            )
    if not mismatches:
        return []
    return [
        Violation(
            ERROR,
            "entity_sequence_mismatch",
            f"{len(mismatches)} residue(s) disagree with _entity_poly_seq: {_truncate(mismatches)}. "
            "Check entity assignments after chain splitting/cropping; source left unchanged.",
        )
    ]


def load_atom_array(path: Path) -> AtomArray:
    """Parse *path* into an AtomArrayPlus without repairing anything."""
    from atomworks.io.config import ParseConfig
    from atomworks.io.parser import parse

    config = ParseConfig(
        add_missing_atoms=False,
        load_standard_annotations=True,
        remove_waters=False,
        remove_ccds=(),
        fix_ligands_at_symmetry_centers=False,
        fix_arginines=False,
        add_id_and_entity_annotations=True,
        convert_mse_to_met=False,
        long_bond_policy="keep",
        struct_conn_distance_policy="keep",
        add_bond_types_from_struct_conn=("covale", "metalc", "disulf"),
        build_assembly="first",
        return_atom_array_plus=True,
    )
    result = parse(path, config=config)
    assemblies = result.get("assemblies") or {}
    arr = next(iter(assemblies.values())) if assemblies else result["asym_unit"]
    if hasattr(arr, "stack_depth"):
        arr = arr[0]
    return arr


# Direct coord-implies-sequence pre-check (runs before the pipeline)


def check_conditioned_coordinates(arr: AtomArray) -> list[Violation]:
    """Require finite selected coordinate references; leave unselected atoms alone.
    Absolute mask-only inputs use stored coordinates; internal conditions need explicit references.
    """
    from atomworks.ml.conditions import C_CRD

    from rfproteina.conditions import C_INTCRD

    violations = []
    for condition in (C_CRD, C_INTCRD):
        mask = condition.mask(arr)
        references = (
            arr.coord if condition is C_CRD and not condition.has_annotation(arr) else condition.annotation(arr)
        )
        bad = mask & ~np.isfinite(references).all(axis=-1)
        if bad.any():
            labels = [f"{_residue_label(arr, i)}:{arr.atom_name[i]}" for i in np.flatnonzero(bad)]
            violations.append(
                Violation(
                    ERROR,
                    "conditioned_coordinates_nonfinite",
                    f"{condition.name}: {len(labels)} conditioned atom(s) have nonfinite reference coordinates: "
                    f"{_truncate(labels)}. Source left unchanged.",
                )
            )
    return violations


def check_coord_implies_seq(arr: AtomArray) -> list[Violation]:
    """Flag non-backbone coord-conditioned tokens that lack sequence conditioning.

    Mirrors ``EnsureAtomizedOrCoordConditionedResiduesAreSequenceConditioned`` but reports
    instead of fixing; must run before the pipeline, which ORs the fix in.
    """
    from atomworks.io.utils.annotator import ensure_annotations
    from atomworks.io.utils.atom_array_plus import as_atom_array_plus
    from atomworks.ml.conditions import C_CRD, C_SEQ
    from atomworks.ml.utils.token import apply_and_spread_token_wise

    from rfproteina.conditions import C_CRDGRP

    aap = as_atom_array_plus(arr.copy())
    violations: list[Violation] = []

    seq_mask = C_SEQ.mask(aap, default="generate")
    # Absolute OR internal coord conditioning, matching the transform.
    crd_mask = C_CRD.mask(aap, default="generate") | C_CRDGRP.is_internal(aap)

    has_atomize = "atomize" in aap.get_annotation_categories()
    if not crd_mask.any() and not has_atomize:
        return violations

    def _spread(mask: np.ndarray) -> np.ndarray:
        return apply_and_spread_token_wise(aap, mask, np.any)

    seq_tok = _spread(seq_mask)

    # Rule 1: atomized tokens always require sequence conditioning.
    if has_atomize:
        bad = _spread(aap.atomize) & ~seq_tok
        if bad.any():
            labels = sorted({_residue_label(aap, i) for i in np.where(bad)[0]})
            violations.append(
                Violation(
                    ERROR,
                    "atomized_must_be_seq_conditioned",
                    f"{len(labels)} atomized residue(s) lack sequence conditioning: {_truncate(labels)}. "
                    "Pipeline would auto-fix; CIF as written is wrong.",
                )
            )

    # Rule 2: non-backbone coordinate conditioning requires sequence conditioning.
    if crd_mask.any():
        ensure_annotations(aap, "is_protein_backbone", "is_rna_backbone", "is_dna_backbone")
        is_backbone = aap.is_protein_backbone | aap.is_rna_backbone | aap.is_dna_backbone
        bad = _spread(crd_mask & ~is_backbone) & ~seq_tok
        if bad.any():
            labels = sorted({_residue_label(aap, i) for i in np.where(bad)[0]})
            violations.append(
                Violation(
                    ERROR,
                    "coord_conditioned_must_be_seq_conditioned",
                    f"{len(labels)} residue(s) have non-backbone coord conditioning but no "
                    f"sequence conditioning: {_truncate(labels)}. "
                    "Pipeline would auto-fix; CIF as written is wrong. (Backbone-only N/CA/C/O exempt.)",
                )
            )

    return violations


# Invariant pipeline


def run_pipeline_validation(arr: AtomArray) -> list[Violation]:
    """Run the design validation pipeline on one realization of *arr*, as generation does.

    Delegates to :py:func:`rfproteina.conditions_reporting.run_pipeline_validation`, which
    realizes expandable segments on a copy before featurization.
    """
    from rfproteina.conditions_reporting import run_pipeline_validation as validate

    violations = []
    for message in validate(arr):
        if message.startswith("[pipeline_error] "):
            detail = message.removeprefix("[pipeline_error] ")
            violations.append(Violation(ERROR, "pipeline_error", detail.splitlines()[0] if detail else message))
        else:
            violations.append(Violation(ERROR, "pipeline", message))
    return violations


# Component atom inventories and res_id gaps


def check_missing_atoms(arr: AtomArray) -> list[Violation]:
    """Report incomplete polymers and component/CCD atom-set mismatches for intent review."""
    import biotite.structure as struc
    from atomworks.constants import CCD_MIRROR_PATH
    from atomworks.io.template import _get_missing_atoms_template

    # CCD_MIRROR_PATH is unset in many envs; "" falls back to Biotite's built-in CCD.
    ccd_mirror = str(CCD_MIRROR_PATH or "")
    # OXT is the C-terminal carboxylate oxygen: legitimately absent from every internal polymer
    # residue, so ignoring it avoids flagging essentially the whole chain.
    _TERMINAL_OPTIONAL_ATOMS = frozenset({"OXT"})

    cats = arr.get_annotation_categories()
    atomize = arr.get_annotation("atomize").astype(bool) if "atomize" in cats else np.zeros(len(arr), bool)

    bounds = struc.get_residue_starts(arr, add_exclusive_stop=True)
    ccd_short, ccd_mismatch, polymer_short, n_missing = [], [], [], 0
    for i in range(len(bounds) - 1):
        start, stop = int(bounds[i]), int(bounds[i + 1])
        res_name = str(arr.res_name[start])
        if res_name == "HOH":
            continue

        # Heavy atoms only (hydrogen_policy="remove"), else every CCD hydrogen reads as missing.
        heavy_names = frozenset(str(arr.atom_name[j]) for j in range(start, stop) if str(arr.element[j]).upper() != "H")
        try:
            template = _get_missing_atoms_template(
                ccd_code=res_name,
                actual_atom_names=heavy_names,
                ccd_mirror_path=ccd_mirror,
                hydrogen_policy="remove",
            )
        except ValueError:
            ccd_mismatch.append(_residue_label(arr, start))
            continue

        if template is None:
            continue
        missing = [n for n in (str(x) for x in template.atom_name) if n not in _TERMINAL_OPTIONAL_ATOMS]
        if not missing:
            continue

        label = f"{_residue_label(arr, start)} (+{len(missing)})"
        # Polymer if not atomized and res_name is standard; atomize marks ligands/PTMs/non-canonicals.
        is_polymer = not atomize[start] and res_name in POLYMER_RES_NAMES
        if is_polymer:
            polymer_short.append(label)
        else:
            ccd_short.append(label)
            n_missing += len(missing)

    out = []
    if ccd_short:
        out.append(
            Violation(
                WARN,
                "component_ccd_atoms_missing",
                f"{len(ccd_short)} non-polymer component(s) are missing {n_missing} heavy atom(s) "
                f"from the CCD entry with the same code: {_truncate(sorted(ccd_short), limit=20)}. "
                "Confirm whether each component is intended to match that CCD or is an explicitly authored "
                "custom component; validate its atoms, bonds, bond orders, aromaticity, and formal charges.",
            )
        )
    if ccd_mismatch:
        out.append(
            Violation(
                WARN,
                "component_ccd_atom_set_mismatch",
                f"Could not compare {len(ccd_mismatch)} component(s) with the CCD entry for their code: "
                f"{_truncate(sorted(ccd_mismatch), limit=20)}. Non-CCD and custom components are supported; "
                "confirm their explicit atom inventory, bonds, bond orders, aromaticity, and formal charges.",
            )
        )
    if polymer_short:
        out.append(
            Violation(
                WARN,
                "polymer_atoms_missing",
                f"{len(polymer_short)} polymer residue(s) are incomplete: "
                f"{_truncate(sorted(polymer_short), limit=8)}. Express partial conditioning with masks on a "
                "complete residue. If the source is genuinely unresolved, confirm the resulting component "
                "identity and custom-CCD behavior before generation.",
            )
        )
    return out


def check_res_id_gaps(arr: AtomArray) -> list[Violation]:
    """Flag internal res_id discontinuities within an index group (shared logic; see below)."""
    from rfproteina.transforms.invariants import find_index_group_res_id_gaps

    if not C_IDXGRP.has_annotation(arr):
        return [Violation(WARN, "res_id_gap_check_skipped", "No index-group annotation; cannot check res_id gaps.")]

    messages = find_index_group_res_id_gaps(arr)
    if not messages:
        return []
    return [
        Violation(
            WARN,
            "res_id_gap",
            f"Residue numbering has {len(messages)} internal gap(s) within index groups: "
            f"{'; '.join(messages)}. Model reads intra-group gaps as breaks within a "
            "contiguously-indexed region -- confirm intentional.",
        )
    ]


# Missing or unknown formal charges


def check_formal_charges(path: Path) -> list[Violation]:
    """Flag ``?`` (unknown) ``_atom_site.pdbx_formal_charge`` entries.

    Reads raw CIF: the parser resolves ``?`` to 0/CCD, hiding unknown-vs-neutral downstream.
    """
    from atomworks.io.utils.io_utils import read_any

    try:
        block = read_any(path).block
        category = block["atom_site"]
    except Exception as e:
        return [Violation(WARN, "charge_check_failed", f"Could not read atom_site: {type(e).__name__}: {e}")]

    if "pdbx_formal_charge" not in category:
        return [
            Violation(
                WARN,
                "formal_charge_absent",
                "No '_atom_site.pdbx_formal_charge' column; every charge defaults to 0/CCD.",
            )
        ]

    charges = category["pdbx_formal_charge"].as_array(str)
    comps = category["label_comp_id"].as_array(str)
    unknown = np.array([str(c).strip() in ("?", ".", "") for c in charges])
    if not unknown.any():
        return []

    per_res = Counter(str(c) for c, u in zip(comps, unknown, strict=False) if u)
    known = Counter(str(c).strip() for c in charges if str(c).strip() not in ("?", ".", ""))
    known_str = f" Specified elsewhere: {dict(known)}." if known else ""
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(per_res.items(), key=lambda kv: -kv[1]))
    return [
        Violation(
            WARN,
            "formal_charge_unknown",
            f"{int(unknown.sum())}/{len(charges)} atoms have an unknown formal charge ('?'). "
            f"By residue: {breakdown}.{known_str} "
            "Mixed known/unknown looks deliberate but isn't.",
        )
    ]


# Ligands that lost their bond orders


def _residue_slices(arr: AtomArray) -> Iterator[tuple[int, int]]:
    """Yield ``(start, stop)`` for each residue."""
    import biotite.structure as struc

    bounds = struc.get_residue_starts(arr, add_exclusive_stop=True)
    for i in range(len(bounds) - 1):
        yield int(bounds[i]), int(bounds[i + 1])


def _has_cycle(n_atoms: int, edges: list[tuple[int, int]]) -> bool:
    """True if the graph has a cycle (union-find; biotite 1.6 has no ``find_rings``)."""
    parent = list(range(n_atoms))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra == rb:
            return True
        parent[ra] = rb
    return False


def check_ligand_bond_orders(arr: AtomArray) -> list[Violation]:
    """Flag multi-atom non-polymer residues whose bonds are 100% SINGLE.

    A ring or sizeable ligand with no double/aromatic bond is almost always stripped orders.
    """
    import biotite.structure as struc

    if arr.bonds is None:
        return [Violation(WARN, "no_bonds", "AtomArray carries no BondList at all.")]

    bonds = arr.bonds.as_array()
    flagged = []
    for start, stop in _residue_slices(arr):
        if arr.is_polymer[start]:
            continue
        n_atoms = stop - start
        if n_atoms < 2:
            continue

        intra = bonds[(bonds[:, 0] >= start) & (bonds[:, 0] < stop) & (bonds[:, 1] >= start) & (bonds[:, 1] < stop)]
        if len(intra) == 0:
            continue
        if not np.all(intra[:, 2] == int(struc.BondType.SINGLE)):
            continue

        heavy = int(np.sum(np.char.upper(arr.element[start:stop].astype(str)) != "H"))
        edges = [(int(a - start), int(b - start)) for a, b, _ in intra]
        ring = _has_cycle(n_atoms, edges)
        if ring or heavy > 6:
            why = "has a ring" if ring else f"{heavy} heavy atoms"
            flagged.append(f"{_residue_label(arr, start)} ({len(intra)} bonds, all SINGLE, {why})")

    if not flagged:
        return []
    return [
        Violation(
            WARN,
            "ligand_all_single_bonds",
            f"{len(flagged)} non-polymer residue(s) have only SINGLE bonds where aromaticity or "
            f"higher orders are expected: {_truncate(flagged)}. "
            "Orders likely stripped on import; check _chem_comp_bond value_order.",
        )
    ]


# Metal coordination bonds


def check_metal_bonds(arr: AtomArray) -> list[Violation]:
    """Flag metal atoms with zero bonds -- only where that is actually wrong.

    Lone ion with zero bonds = note (struct_conn usually absent); metal inside a multi-atom
    residue (heme Fe, Fe-S cluster) with no bonds = error (bond graph collapsed).
    """
    import biotite.structure as struc
    from atomworks.constants import METAL_ELEMENTS

    elements = np.char.upper(arr.element.astype(str))
    metal_mask = np.isin(elements, list(METAL_ELEMENTS))
    if not metal_mask.any():
        return []

    if arr.bonds is None:
        return [
            Violation(
                WARN,
                "metal_no_bonds",
                f"{int(metal_mask.sum())} metal atom(s) present but array has no BondList.",
            )
        ]

    bonds = arr.bonds.as_array()
    # Residue extent per atom: separates a free ion from a metal inside a residue.
    res_size = np.zeros(arr.array_length(), dtype=int)
    for s, e in _residue_slices(arr):
        res_size[s:e] = e - s

    lone_unbonded, embedded_unbonded, coordinated = [], [], []
    for i in np.where(metal_mask)[0]:
        incident = bonds[(bonds[:, 0] == i) | (bonds[:, 1] == i)]
        label = f"{_residue_label(arr, i)}:{arr.atom_name[i]}"
        if len(incident) == 0:
            if res_size[i] == 1:
                lone_unbonded.append(label)  # free ion: expected
            else:
                embedded_unbonded.append(f"{label} (in a {res_size[i]}-atom residue)")
        else:
            n_coord = int(np.sum(incident[:, 2] == int(struc.BondType.COORDINATION)))
            coordinated.append(f"{label} ({len(incident)} bonds, {n_coord} COORDINATION)")

    out = []
    if embedded_unbonded:
        out.append(
            Violation(
                ERROR,
                "metal_missing_intra_residue_bonds",
                f"{len(embedded_unbonded)} metal atom(s) sit inside a multi-atom residue but have NO "
                f"bonds: {_truncate(embedded_unbonded)}. These bonds belong to the residue itself "
                "(heme iron to its 4 porphyrin N), so their absence means the bond graph is broken. "
                "Fix the source CIF or its CCD entry; do not paper over with --coordination_bond.",
            )
        )
    if lone_unbonded:
        nearby = _describe_metal_coordination(arr, metal_mask)
        detail = f" Nearby coordinating atoms: {nearby}." if nearby else " No coordinating atoms within range."
        out.append(
            Violation(
                NOTE,
                "metal_no_bonds",
                f"{len(lone_unbonded)} metal atom(s) have no bonds: {_truncate(lone_unbonded)}. Normal "
                f"-- most CIFs lack struct_conn, so the metal reaches the model as an isolated atom.{detail} "
                "These are geometric neighbours, not bonds. If coordination bonds are intended, "
                "specify their atom pairs and add them explicitly with the AtomWorks API "
                "or Design Studio. Never infer them by distance.",
            )
        )
    if coordinated:
        non_coord = [c for c in coordinated if ", 0 COORDINATION" in c]
        if non_coord:
            out.append(
                Violation(
                    WARN,
                    "metal_bonds_not_coordination",
                    f"Metal(s) bonded but with no COORDINATION-typed bond: {_truncate(non_coord)}.",
                )
            )
    return out


# Duplicate res_name values describing different ligands


def check_duplicate_res_names(arr: AtomArray) -> list[Violation]:
    """Flag one res_name used for two structurally different residues.

    ``_atom_array_chem_comp_atom_rows`` is first-wins, so a second ligand sharing a res_name
    is silently described by the first's definition.
    """
    from atomworks.io.utils.bonds import hash_atom_array

    by_name = defaultdict(list)

    # Only non-standard residues collide meaningfully; for standard CCDs the CCD is authoritative.
    standard = get_standard_ccd_codes()

    for start, stop in _residue_slices(arr):
        res_name = str(arr.res_name[start])
        if res_name in standard:
            continue
        # Per-residue connectivity+annotation hash: same res_name, different hash = collision.
        res_hash = hash_atom_array(arr[start:stop])
        by_name[res_name].append((res_hash, _residue_label(arr, start)))

    out = []
    for res_name, entries in sorted(by_name.items()):
        distinct_hashes = {h for h, _ in entries}
        if len(distinct_hashes) <= 1:
            continue

        examples = _truncate(sorted(label for _, label in entries), limit=8)
        out.append(
            Violation(
                ERROR,
                "duplicate_res_name_different_ligand",
                f"res_name '{res_name}' describes {len(distinct_hashes)} structurally DIFFERENT residues "
                f"(differing connectivity/atom hashes); instances: {examples}. "
                "_atom_array_chem_comp_atom_rows is first-wins, so chem_comp describes all with the "
                "first's definition. Mitigate with "
                "atomworks.io.tools.inference.assign_res_name_from_atom_array_hash (renames by hash to 'L:{id}').",
            )
        )
    return out


# struct_conn and polymer-to-non-polymer bonds


def check_struct_conn(path: Path, arr: AtomArray) -> list[Violation]:
    """Verify declared ``struct_conn`` covales materialized as bonds; report inferred ones.

    A declared covale absent from the bond graph is a silently-lost modification; with none
    declared, every polymer<->non-polymer bond was inferred from geometry.
    """
    from atomworks.io.utils.io_utils import read_any

    out: list[Violation] = []

    try:
        block = read_any(path).block
    except Exception as e:
        return [Violation(WARN, "struct_conn_check_failed", f"Could not read CIF: {type(e).__name__}: {e}")]

    # Inter-residue polymer<->non-polymer bonds present in the parsed array.
    inferred = []
    if arr.bonds is not None:
        bonds = arr.bonds.as_array()
        for a, b, _ in bonds:
            if arr.is_polymer[a] == arr.is_polymer[b]:
                continue
            if arr.res_id[a] == arr.res_id[b] and arr.chain_id[a] == arr.chain_id[b]:
                continue
            inferred.append(
                f"{_residue_label(arr, a)}:{arr.atom_name[a]} -- {_residue_label(arr, b)}:{arr.atom_name[b]}"
            )

    if "struct_conn" not in block:
        if inferred:
            out.append(
                Violation(
                    WARN,
                    "struct_conn_absent_bonds_inferred",
                    f"No _struct_conn category, but {len(inferred)} polymer<->non-polymer bond(s) "
                    f"were inferred from geometry: {_truncate(inferred)}. "
                    "Inferred bonds are a guess -- declare them in struct_conn.",
                )
            )
        else:
            out.append(
                Violation(
                    WARN,
                    "struct_conn_absent",
                    "No _struct_conn category. Any covalent modification / NCAA linkage must be "
                    "inferred from geometry. If this structure has one, declare it explicitly.",
                )
            )
        return out

    category = block["struct_conn"]

    def _col(name: str) -> np.ndarray | None:
        if name not in category:
            return None
        return np.atleast_1d(category[name].as_array(str))

    conn_type = _col("conn_type_id")
    n_records = len(conn_type) if conn_type is not None else 0
    p1_comp, p2_comp = _col("ptnr1_label_comp_id"), _col("ptnr2_label_comp_id")
    p1_atom, p2_atom = _col("ptnr1_label_atom_id"), _col("ptnr2_label_atom_id")
    p1_asym, p2_asym = _col("ptnr1_label_asym_id"), _col("ptnr2_label_asym_id")

    if p1_atom is None or p2_atom is None:
        return [
            Violation(
                WARN,
                "struct_conn_unparsed",
                f"_struct_conn has {n_records} record(s) but no ptnr atom_id columns to verify.",
            )
        ]

    bonds = arr.bonds.as_array() if arr.bonds is not None else np.zeros((0, 3), dtype=int)
    bond_pairs = {frozenset((int(a), int(b))) for a, b, _ in bonds}

    missing = []
    for k in range(n_records):
        ctype = str(conn_type[k]).lower() if conn_type is not None else "?"
        # Only covalent linkages must appear in the bond graph; disulf/hydrog/metalc vary.
        if ctype not in ("covale", "covalent"):
            continue

        def _find(atom_name: str, comp: str | None, asym: str | None) -> np.ndarray:
            m = arr.atom_name == atom_name
            if comp is not None:
                m &= arr.res_name == comp
            if asym is not None:
                m &= arr.chain_id == asym
            return np.where(m)[0]

        i_cands = _find(
            str(p1_atom[k]),
            str(p1_comp[k]) if p1_comp is not None else None,
            str(p1_asym[k]) if p1_asym is not None else None,
        )
        j_cands = _find(
            str(p2_atom[k]),
            str(p2_comp[k]) if p2_comp is not None else None,
            str(p2_asym[k]) if p2_asym is not None else None,
        )

        desc = (
            f"{p1_comp[k] if p1_comp is not None else '?'}:{p1_atom[k]} -- "
            f"{p2_comp[k] if p2_comp is not None else '?'}:{p2_atom[k]} ({ctype})"
        )
        if len(i_cands) == 0 or len(j_cands) == 0:
            missing.append(f"{desc} [endpoint atom not found in structure]")
            continue
        if not any(frozenset((int(i), int(j))) in bond_pairs for i in i_cands for j in j_cands):
            missing.append(f"{desc} [declared but no bond in graph]")

    if missing:
        out.append(
            Violation(
                ERROR,
                "struct_conn_bond_missing",
                f"{len(missing)} declared covale struct_conn record(s) did not materialize as bonds: "
                f"{_truncate(missing)}. The covalent modification was silently lost.",
            )
        )
    else:
        out.append(
            Violation(
                WARN,
                "struct_conn_ok",
                f"_struct_conn present with {n_records} record(s); all covale linkages verified in "
                "the bond graph. (Informational -- confirm matches design intent.)",
            )
        )
    return out


# Driver


def check_cif(path: Path, skip_pipeline: bool = False) -> tuple[list[Violation], object]:
    """Run every check against *path*. Returns ``(violations, atom_array)``."""
    violations = check_entity_sequences(path)
    arr = load_atom_array(path)

    # Part 1 - pre-check FIRST (pipeline would auto-fix this away).
    violations += check_conditioned_coordinates(arr)
    violations += check_coord_implies_seq(arr)

    # Part 1 - invariants, then the pipeline backstop.
    violations += check_missing_atoms(arr)
    violations += check_res_id_gaps(arr)
    if not skip_pipeline:
        violations += run_pipeline_validation(arr)

    # Part 2 - gotcha scan.
    violations += check_formal_charges(path)
    violations += check_ligand_bond_orders(arr)
    violations += check_metal_bonds(arr)
    violations += check_duplicate_res_names(arr)
    violations += check_struct_conn(path, arr)

    return violations, arr


def main(cif: str, strict: bool = False, skip_pipeline: bool = False, quiet: bool = False) -> None:
    """Validate an annotated CIF: invariant pipeline + gotcha scan. Never repairs.

    Args:
      cif: Path to the CIF to validate.
      strict: Treat warnings as errors (nonzero exit).
      skip_pipeline: Skip the slow validation pipeline.
      quiet: Print only violations and the verdict.
    """
    path = Path(cif)
    if not path.exists():
        print(f"error: no such file: {cif}", file=sys.stderr)
        raise SystemExit(2)

    # atomworks is chatty; keep the report readable.
    warnings.filterwarnings("ignore")
    logging.getLogger("atomworks").setLevel(logging.ERROR)
    try:
        violations, arr = check_cif(path, skip_pipeline=skip_pipeline)
    except Exception as e:
        print(f"error: failed to load {cif}: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    if not quiet:
        res_names = sorted({str(x) for x in arr.res_name})
        print(path)
        print(f"  {len(arr)} atoms, {len({str(c) for c in arr.chain_id})} chain(s), res_names: {_truncate(res_names)}")

    errors = [v for v in violations if v.severity == ERROR]
    warns = [v for v in violations if v.severity == WARN]
    notes = [v for v in violations if v.severity == NOTE]
    if not violations:
        print("  (no violations)")
    for v in errors + warns + notes:
        print(v.format())
    print(f"\n  {len(errors)} error(s), {len(warns)} warning(s), {len(notes)} note(s)")

    if errors or (warns and strict):
        raise SystemExit(1)


if __name__ == "__main__":
    fire.Fire(main)
