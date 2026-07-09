/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

process GATK_HAPLOTYPECALLER {
    tag "$meta.id"
    label 'process_high'

    input:
    tuple val(meta), path(bam)
    path reference

    output:
    tuple val(meta), path("*.vcf.gz"), emit: vcf

    script:
    """
    echo "## stub" | gzip > ${meta.id}.vcf.gz
    """
}
