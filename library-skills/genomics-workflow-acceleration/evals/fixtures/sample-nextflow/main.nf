#!/usr/bin/env nextflow

/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal fixture for eval cases — CPU-style GATK/BWA names, not production-ready.
 */

params.samplesheet = params.samplesheet ?: 'samplesheet.csv'
params.outdir      = params.outdir ?: 'results'
params.reference   = params.reference ?: 'genome.fa'

include { BWA_MEM } from './modules/local/bwa_mem'
include { GATK_MARKDUPLICATES } from './modules/local/gatk_markduplicates'
include { GATK_HAPLOTYPECALLER } from './modules/local/gatk_haplotypecaller'

workflow {
    ch_samples = channel.fromPath(params.samplesheet)
        .splitCsv(header: true)
        .map { row -> tuple(row.sample_id, file(row.fastq_1), file(row.fastq_2)) }

    BWA_MEM(ch_samples, file(params.reference))
    GATK_MARKDUPLICATES(BWA_MEM.out.bam)
    GATK_HAPLOTYPECALLER(GATK_MARKDUPLICATES.out.bam, file(params.reference))
}
