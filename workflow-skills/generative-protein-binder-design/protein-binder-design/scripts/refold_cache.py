#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Reconcile a synthetic campaign with saved responses; never submit inference.

The cache binding contract is documented in references/offline.md. This is an
offline fixture/recovery adapter, not an endpoint client or a provenance attestor.

Usage: python3 refold_cache.py manifest.json --output-dir DIR
Arguments: A synthetic offline-bookkeeping manifest and a new directory outside its run.
Output: Copied run with verified metrics or per-candidate blocked reasons, both CSVs,
    summary.json, recovered complexes, and a JSON summary on stdout.
Exit codes: 0 recovery/export completed (inspect blocked candidates); 1 invalid run
    or I/O failure; 2 invalid CLI arguments. No inference requests are submitted.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
from pathlib import Path

from biotite import InvalidFileError

from manifest import Manifest
from offline_bookkeeping import export_run

PLDDT_PERCENT_MAX = 100
ARTIFACT_ID_HEX_LENGTH = 16


class CacheError(ValueError):
    """A saved response cannot safely supply scores for this candidate."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise CacheError("artifact_outside_run")
    return path


def checked_bytes(root: Path, record: dict) -> bytes:
    try:
        value = local_file(root, record["path"]).read_bytes()
    except FileNotFoundError as exc:
        raise CacheError("missing_artifact") from exc
    if digest(value) != record["sha256"]:
        raise CacheError("artifact_digest_mismatch")
    return value


def finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def binder_plddt(text, format, chain, sequence_length, scale):
    """Mean CA confidence for an explicitly selected binder chain and scale."""
    from biotite.structure.io import pdb, pdbx

    if format == "pdb":
        atoms = pdb.PDBFile.read(io.StringIO(text)).get_structure(
            model=1, extra_fields=["b_factor"]
        )
    elif format in {"cif", "mmcif"}:
        atoms = pdbx.get_structure(
            pdbx.CIFFile.read(io.StringIO(text)),
            model=1,
            use_author_fields=False,
            extra_fields=["b_factor"],
        )
    else:
        raise CacheError("unsupported_structure_format")
    selected = atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA")]
    if len(selected) != sequence_length or not len(selected):
        raise CacheError("binder_length_mismatch")
    if scale not in {"0-1", "0-100"}:
        raise CacheError("plddt_scale_unresolved")
    values = [float(v) for v in selected.b_factor]
    upper = 1 if scale == "0-1" else PLDDT_PERCENT_MAX
    if any(not math.isfinite(v) or not 0 <= v <= upper for v in values):
        raise CacheError("invalid_plddt")
    return sum(values) / len(values) * (PLDDT_PERCENT_MAX / upper)


def extract_scores(manifest: Manifest, candidate: dict, root: Path):
    binding = candidate.get("prediction")
    if not binding:
        raise CacheError("missing_prediction")
    target = checked_bytes(root, manifest.data["target"]["structure"])
    if binding["candidate_id"] != candidate["id"]:
        raise CacheError("candidate_mismatch")
    if binding["target_sha256"] != digest(target):
        raise CacheError("target_mismatch")
    if binding["sequence_sha256"] != digest(candidate["sequence"].encode()):
        raise CacheError("sequence_mismatch")
    if binding["binder_chain"] == binding["target_chain"]:
        raise CacheError("chain_roles_overlap")
    raw = checked_bytes(root, binding["response"])
    response = json.loads(raw)
    index = binding["sample_index"]
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise CacheError("invalid_sample_index")
    scores = {}
    if binding["provider"] == "boltz2":
        structures = response["structures"]
        confidences = response.get("confidence_scores", [])
        if len(confidences) != len(structures):
            raise CacheError("sample_count_mismatch")
        if index >= len(structures):
            raise CacheError("invalid_sample_index")
        sample = structures[index]
        scores["boltz2_confidence"] = confidences[index]
    elif binding["provider"] == "openfold3":
        outputs = [
            o for o in response["outputs"] if o.get("input_id") == candidate["id"]
        ]
        if len(outputs) != 1:
            raise CacheError("candidate_mismatch")
        samples = outputs[0]["structures_with_scores"]
        if index >= len(samples):
            raise CacheError("invalid_sample_index")
        sample = samples[index]
        if "iptm_score" in sample:
            scores["iptm"] = sample["iptm_score"]
    else:
        raise CacheError("unsupported_provider")
    if any(not finite(v) or not 0 <= v <= 1 for v in scores.values()):
        raise CacheError("invalid_confidence")
    text, format = sample["structure"], sample["format"]
    if digest(text.encode()) != binding["complex_sha256"]:
        raise CacheError("sample_digest_mismatch")
    # Both chains must be present; confidence cannot establish a missing complex.
    from pdb_utils import structure_ca_coords

    structure_ca_coords(text, binding["target_chain"], format=format)
    scores["binder_plddt"] = binder_plddt(
        text,
        format,
        binding["binder_chain"],
        len(candidate["sequence"]),
        binding["plddt_scale"],
    )
    if "self_consistency_rmsd" in manifest.missing_scores(candidate["id"]):
        from metrics import ca_rmsd_from_structures

        backbone = checked_bytes(root, binding["backbone"])
        scores["self_consistency_rmsd"] = ca_rmsd_from_structures(
            backbone.decode(),
            text,
            backbone_chain=binding["backbone_chain"],
            predicted_chain=binding["binder_chain"],
            predicted_format=format,
        )
    return scores, text, format, binding


def recover(input_manifest: Path, output_dir: Path) -> dict:
    """Copy an interrupted fixture; preserve complete results and failed stages."""
    input_manifest, output_dir = (
        Path(input_manifest).resolve(),
        Path(output_dir).resolve(),
    )
    if input_manifest.name != "manifest.json":
        raise ValueError("input must be named manifest.json")
    if output_dir.is_relative_to(input_manifest.parent):
        raise ValueError("output must be outside the source run")
    if Manifest.load(input_manifest).data.get("mode") != "offline-bookkeeping":
        raise ValueError(
            "this helper accepts explicitly synthetic offline-bookkeeping runs only"
        )
    # Copy once; refusing an existing destination prevents accidental overwrites.
    shutil.copytree(input_manifest.parent, output_dir)
    manifest = Manifest.load(output_dir)
    manifest.data["run_dir"] = str(output_dir)
    manifest.data["mode"] = "offline-bookkeeping"
    manifest.data["source_manifest_sha256"] = digest(input_manifest.read_bytes())
    for candidate in manifest.data["candidates"]:
        missing = manifest.missing_scores(candidate["id"])
        if not missing:
            candidate["cache_status"] = "complete"
            candidate.pop("cache_reason", None)
            continue
        try:
            scores, structure, format, binding = extract_scores(
                manifest, candidate, output_dir
            )
            updates = {key: value for key, value in scores.items() if key in missing}
            if set(missing) - updates.keys():
                raise CacheError("missing_required_scores")
            # Commit metrics only after all bindings and required scores validate.
            complexes = output_dir / "recovered_complexes"
            complexes.mkdir(exist_ok=True)
            name = digest(candidate["id"].encode())[:ARTIFACT_ID_HEX_LENGTH] + (
                ".pdb" if format == "pdb" else ".cif"
            )
            path = complexes / name
            path.write_text(structure)
            candidate["scores"].update(updates)
            candidate.setdefault("artifacts", {})["complex"] = str(
                path.relative_to(output_dir)
            )
            candidate["score_provenance"] = dict(binding)
            candidate["cache_status"] = "recovered"
            candidate.pop("cache_reason", None)
        except (
            CacheError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            OSError,
            AttributeError,
            InvalidFileError,
        ) as exc:
            candidate["cache_status"] = "blocked"
            candidate["cache_reason"] = str(exc)
    return export_run(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = recover(args.manifest, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Cache recovery failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
