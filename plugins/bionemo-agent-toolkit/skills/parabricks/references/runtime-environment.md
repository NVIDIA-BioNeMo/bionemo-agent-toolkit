# Parabricks runtime environment

Use this reference when assessing NVIDIA Parabricks readiness, installation gaps,
GPU memory, Docker/container access, storage, or runtime recommendations on a
local or target host.

## First Step

Confirm whether the current machine is the Parabricks execution host. If the
user will run on a remote Linux server, cloud instance, scheduler node, or
container platform, ask for facts from that target environment instead of
assuming local results apply.

When the current machine is the execution host, prefer the repository diagnostic
script and use its report as the basis for recommendations:

```bash
python3 skills/parabricks/scripts/check_parabricks_runtime.py
```

When input, output, or temporary directories are known, include them in the
storage check:

```bash
python3 skills/parabricks/scripts/check_parabricks_runtime.py \
  --path <input-dir> \
  --path <output-dir> \
  --path <tmp-dir>
```

Only run container probes when the user agrees to network/image-access side
effects. These checks may pull images or require NGC authentication:

```bash
python3 skills/parabricks/scripts/check_parabricks_runtime.py \
  --run-container-check \
  --parabricks-version <version>
```

For machine-readable output, use:

```bash
python3 skills/parabricks/scripts/check_parabricks_runtime.py --format json
```

Do not install, upgrade, or modify packages. If prerequisites are missing,
provide commands for the user or system administrator to run, and make clear
that the commands must be reviewed for their OS, package manager, security
policy, and Parabricks version.

## Available Scripts

| Script | Purpose | Arguments |
|--------|---------|-----------|
| `scripts/check_parabricks_runtime.py` | Collect local OS, CPU/RAM, GPU, Docker, optional container, Parabricks image, and storage readiness facts | `--path <dir>` repeatable, `--run-container-check`, `--parabricks-version <tag>`, `--format text\|json`, `--timeout <seconds>` |

## Discovery Commands

Use the diagnostic script first when possible. If the script cannot run, if the
target host is remote, or if extra detail is needed, use commands that fit the
target operating system and available tools.

For operating system and kernel:

```bash
uname -a
cat /etc/os-release
```

For NVIDIA GPU and driver details:

```bash
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version,cuda_version,compute_cap --format=csv
nvidia-smi -L
```

For CPU and memory on Linux:

```bash
lscpu
cat /proc/meminfo | grep MemTotal
cat /proc/cpuinfo | grep processor | wc -l
```

For storage:

```bash
df -h
df -h <input-dir> <output-dir> <tmp-dir>
```

For Docker and NVIDIA Container Toolkit:

```bash
docker --version
docker info
docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu22.04 nvidia-smi
```

For Python:

```bash
python3 --version
```

For Parabricks container access, after the user confirms the desired version:

```bash
docker pull nvcr.io/nvidia/clara/clara-parabricks:<version>
docker run --rm --gpus all nvcr.io/nvidia/clara/clara-parabricks:<version> pbrun --help
```

## Current Requirements To Check

For the latest NVIDIA Parabricks documentation, check:

- A Linux operating system that supports the NVIDIA Container Toolkit.
- Docker version 20.10 or higher.
- An NVIDIA driver compatible with the Parabricks container CUDA version. The
  current installation requirements mention CUDA 12.9.1-compatible drivers
  such as 535, 550, 570, 575, or similar.
- NVIDIA GPU support and memory. Current docs state at least 16 GB GPU memory
  per GPU for all tools, with some tools requiring more by default and offering
  lower-memory options.
- CPU RAM and CPU thread recommendations for multi-GPU systems.
- Python 3 availability.
- No unsupported GPU mode for the target Parabricks version. Verify whether
  vGPU or MIG limitations apply in the current docs before making a strong
  claim.

## Interpret Results

Use the diagnostic script output to report:

- OS/distribution and whether it looks like a supported Linux runtime.
- GPU count, model names, compute capability if available, memory per GPU, and
  whether GPUs are visible through `nvidia-smi`.
- Driver version and CUDA version reported by the driver.
- Whether Docker is installed and new enough.
- Whether Docker can access GPUs through NVIDIA Container Toolkit.
- Whether Python 3 is available.
- CPU thread count and system RAM.
- Free space on input, output, and temporary filesystems when paths are known.
- Whether the selected Parabricks container can be pulled and can run `pbrun`.
- Any missing information that prevents a recommendation.

## Missing Prerequisites

When something is missing, do not run install commands. Provide the next action
for the user.

Examples:

- Missing NVIDIA driver: direct the user to install a CUDA-compatible NVIDIA
  data center or supported GPU driver for their OS, then rerun `nvidia-smi`.
- Missing Docker: provide the official Docker Engine installation page for the
  user's distro and a user-run command only after confirming the OS/package
  manager.
- Missing NVIDIA Container Toolkit: provide the official NVIDIA Container
  Toolkit installation page and tell the user to configure Docker GPU runtime.
- Docker cannot access GPUs: suggest verifying driver health, container toolkit
  installation, Docker daemon configuration, and user permissions.
- Missing Python 3: provide an OS-specific Python 3 install command only after
  confirming the OS/package manager.
- Missing Parabricks image access: ask whether the user is authenticated to
  NVIDIA NGC and whether network/proxy policy permits pulling from `nvcr.io`.

When offering commands, label them as "user-run commands" and keep them
separate from diagnostic commands the agent can safely execute.

## Recommendation Style

Use qualitative recommendations:

- `ready`: required runtime components appear available.
- `hardware-constrained`: GPU memory, CPU RAM, CPU threads, or storage may
  limit the requested workflow.
- `runtime-incomplete`: required software such as Docker, NVIDIA Container
  Toolkit, driver support, Python 3, or image access is missing or unverified.
- `I/O-constrained`: storage layout or free space is likely to dominate runtime
  or failure risk.
- `not supported`: the target OS/GPU/runtime mode appears unsupported for the
  selected Parabricks version.
- `not enough information`: key facts are absent.

Prefer the script's `Assessment`, `Recommendations`, and `Open questions`
sections as the starting point. Add workflow-specific guidance only after
checking the requested Parabricks tool, data size, paths, and selected version.

Do not provide exact runtime predictions unless the user supplies comparable
benchmark data including dataset size, read length, coverage, GPU model/count,
storage type, Parabricks version, and command options.

## fq2bam-Specific Guidance

For `fq2bam`, pay special attention to:

- GPU memory per device.
- Number of GPUs requested.
- System RAM and CPU threads.
- Docker GPU runtime availability.
- FASTQ size and expected output size.
- Reference and known-sites file location.
- Temporary directory location and free space.
- Whether `--low-memory` should be considered for constrained GPU memory when
  supported by the selected Parabricks version.

If the environment looks constrained or incomplete, recommend a safer first run
or prerequisite remediation before aggressive performance tuning.

## Output Template

Structure the response as:

```text
Environment summary:
<OS/GPU/driver/Docker/container toolkit/Python/CPU/RAM/storage facts>

Assessment:
<ready | hardware-constrained | runtime-incomplete | I/O-constrained | not supported | not enough information>

Recommendations:
<specific runtime, command, or setup changes>

User-run install/setup commands:
<only include when OS/package manager is known; otherwise link to official docs>

Open questions:
<only facts still needed for a better recommendation>
```

## Key References

- Parabricks installation requirements:
  <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted/installationrequirements.html>
- Parabricks getting started:
  <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html>
- NVIDIA Container Toolkit installation:
  <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- Docker Engine installation:
  <https://docs.docker.com/engine/install/>
- NGC CLI documentation:
  <https://docs.ngc.nvidia.com/cli/>
