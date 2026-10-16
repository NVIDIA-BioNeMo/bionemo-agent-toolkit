#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Standalone artifact verifier; no agent helper imports, network or LLM calls.

Harbor copies only this file to /tests. Input digests below pin the fixture truth;
an agent cannot change that truth by editing its input copies. ACES plus custom
keeps the ACES headline score: artifact_correctness is a separate binary metric.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path


BOOKKEEPING = {
    "offline-manifest": ("bookkeeping.json", None, ["best", "boundary"]),
    "offline-boltz2-ranking": (
        "boltz2_only.json",
        "boltz2-only",
        ["binder_a", "binder_b"],
    ),
    "offline-mixed-threshold-ranking": (
        "mixed_thresholds.json",
        "mixed-thresholds",
        ["binder_a", "binder_b"],
    ),
    "offline-empty-ranking": ("no_survivors.json", "no-survivors", []),
}
# Hand-calculated outcomes, independent of the campaign helper and its parser.
CACHE_RUNS = {
    "raw_refolds/boltz2": (
        "raw-refolds/boltz2",
        ["selected"],
        {
            "selected": (
                {"boltz2_confidence": 0.81, "binder_plddt": 82},
                "recovered",
                None,
            ),
            "poor_binder": (
                {"boltz2_confidence": 0.99, "binder_plddt": 60},
                "recovered",
                None,
            ),
            "incomplete": ({}, "blocked", "binder_length_mismatch"),
            "control": (
                {"boltz2_confidence": 0.999, "binder_plddt": 99},
                "recovered",
                None,
            ),
        },
    ),
    "raw_refolds/openfold3": (
        "raw-refolds/openfold3",
        ["selected"],
        {
            "selected": ({"iptm": 0.83, "binder_plddt": 86}, "recovered", None),
            "composite_only": ({}, "blocked", "missing_required_scores"),
            "poor_binder": ({"iptm": 0.99, "binder_plddt": 60}, "recovered", None),
        },
    ),
    "resume_cache": (
        "resumed",
        ["done", "recoverable"],
        {
            "done": (
                {"iptm": 0.9, "binder_plddt": 90, "self_consistency_rmsd": 0},
                "complete",
                None,
            ),
            "below": (
                {"iptm": 0.7, "binder_plddt": 85, "self_consistency_rmsd": 0},
                "complete",
                None,
            ),
            "recoverable": (
                {"iptm": 0.86, "binder_plddt": 84, "self_consistency_rmsd": 0},
                "recovered",
                None,
            ),
            "missing": ({}, "blocked", "missing_artifact"),
            "failed": ({}, "blocked", "missing_prediction"),
            "control": ({"iptm": 0.99, "binder_plddt": 88}, "complete", None),
        },
    ),
    "provenance_cache": (
        "provenance",
        ["valid"],
        {
            "valid": (
                {"boltz2_confidence": 0.9, "binder_plddt": 84},
                "recovered",
                None,
            ),
            "candidate_swap": ({}, "blocked", "candidate_mismatch"),
            "target_swap": ({}, "blocked", "target_mismatch"),
            "sequence_swap": ({}, "blocked", "sequence_mismatch"),
            "sample_swap": ({}, "blocked", "sample_digest_mismatch"),
            "response_tampered": ({}, "blocked", "artifact_digest_mismatch"),
        },
    ),
}
CACHE_CASES = {
    "offline-refold-extraction": ["raw_refolds/boltz2", "raw_refolds/openfold3"],
    "offline-cache-resume": ["resume_cache"],
    "offline-provenance-rejection": ["provenance_cache"],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def same(actual, expected, *, approximate=False):
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(
                same(actual[k], v, approximate=approximate) for k, v in expected.items()
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                same(a, e, approximate=approximate) for a, e in zip(actual, expected)
            )
        )
    if numeric(expected):
        return numeric(actual) and (
            math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-6)
            if approximate
            else actual == expected
        )
    return type(actual) is type(expected) and actual == expected


def read_json(path):
    return json.loads(Path(path).read_text())


def metrics(candidate, filters):
    required = {}
    for key, value in filters.items():
        if value is None:
            continue
        metric, direction = key.rsplit("_", 1)
        if (
            metric == "self_consistency_rmsd"
            and candidate.get("is_control")
            and not candidate.get("artifacts", {}).get("backbone_pdb")
        ):
            continue
        required[metric] = (direction, value)
    return required


def passes(candidate, filters):
    required = metrics(candidate, filters)
    for key, (direction, cutoff) in required.items():
        value = candidate["scores"].get(key)
        if not numeric(value) or (
            value < cutoff if direction == "min" else value > cutoff
        ):
            return False
    return bool(required)


def check_csv(path, expected, ids, check, *, ordered, approximate=False):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        headers = reader.fieldnames or []
    check(bool(headers) and "id" in headers, f"{path}: CSV header")
    actual_ids = [row.get("id") for row in rows]
    check(
        actual_ids == ids if ordered else sorted(actual_ids) == sorted(ids),
        f"{path}: candidate IDs",
    )
    lookup = {c["id"]: c for c in expected}
    score_keys = {key for c in expected for key in c["scores"]}
    check(score_keys.issubset(headers), f"{path}: supplied score columns")
    if "iptm" not in score_keys:
        check(
            "iptm" not in [key.lower() for key in headers],
            f"{path}: absent ipTM stays absent",
        )
    for row in rows:
        if row.get("id") not in lookup:
            continue
        candidate = lookup[row["id"]]
        for key in score_keys:
            expected_value, actual = candidate["scores"].get(key), row.get(key)
            if expected_value is None:
                ok = actual == ""
            elif numeric(expected_value):
                try:
                    ok = same(float(actual), expected_value, approximate=approximate)
                except (ValueError, TypeError):
                    ok = False
            else:
                ok = actual == str(expected_value)
            check(ok, f"{path}: {row['id']}.{key}")
        if "is_control" in headers:
            check(
                str(row["is_control"]).lower()
                == str(candidate.get("is_control", False)).lower(),
                f"{path}: {row['id']} control flag",
            )


def verify_run(path, source, expected, ranked_ids, check, *, cache=False):
    data = read_json(path / "manifest.json")
    check(same(data.get("target"), source["target"]), f"{path}: target")
    check(same(data.get("filters"), source["filters"]), f"{path}: filters")
    rank_by = data.get("params", {}).get("rank_by", data.get("rank_by"))
    check(rank_by == source["params"]["rank_by"], f"{path}: rank metric")
    actual = data.get("candidates", [])
    check(
        sorted(c["id"] for c in actual) == sorted(c["id"] for c in expected),
        f"{path}: complete manifest",
    )
    lookup = {c["id"]: c for c in actual}
    for candidate in expected:
        cid = candidate["id"]
        record = lookup.get(cid, {})
        check(
            same(record.get("scores"), candidate["scores"], approximate=cache),
            f"{path}: {cid} score values/types/absence",
        )
        check(
            record.get("is_control", False) is candidate.get("is_control", False),
            f"{path}: {cid} control flag",
        )
        check(
            record.get("control_type") == candidate.get("control_type"),
            f"{path}: {cid} control type",
        )
        for flag in ("passed_filter", "passed"):
            if flag in record:
                check(
                    record[flag] is passes(candidate, source["filters"]),
                    f"{path}: {cid} filter status",
                )
    check_csv(
        path / "all_candidates.csv",
        expected,
        [c["id"] for c in expected],
        check,
        ordered=False,
        approximate=cache,
    )
    # Older prompts used the ambiguous phrase "ranked candidates.csv". Accept
    # the three literal interpretations without changing historical prompts.
    alternatives = [
        path / name
        for name in ("candidates.csv", "ranked candidates.csv", "ranked_candidates.csv")
    ]
    ranked_paths = [p for p in alternatives if p.exists()]
    check(bool(ranked_paths), f"{path}: ranked CSV exists")
    if cache:
        check((path / "candidates.csv").exists(), f"{path}: required candidates.csv")
    for ranked_path in ranked_paths:
        check_csv(
            ranked_path, expected, ranked_ids, check, ordered=True, approximate=cache
        )
    return data, lookup


def find_manifests(workspace):
    for root, dirs, names in os.walk(workspace):
        dirs[:] = [
            d
            for d in dirs
            if d not in {"input", "skills", "node_modules"} and not d.startswith(".")
        ]
        if "manifest.json" in names:
            yield Path(root)


def verify_bookkeeping(entry_id, workspace, check):
    filename, destination, ranked = BOOKKEEPING[entry_id]
    fixture = read_json(workspace / "input" / filename)
    for profile in fixture["profiles"]:
        source = {
            "target": fixture["target"],
            "filters": profile["filters"],
            "params": {"rank_by": profile["rank_by"]},
        }
        paths = (
            [workspace / "output" / destination]
            if destination
            else list(find_manifests(workspace))
        )
        attempts = []
        for path in paths:
            checks = []
            try:
                data = read_json(path / "manifest.json")
                if (
                    data.get("params", {}).get("rank_by", data.get("rank_by"))
                    != profile["rank_by"]
                ):
                    continue
                verify_run(
                    path,
                    source,
                    profile["candidates"],
                    ranked,
                    lambda ok, msg: checks.append((ok, msg)),
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                checks.append((False, f"{path}: {type(exc).__name__}: {exc}"))
            attempts.append(checks)
        valid = next((a for a in attempts if a and all(ok for ok, _ in a)), None)
        chosen = (
            valid
            if valid is not None
            else (
                max(attempts, key=lambda a: sum(ok for ok, _ in a)) if attempts else []
            )
        )
        check(bool(chosen), f"{profile['name']}: output manifest found")
        for ok, msg in chosen:
            check(ok, msg)


def verify_cache(name, workspace, check):
    destination, ranked, outcomes = CACHE_RUNS[name]
    source_root, output = workspace / "input" / name, workspace / "output" / destination
    source = read_json(source_root / "manifest.json")
    expected = [{**c, "scores": outcomes[c["id"]][0]} for c in source["candidates"]]
    data, lookup = verify_run(output, source, expected, ranked, check, cache=True)
    check(
        same(data.get("params"), source["params"]), f"{output}: complete saved params"
    )
    check(
        same(data.get("stages", [])[: len(source["stages"])], source["stages"]),
        f"{output}: stage history",
    )
    for original in source["candidates"]:
        cid = original["id"]
        actual = lookup.get(cid, {})
        _, status, reason = outcomes[cid]
        check(actual.get("cache_status") == status, f"{output}: {cid} decision")
        if reason:
            check(
                actual.get("cache_reason") == reason,
                f"{output}: {cid} rejection reason",
            )
        for key, value in original.items():
            if key not in {"scores", "artifacts"}:
                check(same(actual.get(key), value), f"{output}: {cid} preserves {key}")
        for key, value in original["scores"].items():
            check(
                same(actual.get("scores", {}).get(key), value),
                f"{output}: {cid} preserves score {key}",
            )
        for key, value in original.get("artifacts", {}).items():
            check(
                actual.get("artifacts", {}).get(key) == value,
                f"{output}: {cid} preserves artifact {key}",
            )
        if status == "recovered":
            binding = original["prediction"]
            check(
                same(actual.get("score_provenance"), binding),
                f"{output}: {cid} score provenance",
            )
            complex_path = (
                output / actual.get("artifacts", {}).get("complex", "")
            ).resolve()
            check(
                complex_path.is_relative_to(output.resolve())
                and complex_path.is_file()
                and sha(complex_path) == binding["complex_sha256"],
                f"{output}: {cid} saved selected complex",
            )
    # Saved evidence is copied without changing bytes, even when it is rejected.
    for rel, digest in INPUT_HASHES.items():
        prefix = name + "/"
        if rel.startswith(prefix) and rel[len(prefix) :] not in {
            "manifest.json",
            "candidates.csv",
        }:
            path = output / rel[len(prefix) :]
            check(
                path.is_file() and sha(path) == digest,
                f"{path}: preserved evidence bytes",
            )
    summary = read_json(output / "summary.json")
    missing = {
        c["id"]: [
            key
            for key in metrics(c, source["filters"])
            if not numeric(c["scores"].get(key))
        ]
        for c in expected
    }
    missing = {key: value for key, value in missing.items() if value}
    required_summary = {
        "n_candidates": sum(not c.get("is_control", False) for c in expected),
        "n_passed": len(ranked),
        "n_controls": sum(c.get("is_control", False) for c in expected),
        "ranked_ids": ranked,
        "passing_fraction_provisional": True,
        "live_inference": False,
    }
    for key, value in required_summary.items():
        check(same(summary.get(key), value), f"{output}: summary {key}")
    actual_missing = summary.get("missing_scores", {})
    check(
        isinstance(actual_missing, dict)
        and {k: sorted(v) for k, v in actual_missing.items()}
        == {k: sorted(v) for k, v in missing.items()},
        f"{output}: missing scores disclosure",
    )
    check(
        "simulated" in str(summary.get("label", "")).lower(),
        f"{output}: simulation label",
    )


def target_atoms(text):
    """Read structural fields without depending on PDB writer formatting."""
    atoms = {}
    explicit_model = False
    in_model = False
    ended = False
    for line in text.splitlines():
        record = line[:6].strip()
        if record == "MODEL":
            if explicit_model or atoms or ended or int(line[10:14]) != 1:
                raise ValueError("target must contain only the first model")
            explicit_model = in_model = True
        elif record == "ENDMDL":
            if not in_model:
                raise ValueError("unexpected ENDMDL in target")
            in_model = False
        elif record == "END":
            ended = True
        elif record in {"ATOM", "HETATM"}:
            if ended or (explicit_model and not in_model):
                raise ValueError("target atom outside its model")
            key = (line[21], int(line[22:26]), line[26].strip(), line[12:16].strip())
            if key in atoms:
                raise ValueError(f"duplicate target atom/conformer: {key}")
            coordinates = tuple(
                float(line[start : start + 8]) for start in (30, 38, 46)
            )
            if not all(math.isfinite(value) for value in coordinates):
                raise ValueError("non-finite target coordinates")
            atoms[key] = (line[17:20].strip(), line[16].strip(), coordinates)
    if in_model:
        raise ValueError("unclosed target model")
    return atoms


def verify_target(workspace, check):
    root = workspace / "output/target-prep"
    data = read_json(root / "preparation.json")
    expected = {
        "chain": "E",
        "sequence": "AGST",
        "author_to_sequence": {"10": 1, "42": 2, "42A": 3, "77": 4},
        "simulated": True,
        "live_inference": False,
    }
    for key, value in expected.items():
        check(same(data.get(key), value), f"target preparation: {key}")
    requests = data.get("requests", {})
    present, absent = requests.get("present", {}), requests.get("missing", {})
    check(
        present.get("status") == "ready"
        and present.get("hotspot_res") == ["E42", "E77"]
        and same(present.get("sequence_indices"), [2, 4]),
        "present hotspot handoff",
    )
    check(
        absent.get("status") == "blocked"
        and absent.get("missing_author_residues") == ["43"]
        and not absent.get("hotspot_res")
        and not absent.get("sequence_indices"),
        "missing hotspot blocks its request",
    )
    atoms = target_atoms((root / "target.pdb").read_text())
    # Hand-checked first-model atoms from the digest-pinned synthetic input.
    expected_atoms = {
        ("E", 10, "", "CA"): ("ALA", "", (0.0, 0.0, 0.0)),
        ("E", 42, "", "CA"): ("GLY", "B", (4.0, 0.0, 0.0)),
        ("E", 42, "A", "CA"): ("SER", "", (4.0, 3.0, 0.0)),
        ("E", 77, "", "CA"): ("THR", "", (8.0, 3.0, 0.0)),
    }
    check(
        list(atoms) == list(expected_atoms)
        and all(
            atoms[key][0] == residue
            # Writers may clear altLoc after selecting the required conformer.
            and atoms[key][1] in {"", altloc}
            and all(
                math.isclose(actual, expected, rel_tol=0, abs_tol=0.0005)
                for actual, expected in zip(atoms[key][2], coordinates)
            )
            for key, (residue, altloc, coordinates) in expected_atoms.items()
        ),
        "extracted PDB chain/model/author numbering/selected coordinates",
    )


def grade(entry_id, workspace):
    workspace = Path(workspace)
    checks = []

    def check(ok, message):
        checks.append({"passed": bool(ok), "message": message})

    if entry_id in BOOKKEEPING:
        prefixes = [BOOKKEEPING[entry_id][0]]
    elif entry_id in CACHE_CASES:
        prefixes = [name + "/" for name in CACHE_CASES[entry_id]] + [
            "cache_contract.md"
        ]
    elif entry_id == "offline-target-preparation":
        prefixes = ["target_prep/"]
    else:
        prefixes = []
        check(False, f"unknown case: {entry_id}")
    for rel, digest in INPUT_HASHES.items():
        if any(
            rel == prefix or (prefix.endswith("/") and rel.startswith(prefix))
            for prefix in prefixes
        ):
            path = workspace / "input" / rel
            check(path.is_file() and sha(path) == digest, f"immutable fixture: {rel}")
    if checks and all(item["passed"] for item in checks):
        try:
            if entry_id in BOOKKEEPING:
                verify_bookkeeping(entry_id, workspace, check)
            elif entry_id in CACHE_CASES:
                for name in CACHE_CASES[entry_id]:
                    verify_cache(name, workspace, check)
            else:
                verify_target(workspace, check)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            check(
                False, f"artifact read/validation failed: {type(exc).__name__}: {exc}"
            )
    passed = bool(checks) and all(item["passed"] for item in checks)
    return {
        "overall": float(passed),
        "custom_metrics": {"artifact_correctness": float(passed)},
        "details": {
            "artifact_correctness": {
                "passed": passed,
                "checks": checks,
                "scope": "saved artifacts only; no proof of live inference or save/reload execution",
            }
        },
    }


def main():
    tests = Path(os.environ.get("HARBOR_TESTS_DIR", "/tests"))
    verifier = Path(os.environ.get("HARBOR_VERIFIER_DIR", "/logs/verifier"))
    entry = read_json(tests / "entry.json")
    result = grade(
        entry["id"], Path(os.environ.get("BINDER_EVAL_WORKSPACE", "/workspace"))
    )
    verifier.mkdir(parents=True, exist_ok=True)
    Path(
        os.environ.get("HARBOR_REWARD_JSON", str(verifier / "reward.json"))
    ).write_text(json.dumps(result, indent=2) + "\n")


# INPUT_HASHES is pinned below, outside the agent's mutable /workspace/input.
INPUT_HASHES = {
    "boltz2_only.json": "c7b760c45bb2950f59c277eb08587789d8b945f03ca12f0d5407aa147e74ee59",
    "bookkeeping.json": "23a769f5f3f02c96c6758eb3b5787b99befbe69b898a64f170fe416c24a80fd3",
    "cache_contract.md": "24744e774ff688963bf99b540c7cfd9c525b8c870b2ce863cf298a210262edb6",
    "mixed_thresholds.json": "fcc5b8aa40870a1fb0e9deb4362a60996fc155121f21365bb1640aae97ae5420",
    "no_survivors.json": "2bfde692731de2850bee4f126dcc2c75cbd4e0b7eb97b1bbaa9566ea077f3022",
    "provenance_cache/backbone.pdb": "217f6524bd2ce0e9ddac2cf44fc2c3ef091768bf8539f269be520f4fad5de764",
    "provenance_cache/manifest.json": "5f08e89bd297f0c42e8e5302353a03d31f8e885c87178c807c938f4568c622cc",
    "provenance_cache/responses/candidate_swap.json": "b7529dacb3c5123b550074006b88536e17ead761ddb79b71d12c4a8a7bbf3d89",
    "provenance_cache/responses/response_tampered.json": "7943c5202ba623e735fafa2d2661810171ada09095bed9038d0a06f9232eda76",
    "provenance_cache/responses/sample_swap.json": "b7529dacb3c5123b550074006b88536e17ead761ddb79b71d12c4a8a7bbf3d89",
    "provenance_cache/responses/sequence_swap.json": "b7529dacb3c5123b550074006b88536e17ead761ddb79b71d12c4a8a7bbf3d89",
    "provenance_cache/responses/target_swap.json": "b7529dacb3c5123b550074006b88536e17ead761ddb79b71d12c4a8a7bbf3d89",
    "provenance_cache/responses/valid.json": "b7529dacb3c5123b550074006b88536e17ead761ddb79b71d12c4a8a7bbf3d89",
    "provenance_cache/target.pdb": "c8d7a6f455e0a524ec91d0689377243becb1f9395b5d83d51fc7089c091f9d10",
    "raw_refolds/boltz2/backbone.pdb": "217f6524bd2ce0e9ddac2cf44fc2c3ef091768bf8539f269be520f4fad5de764",
    "raw_refolds/boltz2/manifest.json": "b2666564b055d96269d619d6c0b6fe33229878fa5625342c567444d99d243055",
    "raw_refolds/boltz2/responses/control.json": "d3b2430f50a5e20c5af3d4b11cdc5a2d59c7717d342fedef98220e8fbd5d5ae5",
    "raw_refolds/boltz2/responses/incomplete.json": "c23989c01579afb22e2321e24c0b10daea5ad1357cca6af74146678d5d9d9f11",
    "raw_refolds/boltz2/responses/poor_binder.json": "45049bc8801df9bf9b763ec0e4539f6ce0f4828f287c326e1b657e006c084339",
    "raw_refolds/boltz2/responses/selected.json": "fb0fc1994076830ceeea1d8dd2d40485a6e8658b22ff289a9e676bb480c53a2c",
    "raw_refolds/boltz2/target.pdb": "c8d7a6f455e0a524ec91d0689377243becb1f9395b5d83d51fc7089c091f9d10",
    "raw_refolds/openfold3/backbone.pdb": "217f6524bd2ce0e9ddac2cf44fc2c3ef091768bf8539f269be520f4fad5de764",
    "raw_refolds/openfold3/manifest.json": "c1080b79c08db16a76ec89cf754f5d859fbb9ee0e18fee74249e49151990f06a",
    "raw_refolds/openfold3/responses/composite_only.json": "5123c9b20050bc54cdb559537b2ffc32d3d630d8683af02746bad5a234a133c4",
    "raw_refolds/openfold3/responses/poor_binder.json": "119c9a8719156a0d169d9258bc52dabe4ad497fffdfa0ab0c3497bc1dec32fb1",
    "raw_refolds/openfold3/responses/selected.json": "605dd0759e2642108810f6a88baef0f12427a86f2e5acfe3349f19d9a4b7399b",
    "raw_refolds/openfold3/target.pdb": "c8d7a6f455e0a524ec91d0689377243becb1f9395b5d83d51fc7089c091f9d10",
    "resume_cache/backbone.pdb": "217f6524bd2ce0e9ddac2cf44fc2c3ef091768bf8539f269be520f4fad5de764",
    "resume_cache/below.pdb": "038c31607d7610be18bf20022f25adb00866733c70d26d372458d7d73e516b86",
    "resume_cache/candidates.csv": "0d4f8840021deaf5107cb8eb02577acd1db45f26b8cb4ae043a6f0957db32f0e",
    "resume_cache/done.pdb": "038c31607d7610be18bf20022f25adb00866733c70d26d372458d7d73e516b86",
    "resume_cache/manifest.json": "35a9958917c527b27fdb679df481aaa34b7a0f4bd59ef6ec5219752be08bf119",
    "resume_cache/responses/below.json": "9486ff3d9be5100cacbf77d25a604c27db8caa89e3ee82d161056138ae45db0c",
    "resume_cache/responses/control.json": "7c074850d88c42357c6983784e8c7d28dcc14fa728dc3b9ea278ee0167b14b94",
    "resume_cache/responses/done.json": "94b16fe78c2cea20d2f2179d1a763feb98ec9de71e0222825cb2cc4bd1f1669f",
    "resume_cache/responses/recoverable.json": "214ee2ae319ad54656a6a3406ecacc571bee992c178881d61199d35c9f8d81af",
    "resume_cache/target.pdb": "c8d7a6f455e0a524ec91d0689377243becb1f9395b5d83d51fc7089c091f9d10",
    "target_prep/CONTRACT.md": "886e330fa4562df5029c874418a92bf108ec12331b69e16506f57d9ed9e7382b",
    "target_prep/request.json": "d8d0c7e0e92d0c18a1a493a4853f0e7e1718be9bb30c2cbd44c9410747652298",
    "target_prep/target.pdb": "6ef9dfdb6bf827b336d34aa768c36ed238581d365fab228ac2452ed0e019ca45",
}


if __name__ == "__main__":
    main()
