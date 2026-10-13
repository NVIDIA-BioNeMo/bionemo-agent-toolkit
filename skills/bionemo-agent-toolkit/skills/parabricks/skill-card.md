## Description: <br>
Select NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide version-aware commands for FASTQ/BAM processing, RNA-seq, variant calling, BAM QC, and GVCF workflows. <br>

Use is subject to the licenses below. Current version 1.3.0 is awaiting live
evaluation and a matching signature; the historical evaluation verdict was
**NEUTRAL**, not a publication recommendation. See [BENCHMARK.md](BENCHMARK.md). <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
CC-BY-4.0 AND Apache-2.0 <br>
## Use Case: <br>
Developers and bioinformatics engineers selecting and configuring NVIDIA Parabricks GPU-accelerated genomics tools for FASTQ/BAM processing, variant calling, RNA-seq alignment, and runtime readiness assessment. <br>

### Triggers and exclusions
Use for requests such as "prepare a pbrun fq2bam command", "translate these STAR
arguments to Parabricks", or "check this host's Parabricks readiness".
Whole-workflow acceleration planning belongs to `genomics-workflow-acceleration`.
General GPU advice, unrelated genomics tools and clinical interpretation are
outside this skill's scope.

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [Optional] <br>
**Credential Type(s):** [API key] <br>

Command guidance needs no GPU, local Parabricks installation, or credential.
The readiness helper requires Bash and GNU coreutils `timeout` (or `gtimeout`);
the STAR translator requires Python 3.7 or newer and only its standard library.
Executing the documented Parabricks commands requires a supported Linux host,
an NVIDIA GPU with enough memory, a compatible driver, Docker, NVIDIA Container
Toolkit, and access to the selected image. Pulling from `nvcr.io` may require
NGC authentication. See the [runtime guide](references/runtime-environment.md)
for release-specific checks. <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [Tool Index](references/tool-index.md) <br>
- [Runtime Environment](references/runtime-environment.md) <br>
- [Command Conventions](references/command-conventions.md) <br>
- [Performance](references/performance.md) <br>
- [Shared Options](references/shared-options.md) <br>
- [Parabricks Release Notes](https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Configuration instructions, Analysis] <br>
**Output Format:** [Markdown with inline bash code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Historical Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
The current payload contains 18 tasks (17 positive, 1 negative); it has no live
evaluation result for the final changes yet. <br>
The historical results below cover version 1.2.1 on 2026-10-02 with 7 tasks
(6 positive, 1 negative) in isolated sandbox pods; evaluator dataset digest
sha256:23088600f666e241635d67155f709ac6a3b62ee4705f6b793e39fe5421955b6b.
See [BENCHMARK.md](BENCHMARK.md) for provenance and the current dataset file hash. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Checks final-answer correctness against the reference answer. <br>
- Discoverability: Checks whether the expected skill was selected and decoys were avoided. <br>
- Effectiveness: Checks whether the user's goal was achieved and expected workflow behavior was followed. <br>
- Efficiency: Checks tool-call productivity and token efficiency. <br>

Underlying evaluation signals used in this run: <br>
- `security`: Detects unsafe operations, secret leakage, and unauthorized access. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `skill_efficiency`: Tool-call productivity. <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Historical Evaluation Results (1.2.1): <br>
Reported verdict: **NEUTRAL**; overall lift was unavailable. The original
below-PASS explanation conflicts with the displayed scores, as documented in
[BENCHMARK.md](BENCHMARK.md). These scores do not establish a current pass. <br>

| Measure | Claude Code (with skill) | Codex (with skill) |
|---|---:|---:|
| Overall | 97.7% | 96.5% |
| Security | 100.0% | 100.0% |
| Correctness | 100.0% | 100.0% |
| Discoverability | 100.0% | 95.0% |
| Effectiveness | 97.1% | 98.6% |
| Efficiency | 91.1% | 88.9% |

## Skill Version(s): <br>
Current payload: 1.3.0 (source: `SKILL.md` frontmatter). Historical evaluation:
1.2.1. A new signature must be generated by NVSkills CI after validation of the
final payload. <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>
