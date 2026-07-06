# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

version 1.0

workflow GermlineStub {
  input {
    File ref_fasta
    File fastq_r1
    File fastq_r2
    String sample_id
  }
  call BwaMem { input: ... }
  call GatkHaplotypeCaller { input: bam = BwaMem.bam, ref = ref_fasta, sample_id = sample_id }
  output { File vcf = GatkHaplotypeCaller.vcf }
}

task BwaMem {
  input {
    File r1
    File r2
    File ref
    String sample_id
  }
  command <<<
    echo "bwa mem stub" > ~{sample_id}.bam
  >>>
  output { File bam = "~{sample_id}.bam" }
  runtime { docker: "ubuntu:22.04" cpu: 4 memory: "8G" }
}

task GatkHaplotypeCaller {
  input {
    File bam
    File ref
    String sample_id
  }
  command <<<
    echo "## stub" | gzip > ~{sample_id}.vcf.gz
  >>>
  output { File vcf = "~{sample_id}.vcf.gz" }
  runtime { docker: "ubuntu:22.04" cpu: 8 memory: "16G" }
}
