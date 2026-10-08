#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Draft Parabricks 4.7.0 RNA commands from JSON STAR argument arrays.

No subprocesses, network requests, input-data inspection, or workloads are run.
Mappings: Parabricks 4.7.0 man_rna_fq2bam and STAR 2.7.2a parametersDefault.
See references/pbrun-rna_fq2bam.md for scope, input schema, and limitations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys


SCALARS = {
    "genomeSAindexNbases": "num-sa-bases",
    "alignIntronMax": "max-intron-size",
    "alignIntronMin": "min-intron-size",
    "outFilterMatchNmin": "min-match-filter",
    "outFilterMatchNminOverLread": "min-match-filter-normalized",
    "outFilterIntronMotifs": "out-filter-intron-motifs",
    "outFilterMismatchNmax": "max-out-filter-mismatch",
    "outFilterMismatchNoverLmax": "max-out-filter-mismatch-ratio",
    "outFilterMultimapNmax": "max-out-filter-multimap",
    "outReadsUnmapped": "out-reads-unmapped",
    "outSAMstrandField": "out-sam-strand-field",
    "outSAMmode": "out-sam-mode",
    "outSAMmapqUnique": "out-sam-mapq-unique",
    "outFilterScoreMinOverLread": "min-score-filter",
    "alignSplicedMateMapLminOverLmate": "min-spliced-mate-length",
    "limitOutSAMoneReadBytes": "max-out-read-size",
    "alignTranscriptsPerReadNmax": "max-alignments-per-read",
    "scoreGap": "score-gap",
    "seedSearchStartLmax": "seed-search-start",
    "limitBAMsortRAM": "max-bam-sort-memory",
    "alignEndsType": "align-ends-type",
    "alignInsertionFlush": "align-insertion-flush",
    "alignMatesGapMax": "max-align-mates-gap",
    "alignSplicedMateMapLmin": "min-align-spliced-mate-map",
    "limitOutSJcollapsed": "max-collapsed-junctions",
    "alignSJoverhangMin": "min-align-sj-overhang",
    "alignSJDBoverhangMin": "min-align-sjdb-overhang",
    "sjdbOverhang": "sjdb-overhang",
    "chimJunctionOverhangMin": "min-chim-overhang",
    "chimSegmentMin": "min-chim-segment",
    "chimMultimapNmax": "max-chim-multimap",
    "chimMultimapScoreRange": "chim-multimap-score-range",
    "chimScoreJunctionNonGTAG": "chim-score-non-gtag",
    "chimNonchimScoreDropMin": "min-non-chim-score-drop",
    "chimOutJunctionFormat": "out-chim-format",
    "twopassMode": "two-pass-mode",
}
VECTORS = {
    "readNameSeparator": ("read-name-separator", None),
    "outSAMattributes": ("out-sam-attributes", None),
    "alignSJstitchMismatchNmax": ("max-junction-mismatches", 4),
}
ENUMS = {
    "outReadsUnmapped": {"None", "Fastx"},
    "outSAMstrandField": {"None", "intronMotif"},
    "outSAMmode": {"None", "Full", "NoQS"},
    "alignEndsType": {"Local", "EndToEnd"},
    "alignInsertionFlush": {"None", "Right"},
    "twopassMode": {"None", "Basic"},
}


def nonempty_string(value):
    return isinstance(value, str) and bool(value) and "\x00" not in value


def parse_options(tokens):
    if not isinstance(tokens, list) or not tokens or not all(nonempty_string(t) for t in tokens):
        raise ValueError("star_args must be a nonempty array of argument strings, not a shell command")
    if PurePosixPath(tokens[0]).name == "STAR":
        tokens = tokens[1:]
    options = {}
    current = None
    for token in tokens:
        if token.startswith("--"):
            if not re.fullmatch(r"--[A-Za-z][A-Za-z0-9]*", token):
                raise ValueError(f"Use separate STAR flag and value tokens: {token!r}")
            current = token[2:]
            if current in options:
                raise ValueError(f"Repeated STAR option needs manual resolution: {token}")
            options[current] = []
        elif current is None:
            raise ValueError(f"Expected a STAR option, received {token!r}")
        else:
            options[current].append(token)
    return options


def one(options, name):
    values = options.get(name, [])
    if len(values) != 1:
        raise ValueError(f"--{name} requires exactly one value")
    return values[0]


def read_inputs(options):
    reads = options.get("readFilesIn", [])
    if len(reads) not in (1, 2):
        raise ValueError("--readFilesIn requires one single-end list or two paired-end lists")
    mates = [value.split(",") for value in reads]
    if any(not value for mate in mates for value in mate) or len({len(mate) for mate in mates}) != 1:
        raise ValueError("Read lists must have equal lane counts and no empty members")
    lanes = list(zip(*mates))
    groups = []
    rg_tokens = options.get("outSAMattrRGline", ["-"])
    if rg_tokens != ["-"]:
        groups = [[]]
        for token in rg_tokens:
            if token == ",":
                groups.append([])
            else:
                groups[-1].append(token)
        if len(groups) != len(lanes):
            raise ValueError("Provide one comma-separated read group per lane; no groups are inferred or replicated")
        for group in groups:
            if not group or not group[0].startswith("ID:"):
                raise ValueError("Each STAR read group must start with ID:")
            tags = []
            for tag in group:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]:[^\t\r\n]+", tag) or "\\t" in tag:
                    raise ValueError(f"Invalid or ambiguous read-group tag: {tag!r}")
                tags.append(tag[:2])
            if len(tags) != len(set(tags)):
                raise ValueError("A read group cannot repeat a tag")
    argv = []
    for index, lane in enumerate(lanes):
        argv.extend(["--in-fq" if len(mates) == 2 else "--in-se-fq", *lane])
        if groups:
            argv.append("@RG\\t" + "\\t".join(groups[index]))
    return argv


def translate(request):
    result = {"status": "invalid", "draft_argv": None, "command": None,
              "notes": [], "issues": [], "untranslated": []}
    if isinstance(request, dict) and "name" in request:
        result["name"] = request["name"]
    try:
        if not isinstance(request, dict):
            raise ValueError("Each request must be a JSON object")
        allowed = {"name", "version", "star_args", "ref", "output_dir", "out_bam", "mark_duplicates"}
        if set(request) - allowed:
            raise ValueError(f"Unknown request fields: {sorted(set(request) - allowed)}")
        if request.get("version") != "4.7.0":
            raise ValueError('This helper supports only explicit version "4.7.0"')
        for field in ("ref", "output_dir", "out_bam"):
            if not nonempty_string(request.get(field)):
                raise ValueError(f"{field} must be an explicit nonempty path string")
        if not isinstance(request.get("mark_duplicates", False), bool):
            raise ValueError("mark_duplicates must be a JSON boolean")
        options = parse_options(request.get("star_args"))
        if "runMode" in options and one(options, "runMode") != "alignReads":
            raise ValueError("This helper translates alignment only, not STAR indexing or other run modes")
        genome = one(options, "genomeDir")
        argv = ["pbrun", "rna_fq2bam", "--ref", request["ref"],
                "--genome-lib-dir", genome, "--output-dir", request["output_dir"],
                "--out-bam", request["out_bam"], *read_inputs(options)]
        if not request.get("mark_duplicates", False):
            argv.append("--no-markdups")
            result["notes"].append("Duplicate marking is disabled to preserve CPU STAR's lack of a marking step.")
        else:
            result["issues"].append("Duplicate marking adds a processing step that CPU STAR does not perform.")
        handled = {"genomeDir", "readFilesIn", "outSAMattrRGline", "runMode"}
        for name, values in options.items():
            if name in handled:
                continue
            if name in SCALARS:
                value = one(options, name)
                if name in ENUMS and value not in ENUMS[name]:
                    result["untranslated"].append({"option": "--" + name, "values": values})
                else:
                    argv.extend(["--" + SCALARS[name], value])
            elif name in VECTORS:
                target, count = VECTORS[name]
                if not values or (count is not None and len(values) != count):
                    raise ValueError(f"Wrong number of values for --{name}")
                argv.extend(["--" + target, *values])
            elif name == "runThreadN":
                one(options, name)
                result["notes"].append("--runThreadN is a CPU thread count; --num-threads is workers per GPU stream. Leave Parabricks at auto unless separately tuned.")
            elif name == "outSAMtype":
                if values != ["BAM", "SortedByCoordinate"]:
                    result["issues"].append(f"STAR requested output mode {values!r}; rna_fq2bam produces a coordinate-sorted BAM. Review the output contract.")
            elif name == "outFileNamePrefix":
                prefix = one(options, name)
                basename = prefix.rsplit("/", 1)[-1]
                if basename:
                    argv.extend(["--out-prefix", basename])
                result["notes"].append("Generated STAR outputs use the requested output_dir and the original prefix basename; the final BAM uses out_bam.")
            elif name == "readFilesCommand":
                if not values:
                    raise ValueError("--readFilesCommand requires a command")
                # STAR joins these tokens as a command string. Preserve that
                # string; shlex.join(argv) below quotes it as one pbrun value.
                argv.extend(["--read-files-command", " ".join(values)])
            elif name == "chimOutType":
                forms = {("Junctions",): "Junctions", ("WithinBAM",): "WithinBAM",
                         ("WithinBAM", "HardClip"): "WithinBAM_HardClip",
                         ("WithinBAM", "SoftClip"): "WithinBAM_SoftClip"}
                if tuple(values) in forms:
                    argv.extend(["--out-chim-type", forms[tuple(values)]])
                else:
                    result["untranslated"].append({"option": "--" + name, "values": values})
            elif name == "outSAMunmapped":
                if values in (["None"], ["Within"]):
                    argv.extend(["--out-sam-unmapped", values[0]])
                elif values == ["Within", "KeepPairs"]:
                    argv.extend(["--out-sam-unmapped", "Within_KeepPairs"])
                    result["issues"].append("Within_KeepPairs behaves like Within in sorted output. Extra unmapped-mate copies for each alignment of a multi-mapping mate and unsorted adjacency are not preserved; ordinary unmapped-read inclusion remains possible. Fastx is not a replacement for that record-level contract.")
                else:
                    result["untranslated"].append({"option": "--" + name, "values": values})
            else:
                result["untranslated"].append({"option": "--" + name, "values": values})
        if "outSAMtype" not in options:
            result["issues"].append("STAR's default output is SAM; the requested Parabricks target is a sorted BAM. Review that format change.")
        if options.get("outSAMmode") == ["None"]:
            result["issues"].append("--outSAMmode None suppresses alignment output; review its conflict with a requested final BAM.")
        if "chimOutType" in options and options.get("chimSegmentMin", ["0"]) == ["0"]:
            result["issues"].append("Chimeric output is disabled when --min-chim-segment is zero (the default).")
        if result["untranslated"]:
            result["issues"].append("Untranslated options were omitted from the draft. Resolve them before using it; this is not an equivalent command.")
        if options.get("outSAMattrRGline", ["-"]) == ["-"]:
            result["issues"].append("Parabricks will generate read groups. Confirm sample metadata if read-group identity matters; no metadata was inferred by this helper.")
        result["notes"].append("Draft only: paths, reference/index compatibility, numeric ranges, runtime readiness, and biological output parity are not validated.")
        result.update(status="needs_review" if result["issues"] else "draft",
                      draft_argv=argv, command=shlex.join(argv))
    except ValueError as exc:
        result["issues"].append(str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON object or array of translation requests; use - for stdin")
    args = parser.parse_args()
    try:
        data = json.loads(sys.stdin.read() if args.input == "-" else Path(args.input).read_text())
        results = [translate(item) for item in data] if isinstance(data, list) else translate(data)
        print(json.dumps(results, indent=2))
        items = results if isinstance(results, list) else [results]
        return 2 if any(item["status"] == "invalid" for item in items) else 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "issues": [str(exc)]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
