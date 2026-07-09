/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

process BWA_MEM {
    tag "$meta.id"
    label 'process_medium'

    input:
    tuple val(meta), path(reads)
    path reference

    output:
    tuple val(meta), path("*.bam"), emit: bam

    script:
    """
    echo "bwa mem stub" > ${meta.id}.bam
    """
}
