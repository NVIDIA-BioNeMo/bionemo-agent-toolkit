#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_CUDA_TEST_IMAGE = "nvidia/cuda:12.9.1-base-ubuntu22.04"
MIN_DOCKER_VERSION = tuple(int(part) for part in "20.10".split("."))
MIN_GPU_MEMORY_GB = int("16")
BYTES_PER_KIB = int("1024")
MIB_PER_GIB = BYTES_PER_KIB
BYTES_PER_GIB = BYTES_PER_KIB ** int("3")
LOW_STORAGE_WARNING_GB = int("100")
SUMMARY_MAX_CHARS = int("300")
DEFAULT_TIMEOUT_SECONDS = int("30")
SCHEMA_VERSION = int("1")
GPU_QUERY_FIELD_COUNT = int("6")
GPU_DISPLAY_START_INDEX = int("1")
VERSION_TOKEN_INDEX = 0
KEY_VALUE_SPLIT_MAX = 1
MEMINFO_MIN_FIELDS = 2
MEMINFO_VALUE_INDEX = 1
ZERO_EXIT_CODE = 0
GPU_NAME_INDEX = 0
GPU_TOTAL_MB_INDEX = 1
GPU_FREE_MB_INDEX = 2
GPU_DRIVER_INDEX = int("3")
GPU_CUDA_INDEX = int("4")
GPU_COMPUTE_CAP_INDEX = int("5")
GB_DECIMAL_PLACES = 2
MIN_DOCKER_VERSION_TEXT = ".".join(str(part) for part in MIN_DOCKER_VERSION)
EXAMPLE_PARABRICKS_VERSION = "4.7.0-1"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


Runner = Callable[[list[str], int], CommandResult]


def run_command(command: list[str], timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return CommandResult(command, None, "", "command not found")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command,
            None,
            exc.stdout or "",
            exc.stderr or "",
            timed_out=True,
        )

    return CommandResult(
        command,
        completed.returncode,
        completed.stdout.strip(),
        completed.stderr.strip(),
    )


def build_report(args: argparse.Namespace, runner: Runner = run_command) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "target": {
            "host": platform.node() or None,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[VERSION_TOKEN_INDEX],
        },
        "checks": {},
        "storage": [],
        "assessment": [],
        "recommendations": [],
        "open_questions": [],
    }

    checks = report["checks"]
    checks["os"] = check_os()
    checks["cpu_memory"] = check_cpu_memory()
    checks["python"] = {
        "status": "ok",
        "version": sys.version.split()[VERSION_TOKEN_INDEX],
        "executable": sys.executable,
    }
    checks["nvidia_smi"] = check_nvidia_smi(runner, args.timeout)
    checks["docker"] = check_docker(runner, args.timeout)

    if args.run_container_check:
        checks["docker_gpu_container"] = check_docker_gpu_container(
            runner, args.timeout, args.cuda_test_image
        )
    else:
        checks["docker_gpu_container"] = {
            "status": "not_checked",
            "reason": "Use --run-container-check to test Docker GPU access.",
        }

    if args.parabricks_version:
        checks["parabricks_container"] = check_parabricks_container(
            runner, args.timeout, args.parabricks_version
        )
    else:
        checks["parabricks_container"] = {
            "status": "not_checked",
            "reason": "Use --parabricks-version <tag> to test pbrun in a Parabricks container.",
        }

    for path in args.path:
        report["storage"].append(check_storage_path(path))

    classify(report)
    return report


def check_os() -> dict[str, Any]:
    info: dict[str, Any] = {
        "status": "ok",
        "system": platform.system(),
        "release": platform.release(),
        "distribution": None,
    }

    os_release = Path("/etc/os-release")
    if os_release.exists():
        values: dict[str, str] = {}
        for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", KEY_VALUE_SPLIT_MAX)
                values[key] = value.strip().strip('"')
        info["distribution"] = values.get("PRETTY_NAME") or values.get("NAME")

    if info["system"] != "Linux":
        info["status"] = "warning"
        info["detail"] = "Parabricks container execution is expected on Linux hosts."

    return info


def check_cpu_memory() -> dict[str, Any]:
    cpu_count = os.cpu_count()
    mem_total_bytes = read_linux_mem_total_bytes()
    result: dict[str, Any] = {
        "status": "ok" if cpu_count else "warning",
        "cpu_count": cpu_count,
        "memory_total_gb": bytes_to_gb(mem_total_bytes),
    }
    if mem_total_bytes is None:
        result["status"] = "warning"
        result["detail"] = "Could not determine total system memory from /proc/meminfo."
    return result


def read_linux_mem_total_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= MEMINFO_MIN_FIELDS and parts[MEMINFO_VALUE_INDEX].isdigit():
                return int(parts[MEMINFO_VALUE_INDEX]) * BYTES_PER_KIB
    return None


def check_nvidia_smi(runner: Runner, timeout: int) -> dict[str, Any]:
    if not shutil.which("nvidia-smi"):
        return {
            "status": "missing",
            "detail": "nvidia-smi was not found on PATH.",
            "gpus": [],
        }

    query = runner(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,driver_version,cuda_version,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        timeout,
    )
    if query.returncode != ZERO_EXIT_CODE:
        return command_failure("nvidia-smi", query)

    gpus = []
    for line in query.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < GPU_QUERY_FIELD_COUNT:
            continue
        total_mb = parse_float(fields[GPU_TOTAL_MB_INDEX])
        free_mb = parse_float(fields[GPU_FREE_MB_INDEX])
        gpus.append(
            {
                "name": fields[GPU_NAME_INDEX],
                "memory_total_gb": round(total_mb / MIB_PER_GIB, GB_DECIMAL_PLACES) if total_mb is not None else None,
                "memory_free_gb": round(free_mb / MIB_PER_GIB, GB_DECIMAL_PLACES) if free_mb is not None else None,
                "driver_version": fields[GPU_DRIVER_INDEX],
                "cuda_version": fields[GPU_CUDA_INDEX],
                "compute_capability": fields[GPU_COMPUTE_CAP_INDEX],
            }
        )

    status = "ok" if gpus else "warning"
    result: dict[str, Any] = {"status": status, "gpus": gpus}
    if not gpus:
        result["detail"] = "nvidia-smi ran, but no GPU rows were parsed."
    return result


def check_docker(runner: Runner, timeout: int) -> dict[str, Any]:
    if not shutil.which("docker"):
        return {"status": "missing", "detail": "docker was not found on PATH."}

    version = runner(["docker", "--version"], timeout)
    if version.returncode != ZERO_EXIT_CODE:
        return command_failure("docker --version", version)

    parsed_version = parse_docker_version(version.stdout)
    info = runner(["docker", "info", "--format", "{{json .}}"], timeout)
    status = "ok"
    details = []
    if parsed_version and parsed_version < MIN_DOCKER_VERSION:
        status = "warning"
        details.append(f"Docker is older than the documented minimum {MIN_DOCKER_VERSION_TEXT}.")
    if info.returncode != ZERO_EXIT_CODE:
        status = "warning"
        details.append("docker info failed; Docker daemon may be unavailable or permission-restricted.")

    return {
        "status": status,
        "version_output": version.stdout,
        "version": ".".join(str(part) for part in parsed_version) if parsed_version else None,
        "daemon_access": info.returncode == ZERO_EXIT_CODE,
        "detail": " ".join(details) or None,
    }


def check_docker_gpu_container(
    runner: Runner, timeout: int, image: str
) -> dict[str, Any]:
    docker = check_docker(runner, timeout)
    if docker.get("status") == "missing":
        return {
            "status": "missing",
            "detail": "Docker is missing, so Docker GPU access cannot be tested.",
        }

    command = ["docker", "run", "--rm", "--gpus", "all", image, "nvidia-smi"]
    result = runner(command, timeout)
    if result.returncode == ZERO_EXIT_CODE:
        return {"status": "ok", "image": image, "detail": "Docker can run nvidia-smi with GPUs."}
    return {
        "status": "failed",
        "image": image,
        "detail": summarize_command_result(result),
    }


def check_parabricks_container(
    runner: Runner, timeout: int, version: str
) -> dict[str, Any]:
    image = f"nvcr.io/nvidia/clara/clara-parabricks:{version}"
    command = ["docker", "run", "--rm", "--gpus", "all", image, "pbrun", "--help"]
    result = runner(command, timeout)
    if result.returncode == ZERO_EXIT_CODE:
        return {
            "status": "ok",
            "image": image,
            "detail": "Parabricks container started and pbrun responded.",
        }
    return {
        "status": "failed",
        "image": image,
        "detail": summarize_command_result(result),
    }


def check_storage_path(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    target = path if path.exists() else first_existing_parent(path)
    if target is None:
        return {
            "path": str(path),
            "status": "missing",
            "detail": "Path and all parents are missing.",
        }

    usage = shutil.disk_usage(target)
    return {
        "path": str(path),
        "checked_path": str(target),
        "status": "ok" if usage.free else "warning",
        "total_gb": bytes_to_gb(usage.total),
        "free_gb": bytes_to_gb(usage.free),
        "used_gb": bytes_to_gb(usage.used),
    }


def first_existing_parent(path: Path) -> Path | None:
    current = path
    while True:
        if current.exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def classify(report: dict[str, Any]) -> None:
    checks = report["checks"]
    assessments: list[str] = []
    recommendations: list[str] = []
    open_questions: list[str] = []

    os_check = checks["os"]
    if os_check["status"] == "warning":
        assessments.append("not supported")
        recommendations.append("Run Parabricks on a Linux host supported by Docker and NVIDIA Container Toolkit.")

    gpu_check = checks["nvidia_smi"]
    if gpu_check["status"] == "missing":
        assessments.append("runtime-incomplete")
        recommendations.append("Make NVIDIA drivers and nvidia-smi available on the target execution host.")
    elif gpu_check["status"] != "ok":
        assessments.append("runtime-incomplete")
        recommendations.append("Resolve nvidia-smi errors before running Parabricks.")
    else:
        low_memory_gpus = [
            gpu for gpu in gpu_check["gpus"]
            if gpu.get("memory_total_gb") is not None and gpu["memory_total_gb"] < MIN_GPU_MEMORY_GB
        ]
        if low_memory_gpus:
            assessments.append("hardware-constrained")
            recommendations.append(
                f"Use a GPU with at least {MIN_GPU_MEMORY_GB} GB memory per GPU, or select workflows/options documented for lower memory."
            )

    docker_check = checks["docker"]
    if docker_check["status"] == "missing":
        assessments.append("runtime-incomplete")
        recommendations.append("Install and configure Docker Engine on the target host.")
    elif docker_check["status"] != "ok":
        assessments.append("runtime-incomplete")
        recommendations.append("Resolve Docker daemon/version/access issues before running Parabricks.")

    gpu_container = checks["docker_gpu_container"]
    if gpu_container["status"] == "not_checked":
        assessments.append("not enough information")
        open_questions.append("Docker GPU container access was not tested; rerun with --run-container-check on the target host.")
    elif gpu_container["status"] != "ok":
        assessments.append("runtime-incomplete")
        recommendations.append("Configure NVIDIA Container Toolkit so Docker can run containers with --gpus all.")

    parabricks = checks["parabricks_container"]
    if parabricks["status"] == "not_checked":
        assessments.append("not enough information")
        open_questions.append("Parabricks container access was not tested; rerun with --parabricks-version <tag> after choosing a version.")
    elif parabricks["status"] != "ok":
        assessments.append("runtime-incomplete")
        recommendations.append("Verify NGC authentication, network/proxy policy, and the requested Parabricks image tag.")

    cpu_memory = checks["cpu_memory"]
    if not cpu_memory.get("cpu_count") or cpu_memory.get("memory_total_gb") is None:
        assessments.append("not enough information")
        open_questions.append("CPU count or total system memory could not be determined.")

    low_storage = [
        item for item in report["storage"]
        if item.get("free_gb") is not None and item["free_gb"] < LOW_STORAGE_WARNING_GB
    ]
    missing_storage = [item for item in report["storage"] if item["status"] == "missing"]
    if low_storage:
        assessments.append("I/O-constrained")
        recommendations.append(
            f"Check input, output, and temporary filesystems; less than {LOW_STORAGE_WARNING_GB} GB free may be risky for many workflows."
        )
    if missing_storage:
        assessments.append("not enough information")
        open_questions.append("One or more requested storage paths do not exist on this host.")

    if not assessments:
        assessments.append("ready")
        recommendations.append(
            "Required local runtime checks passed. Confirm workflow-specific storage, reference files, and Parabricks image access before production runs."
        )

    report["assessment"] = dedupe(assessments)
    report["recommendations"] = dedupe(recommendations)
    report["open_questions"] = dedupe(open_questions)


def render_text(report: dict[str, Any]) -> str:
    lines = []
    target = report["target"]
    checks = report["checks"]

    lines.append("Environment summary:")
    lines.append(f"- Host: {target.get('host') or 'unknown'}")
    lines.append(f"- Platform: {target['platform']} ({target['machine']})")
    os_check = checks["os"]
    lines.append(f"- OS: {os_check.get('distribution') or os_check['system']} {os_check.get('release') or ''}".rstrip())

    cpu = checks["cpu_memory"]
    lines.append(f"- CPU/RAM: {cpu.get('cpu_count') or 'unknown'} CPUs, {format_gb(cpu.get('memory_total_gb'))} RAM")
    lines.append(f"- Python: {checks['python']['version']} ({checks['python']['executable']})")

    gpu = checks["nvidia_smi"]
    if gpu["status"] == "ok":
        lines.append(f"- GPUs: {len(gpu['gpus'])}")
        for index, item in enumerate(gpu["gpus"], start=GPU_DISPLAY_START_INDEX):
            lines.append(
                f"  - GPU {index}: {item['name']}, {format_gb(item.get('memory_total_gb'))} total, "
                f"driver {item['driver_version']}, CUDA {item['cuda_version']}, CC {item['compute_capability']}"
            )
    else:
        lines.append(f"- GPUs: {gpu['status']} ({gpu.get('detail', 'not available')})")

    docker = checks["docker"]
    lines.append(
        f"- Docker: {docker['status']}"
        + (f", {docker.get('version_output')}" if docker.get("version_output") else "")
    )
    lines.append(f"- Docker GPU container: {checks['docker_gpu_container']['status']}")
    lines.append(f"- Parabricks container: {checks['parabricks_container']['status']}")

    if report["storage"]:
        lines.append("- Storage:")
        for item in report["storage"]:
            if item["status"] == "ok":
                lines.append(
                    f"  - {item['path']}: {format_gb(item['free_gb'])} free of {format_gb(item['total_gb'])} "
                    f"(checked {item['checked_path']})"
                )
            else:
                lines.append(f"  - {item['path']}: {item['status']} ({item.get('detail', 'not available')})")

    lines.append("")
    lines.append("Assessment:")
    lines.append(", ".join(report["assessment"]))

    lines.append("")
    lines.append("Recommendations:")
    for item in report["recommendations"]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("Open questions:")
    if report["open_questions"]:
        for item in report["open_questions"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None from this diagnostic run.")

    return "\n".join(lines)


def command_failure(name: str, result: CommandResult) -> dict[str, Any]:
    return {
        "status": "failed",
        "detail": f"{name} failed: {summarize_command_result(result)}",
    }


def summarize_command_result(result: CommandResult) -> str:
    if result.timed_out:
        return "command timed out"
    output = result.stderr or result.stdout or "no output"
    return output.splitlines()[VERSION_TOKEN_INDEX][:SUMMARY_MAX_CHARS]


def parse_docker_version(output: str) -> tuple[int, ...] | None:
    match = re.search(r"version\s+([0-9]+(?:\.[0-9]+){1,2})", output, re.IGNORECASE)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def bytes_to_gb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / BYTES_PER_GIB, GB_DECIMAL_PLACES)


def format_gb(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:g} GB"


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check local NVIDIA Parabricks runtime readiness and print a report."
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Input, output, or temporary path to include in storage checks. Can be repeated.",
    )
    parser.add_argument(
        "--run-container-check",
        action="store_true",
        help="Run a Docker CUDA container with --gpus all to test NVIDIA Container Toolkit.",
    )
    parser.add_argument(
        "--cuda-test-image",
        default=DEFAULT_CUDA_TEST_IMAGE,
        help=f"CUDA image used with --run-container-check. Default: {DEFAULT_CUDA_TEST_IMAGE}",
    )
    parser.add_argument(
        "--parabricks-version",
        help=f"Parabricks container tag to test with pbrun --help, for example {EXAMPLE_PARABRICKS_VERSION}.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report output format.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout in seconds for each external command.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return ZERO_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
