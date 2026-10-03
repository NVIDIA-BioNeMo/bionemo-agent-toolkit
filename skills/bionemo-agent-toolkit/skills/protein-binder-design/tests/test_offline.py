# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Execute offline workflows, then challenge the independent artifact verifier."""

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from offline_bookkeeping import run_fixture  # noqa: E402 - skill scripts are not an installed package
from pdb_utils import (  # noqa: E402 - skill scripts are not an installed package
    ca_coords,
    extract_chain,
    remap_to_seq_index,
    residue_index_map,
    sequence,
)
from refold_cache import digest, recover  # noqa: E402 - skill scripts are not an installed package

spec = importlib.util.spec_from_file_location(
    "artifact_grader", SKILL / "evals/grader.py"
)
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)
CASES = {
    case["id"]: case
    for case in json.loads((SKILL / "evals/evals.json").read_text())["evals"]
}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def prepare_target(workspace):
    """Exercise the public PDB helpers; grading uses independently pinned results."""
    source = workspace / "input/target_prep"
    request = json.loads((source / "request.json").read_text())
    text = (source / request["structure"]).read_text()
    chain = request["chain"]
    result = {
        "chain": chain,
        "sequence": sequence(text, chain),
        "author_to_sequence": residue_index_map(text, chain),
        "simulated": True,
        "live_inference": False,
        "requests": {},
    }
    for item in request["requests"]:
        missing = [r for r in item["hotspots"] if r not in result["author_to_sequence"]]
        if missing:
            result["requests"][item["id"]] = {
                "status": "blocked",
                "missing_author_residues": missing,
            }
        else:
            result["requests"][item["id"]] = {
                "status": "ready",
                "hotspot_res": [chain + r for r in item["hotspots"]],
                "sequence_indices": remap_to_seq_index(text, chain, item["hotspots"]),
            }
    output = workspace / "output/target-prep"
    output.mkdir(parents=True)
    (output / "target.pdb").write_text(extract_chain(text, chain))
    write_json(output / "preparation.json", result)


class OfflineWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def stage(self, case):
        for item in CASES[case]["files"]:
            source = SKILL / item
            destination = (
                self.workspace / "input" / source.relative_to(SKILL / "evals/files")
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)

    def execute(self, case):
        if case in grader.BOOKKEEPING:
            filename, destination, _ = grader.BOOKKEEPING[case]
            output = self.workspace / "output" / (destination or "bookkeeping")
            run_fixture(self.workspace / "input" / filename, output)
        elif case in grader.CACHE_CASES:
            for name in grader.CACHE_CASES[case]:
                destination = grader.CACHE_RUNS[name][0]
                recover(
                    self.workspace / "input" / name / "manifest.json",
                    self.workspace / "output" / destination,
                )
        else:
            prepare_target(self.workspace)

    def assert_grade(self, case, expected):
        result = grader.grade(case, self.workspace)
        failures = [
            c["message"]
            for c in result["details"]["artifact_correctness"]["checks"]
            if not c["passed"]
        ]
        self.assertEqual(
            result["custom_metrics"]["artifact_correctness"],
            expected,
            "\n".join(failures),
        )

    def test_all_cases_require_artifacts_and_pass_after_real_execution(self):
        for case in CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                self.workspace = Path(root)
                self.stage(case)
                before = {
                    p: digest(p.read_bytes())
                    for p in (self.workspace / "input").rglob("*")
                    if p.is_file()
                }
                self.assert_grade(case, 0)
                self.execute(case)
                self.assert_grade(case, 1)
                self.assertEqual(before, {p: digest(p.read_bytes()) for p in before})

    def test_original_scores_are_not_coerced_and_absent_keys_stay_absent(self):
        case = "offline-mixed-threshold-ranking"
        self.stage(case)
        self.execute(case)
        data = json.loads(
            (self.workspace / "output/mixed-thresholds/manifest.json").read_text()
        )
        rows = {c["id"]: c for c in data["candidates"]}
        self.assertEqual(rows["invalid_score"]["scores"]["iptm"], "0.95")
        self.assertNotIn("self_consistency_rmsd", rows["pending"]["scores"])
        self.assertFalse(rows["invalid_score"]["passed_filter"])

    def test_bookkeeping_verifier_accepts_equivalent_minimal_manifest(self):
        case = "offline-boltz2-ranking"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/boltz2-only/manifest.json"
        data = json.loads(path.read_text())
        # A baseline need not reproduce helper-specific timestamps or schema extras.
        minimal = {key: data[key] for key in ("target", "filters", "candidates")}
        minimal["rank_by"] = data["params"]["rank_by"]
        for candidate in minimal["candidates"]:
            for key in (
                "created",
                "backbone_id",
                "filter_metrics",
                "filter_exemptions",
                "passed_filter",
            ):
                candidate.pop(key, None)
        write_json(path, minimal)
        self.assert_grade(case, 1)

    def test_target_verifier_accepts_equivalent_pdb_writers(self):
        case = "offline-target-preparation"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/target-prep/target.pdb"
        atoms = [
            line for line in path.read_text().splitlines() if line.startswith("ATOM")
        ]
        rewritten = []
        for serial, line in enumerate(atoms, 101):
            # Change serials, atom-name alignment and numeric formatting; clear
            # altLoc after choosing B, and omit unused trailing PDB fields.
            xyz = "".join(
                f"{float(line[start : start + 8]):8.2f}" for start in (30, 38, 46)
            )
            rewritten.append(f"ATOM  {serial:5d} CA   {line[17:30]}{xyz}")
        for model_records in (False, True):
            with self.subTest(model_records=model_records):
                text = "\n".join(rewritten) + "\n"
                if model_records:
                    text = "MODEL        1\n" + text + "ENDMDL\n"
                path.write_text(text + "END\n")
                self.assert_grade(case, 1)

    def test_target_verifier_rejects_duplicate_conformers_and_wrong_structure(self):
        case = "offline-target-preparation"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/target-prep/target.pdb"
        atoms = [
            line for line in path.read_text().splitlines() if line.startswith("ATOM")
        ]
        source = (
            (self.workspace / "input/target_prep/target.pdb").read_text().splitlines()
        )
        alternative = next(
            line for line in source if line.startswith("ATOM") and line[16] == "A"
        )
        changed_serial = atoms[1][:6] + "  999" + atoms[1][11:]
        mutations = {
            "both conformers": atoms[:2] + [alternative] + atoms[2:],
            "same atom, new serial": atoms + [changed_serial],
            "wrong conformer": atoms[:1] + [alternative] + atoms[2:],
            "missing atom": atoms[:-1],
            "wrong chain": [atoms[0][:21] + "A" + atoms[0][22:]] + atoms[1:],
            "lost insertion code": atoms[:2]
            + [atoms[2][:26] + " " + atoms[2][27:]]
            + atoms[3:],
            "wrong residue": [atoms[0][:17] + "VAL" + atoms[0][20:]] + atoms[1:],
            "wrong coordinates": [atoms[0][:30] + "   1.000" + atoms[0][38:]]
            + atoms[1:],
            "non-finite coordinates": [atoms[0][:30] + "     nan" + atoms[0][38:]]
            + atoms[1:],
            "wrong order": list(reversed(atoms)),
            "second model": ["MODEL        2"] + atoms + ["ENDMDL"],
            "two models": ["MODEL        1"]
            + atoms
            + ["ENDMDL", "MODEL        2"]
            + atoms
            + ["ENDMDL"],
            "outside model": ["MODEL        1"] + atoms + ["ENDMDL", atoms[0]],
        }
        for name, lines in mutations.items():
            with self.subTest(name=name):
                path.write_text("\n".join(lines) + "\nEND\n")
                self.assert_grade(case, 0)

    def test_csv_mutations_are_rejected_even_with_correct_manifest_and_summary(self):
        case = "offline-boltz2-ranking"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/boltz2-only/candidates.csv"
        original = path.read_text()
        lines = original.splitlines(keepends=True)
        for text in (
            lines[0],
            lines[0] + "".join(reversed(lines[1:])),
            original.replace("0.89", "0.99"),
            original + lines[1],
        ):
            with self.subTest(text=text):
                path.write_text(text)
                self.assert_grade(case, 0)
        path.write_text(original)
        self.assert_grade(case, 1)

    def test_empty_rank_must_be_a_header_only_file(self):
        case = "offline-empty-ranking"
        self.stage(case)
        self.execute(case)
        root = self.workspace / "output/no-survivors"
        shutil.copy2(root / "all_candidates.csv", root / "candidates.csv")
        self.assert_grade(case, 0)

    def test_agent_cannot_redefine_fixture_truth(self):
        case = "offline-manifest"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "input/bookkeeping.json"
        path.write_text(path.read_text().replace('"iptm_min": 0.8', '"iptm_min": 0.1'))
        self.assert_grade(case, 0)

    def test_supplied_score_preservation_is_exact(self):
        case = "offline-boltz2-ranking"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/boltz2-only/manifest.json"
        data = json.loads(path.read_text())
        data["candidates"][0]["scores"]["boltz2_confidence"] += 1e-9
        write_json(path, data)
        self.assert_grade(case, 0)

    def test_resume_preserves_finite_low_scores_and_only_fills_missing_metrics(self):
        case = "offline-cache-resume"
        self.stage(case)
        self.execute(case)
        data = json.loads((self.workspace / "output/resumed/manifest.json").read_text())
        rows = {c["id"]: c for c in data["candidates"]}
        self.assertEqual(rows["below"]["cache_status"], "complete")
        self.assertEqual(rows["recoverable"]["scores"]["iptm"], 0.86)
        self.assertAlmostEqual(
            rows["recoverable"]["scores"]["binder_plddt"], 84, places=5
        )
        self.assertAlmostEqual(
            rows["recoverable"]["scores"]["self_consistency_rmsd"], 0, places=6
        )
        self.assertEqual(
            rows["failed"]["failure_reason"], "HTTP 503: retries exhausted"
        )
        self.assertEqual(rows["missing"]["scores"], {})

    def test_recovered_scores_and_provenance_are_checked_independently(self):
        case = "offline-cache-resume"
        self.stage(case)
        self.execute(case)
        path = self.workspace / "output/resumed/manifest.json"
        original = json.loads(path.read_text())
        for kind in ("old_score", "sample", "failure", "reason", "decision"):
            data = copy.deepcopy(original)
            rows = {c["id"]: c for c in data["candidates"]}
            if kind == "old_score":
                rows["recoverable"]["scores"]["iptm"] = 0.98
            elif kind == "sample":
                rows["recoverable"]["score_provenance"]["sample_index"] = 1
            elif kind == "failure":
                rows["failed"].pop("failure_reason")
            elif kind == "reason":
                rows["missing"]["cache_reason"] = "unknown"
            else:
                rows["below"]["cache_status"] = "blocked"
            write_json(path, data)
            with self.subTest(kind=kind):
                self.assert_grade(case, 0)

    def test_saved_selected_complex_bytes_are_checked(self):
        case = "offline-refold-extraction"
        self.stage(case)
        self.execute(case)
        root = self.workspace / "output/raw-refolds/boltz2"
        data = json.loads((root / "manifest.json").read_text())
        row = next(c for c in data["candidates"] if c["id"] == "selected")
        path = root / row["artifacts"]["complex"]
        path.write_text(path.read_text() + "# changed\n")
        self.assert_grade(case, 0)

    def test_all_provenance_mismatches_block_import(self):
        case = "offline-provenance-rejection"
        self.stage(case)
        self.execute(case)
        data = json.loads(
            (self.workspace / "output/provenance/manifest.json").read_text()
        )
        for candidate in data["candidates"]:
            if candidate["id"] != "valid":
                self.assertEqual(candidate["cache_status"], "blocked")
                self.assertEqual(candidate["scores"], {})
                self.assertNotIn("score_provenance", candidate)

    def test_invalid_sample_index_is_blocked_without_importing_partial_scores(self):
        case = "offline-refold-extraction"
        self.stage(case)
        path = self.workspace / "input/raw_refolds/boltz2/manifest.json"
        original = json.loads(path.read_text())
        for index in (-1, True, 10):
            data = copy.deepcopy(original)
            data["candidates"][0]["prediction"]["sample_index"] = index
            write_json(path, data)
            output = self.workspace / str(index)
            recover(path, output)
            result = json.loads((output / "manifest.json").read_text())["candidates"][0]
            self.assertEqual(result["cache_reason"], "invalid_sample_index")
            self.assertEqual(result["scores"], {})

    def test_existing_output_is_not_overwritten(self):
        case = "offline-cache-resume"
        self.stage(case)
        self.execute(case)
        with self.assertRaises(FileExistsError):
            self.execute(case)
        output = self.workspace / "output/resumed/manifest.json"
        self.assertTrue(output.is_file())

    def test_bookkeeping_validates_all_profiles_before_writing(self):
        source = self.workspace / "fixture.json"
        fixture = json.loads((SKILL / "evals/files/bookkeeping.json").read_text())
        fixture["profiles"][1]["filters"]["binder_plddt_min"] = "80"
        write_json(source, fixture)
        output = self.workspace / "output"
        with self.assertRaisesRegex(ValueError, "finite numbers"):
            run_fixture(source, output)
        self.assertFalse(output.exists())

    def test_real_campaign_is_not_relabelled_as_synthetic(self):
        case = "offline-cache-resume"
        self.stage(case)
        path = self.workspace / "input/resume_cache/manifest.json"
        data = json.loads(path.read_text())
        data["mode"] = "hosted"
        write_json(path, data)
        with self.assertRaisesRegex(ValueError, "synthetic"):
            self.execute(case)
        self.assertFalse((self.workspace / "output/resumed").exists())

    def test_malformed_structure_blocks_one_candidate_and_continues(self):
        case = "offline-refold-extraction"
        self.stage(case)
        root = self.workspace / "input/raw_refolds/openfold3"
        manifest = json.loads((root / "manifest.json").read_text())
        candidate = manifest["candidates"][0]
        path = root / candidate["prediction"]["response"]["path"]
        data = json.loads(path.read_text())
        data["outputs"][0]["structures_with_scores"][1]["structure"] = "not a PDB"
        write_json(path, data)
        candidate["prediction"]["response"]["sha256"] = digest(path.read_bytes())
        candidate["prediction"]["complex_sha256"] = digest(b"not a PDB")
        write_json(root / "manifest.json", manifest)
        recover(root / "manifest.json", self.workspace / "output/broken")
        result = json.loads(
            (self.workspace / "output/broken/manifest.json").read_text()
        )
        self.assertEqual(result["candidates"][0]["cache_status"], "blocked")
        self.assertEqual(result["candidates"][0]["scores"], {})
        self.assertEqual(result["candidates"][2]["cache_status"], "recovered")

    def test_standalone_grader_runs_with_only_grader_and_entry_files(self):
        case = "offline-boltz2-ranking"
        self.stage(case)
        self.execute(case)
        tests, verifier = self.workspace / "tests", self.workspace / "verifier"
        tests.mkdir()
        shutil.copy2(SKILL / "evals/grader.py", tests / "grader.py")
        write_json(tests / "entry.json", {"id": case})
        env = {
            **os.environ,
            "HARBOR_TESTS_DIR": str(tests),
            "HARBOR_VERIFIER_DIR": str(verifier),
            "BINDER_EVAL_WORKSPACE": str(self.workspace),
        }
        subprocess.run(
            [sys.executable, "-I", str(tests / "grader.py")], env=env, check=True
        )
        self.assertEqual(
            json.loads((verifier / "reward.json").read_text())["custom_metrics"],
            {"artifact_correctness": 1.0},
        )


class TargetMappingTests(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / "evals/files/target_prep/target.pdb").read_text()

    def test_insertion_residue_does_not_overwrite_bare_author_number(self):
        self.assertEqual(
            residue_index_map(self.text, "E"), {"10": 1, "42": 2, "42A": 3, "77": 4}
        )
        self.assertEqual(remap_to_seq_index(self.text, "E", [42, "42A", 77]), [2, 3, 4])
        with self.assertRaises(KeyError):
            remap_to_seq_index(self.text, "E", [43])

    def test_first_model_and_highest_occupancy_altloc_only(self):
        self.assertEqual(sequence(self.text, "E"), "AGST")
        self.assertEqual(
            ca_coords(self.text, "E"), [(0, 0, 0), (4, 0, 0), (4, 3, 0), (8, 3, 0)]
        )
        self.assertNotIn("VAL", extract_chain(self.text, "E"))
        saved_ca = [
            line
            for line in extract_chain(self.text, "E").splitlines()
            if line[12:16].strip() == "CA"
        ]
        self.assertEqual(len(saved_ca), 4)
        self.assertEqual(saved_ca[1][16], "B")

    def test_overlapping_author_numbers_require_explicit_chain(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            residue_index_map(self.text)


if __name__ == "__main__":
    unittest.main()
