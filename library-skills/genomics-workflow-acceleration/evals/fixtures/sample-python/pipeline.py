#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Minimal Python pipeline fixture for eval cases."""

from pathlib import Path
import subprocess
import sys


def align_bwa(sample: str, ref: Path, out_bam: Path) -> None:
    subprocess.run(
        ["bash", "-c", f'echo "bwa mem stub" > {out_bam}'],
        check=True,
    )


def call_variants_gatk(bam: Path, ref: Path, out_vcf: Path) -> None:
    subprocess.run(
        ["bash", "-c", f'echo "## stub" | gzip > {out_vcf}'],
        check=True,
    )


def main(sample: str, ref: Path, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    bam = outdir / f"{sample}.bam"
    vcf = outdir / f"{sample}.vcf.gz"
    align_bwa(sample, ref, bam)
    call_variants_gatk(bam, ref, vcf)


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
