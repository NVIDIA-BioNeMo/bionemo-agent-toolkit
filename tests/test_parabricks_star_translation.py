# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""STAR migration regressions: data preservation, unresolved semantics, CLI I/O."""

import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "library-skills" / "parabricks"
          / "scripts" / "translate_star_to_parabricks.py")
spec = importlib.util.spec_from_file_location("star_translation", SCRIPT)
translation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translation)


def request(extra=(), **kwargs):
    return {"version": "4.7.0", "ref": "/ref/genome.fa", "output_dir": "/results/star",
            "out_bam": "/results/final.bam",
            "star_args": ["STAR", "--genomeDir", "/ref/star", "--readFilesIn",
                          "L1_R1.gz,L2_R1.gz", "L1_R2.gz,L2_R2.gz",
                          "--outSAMattrRGline", "ID:L1", "SM:sample", "PU:unit1", ",",
                          "ID:L2", "SM:sample", "PU:unit2",
                          "--outSAMtype", "BAM", "SortedByCoordinate", *extra], **kwargs}


def option_values(argv):
    options = {}
    current = None
    for value in argv[2:]:
        if value.startswith("--"):
            current = value
            options.setdefault(current, []).append([])
        else:
            options[current][-1].append(value)
    return options


class TranslationTests(unittest.TestCase):
    def test_pairs_metadata_required_outputs_and_default_marking(self):
        result = translation.translate(request())
        self.assertEqual(result["status"], "draft")
        options = option_values(result["draft_argv"])
        self.assertEqual(options["--in-fq"], [
            ["L1_R1.gz", "L1_R2.gz", "@RG\\tID:L1\\tSM:sample\\tPU:unit1"],
            ["L2_R1.gz", "L2_R2.gz", "@RG\\tID:L2\\tSM:sample\\tPU:unit2"],
        ])
        for flag, value in [("--ref", "/ref/genome.fa"), ("--genome-lib-dir", "/ref/star"),
                            ("--output-dir", "/results/star"), ("--out-bam", "/results/final.bam")]:
            self.assertEqual(options[flag], [[value]])
        self.assertIn("--no-markdups", options)

    def test_single_end_and_shell_sensitive_paths_round_trip_without_execution(self):
        data = request()
        data["star_args"] = ["--genomeDir", "/ref/index with spaces", "--readFilesIn",
                             "reads/a $(touch should-not-exist).fq.gz", "--outSAMattrRGline",
                             "ID:a", "SM:patient 1", "DS:apostrophe's $literal", "--outSAMtype",
                             "BAM", "SortedByCoordinate"]
        result = translation.translate(data)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(shlex.split(result["command"]), result["draft_argv"])
        options = option_values(result["draft_argv"])
        self.assertNotIn("--in-fq", options)
        self.assertEqual(options["--in-se-fq"][0][0], "reads/a $(touch should-not-exist).fq.gz")
        self.assertIn("\\tSM:patient 1\\t", options["--in-se-fq"][0][1])

    def test_negative_vector_scores_and_chimera_multiword_form(self):
        result = translation.translate(request([
            "--alignSJstitchMismatchNmax", "0", "-1", "0", "0",
            "--chimScoreJunctionNonGTAG", "-1", "--chimSegmentMin", "15",
            "--chimOutType", "WithinBAM", "HardClip", "--runThreadN", "16",
            "--readFilesCommand", "zcat", "-c", "--outFileNamePrefix", "/old/location/S1.",
        ]))
        options = option_values(result["draft_argv"])
        self.assertEqual(options["--max-junction-mismatches"], [["0", "-1", "0", "0"]])
        self.assertEqual(options["--chim-score-non-gtag"], [["-1"]])
        self.assertEqual(options["--out-chim-type"], [["WithinBAM_HardClip"]])
        self.assertEqual(options["--read-files-command"], [["zcat -c"]])
        self.assertEqual(options["--out-prefix"], [["S1."]])
        self.assertNotIn("--num-threads", options)
        self.assertIn("workers per GPU stream", " ".join(result["notes"]))

    def test_already_quoted_decompressor_is_not_quoted_as_an_executable_name(self):
        result = translation.translate(request(["--readFilesCommand", "zcat -c"]))
        self.assertEqual(option_values(result["draft_argv"])["--read-files-command"], [["zcat -c"]])
        self.assertEqual(shlex.split(result["command"]), result["draft_argv"])

    def test_unmapped_record_contract_does_not_claim_all_unmapped_reads_disappear(self):
        result = translation.translate(request(["--outSAMunmapped", "Within", "KeepPairs",
                                                 "--outReadsUnmapped", "Fastx"]))
        self.assertEqual(result["status"], "needs_review")
        issues = " ".join(result["issues"])
        self.assertIn("for each alignment", issues)
        self.assertIn("ordinary unmapped-read inclusion remains possible", issues)
        self.assertIn("Fastx is not a replacement", issues)

    def test_unknown_options_remain_visible_and_block_equivalence_claim(self):
        result = translation.translate(request(["--outSAMprimaryFlag", "AllBestScore",
                                                 "--soloType", "CB_UMI_Simple"]))
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["untranslated"], [
            {"option": "--outSAMprimaryFlag", "values": ["AllBestScore"]},
            {"option": "--soloType", "values": ["CB_UMI_Simple"]},
        ])
        self.assertNotIn("AllBestScore", result["draft_argv"])

    def test_rejects_missing_outputs_unpaired_lanes_ambiguous_groups_and_other_versions(self):
        invalid = []
        for field in ("output_dir", "out_bam", "ref"):
            data = request()
            del data[field]
            invalid.append(data)
        data = request()
        data["version"] = "4.6.0"
        invalid.append(data)
        for tokens in (["--readFilesIn", "a,b", "c"],
                       ["--readFilesIn", "a,", "c,d"],
                       ["--readFilesIn", "a,b", "c,d", "--outSAMattrRGline", "ID:one"],
                       ["--readFilesIn", "a", "--outSAMattrRGline", "SM:s", "ID:one"],
                       ["--readFilesIn", "a", "--outSAMattrRGline", "ID:one", "SM:s", "SM:t"]):
            data = request()
            data["star_args"] = ["--genomeDir", "/ref/star", *tokens]
            invalid.append(data)
        invalid.extend([request(["--genomeDir", "/other"]),
                        request(["--runMode", "genomeGenerate"]),
                        request(["--alignSJstitchMismatchNmax", "0", "-1"])])
        for data in invalid:
            with self.subTest(data=data):
                result = translation.translate(data)
                self.assertEqual(result["status"], "invalid")
                self.assertIsNone(result["command"])
                self.assertIsNone(result["draft_argv"])

    def test_explicit_marking_request_is_a_disclosed_processing_change(self):
        result = translation.translate(request(mark_duplicates=True))
        self.assertEqual(result["status"], "needs_review")
        self.assertNotIn("--no-markdups", result["draft_argv"])
        self.assertIn("adds a processing step", " ".join(result["issues"]))

    def test_cli_batch_preserves_other_drafts_and_returns_failure_for_invalid_request(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run([sys.executable, str(SCRIPT), "--input", "-"],
                                     input=json.dumps([request(name="valid"), {"name": "invalid"}]),
                                     text=True, capture_output=True, cwd=directory, check=False)
            self.assertEqual(process.returncode, 2)
            results = json.loads(process.stdout)
            self.assertEqual([item["name"] for item in results], ["valid", "invalid"])
            self.assertEqual([item["status"] for item in results], ["draft", "invalid"])
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
