#!/usr/bin/env python3
"""Scan changed source skills on PRs, or the full catalog when no base is given.

Use the same source-skill discovery as plugin_sync.py, including nested skills
and vendor exclusions. Keep the scanner's exit policy, but finish every selected
scan before returning a failure. Reports include active and suppressed findings.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from plugin_sync import REPO, discover_source_skills


def changed_paths(repo: Path, base_ref: str) -> list[Path]:
    """Include both sides of renames and deletions within surviving skills."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...HEAD", "--"],
        cwd=repo, check=True, stdout=subprocess.PIPE,
    )
    return [repo / os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def select_skills(skills: list[Path], changed: list[Path] | None) -> list[Path]:
    """None requests a full scan; an empty change list requests no scans."""
    return sorted(
        skill for skill in skills
        if changed is None or any(path.is_relative_to(skill) for path in changed)
    )


def scan_skills(skills: list[Path], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = [
        "## SkillSpector results", "",
        "| Source skill | Exit code | Risk / 100 | Active findings | Suppressed | Inspection |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    exit_code = 0
    for skill in skills:
        report = output_dir / f"{skill.name}.json"
        command = [
            "skillspector", "scan", str(skill), "--no-llm",
            "--format", "json", "--output", str(report),
        ]
        baseline = skill / "config" / "skillspector-baseline.yml"
        if baseline.is_file():
            command.extend(["--baseline", str(baseline), "--show-suppressed"])
        print(f"Scanning {skill}", flush=True)
        result = subprocess.run(command, check=False)
        status = result.returncode if result.returncode in (0, 1, 2) else 2
        try:
            data = json.loads(report.read_text())
            risk = data["risk_assessment"]["score"]
            findings = len(data["issues"])
            suppressed = data["suppressed_count"]
            inspection = data["analysis_completeness"]["status"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Cannot read report for {skill.name}: {exc}", flush=True)
            risk = findings = suppressed = inspection = "unavailable"
            status = 2
        exit_code = max(exit_code, status)
        row = f"| {skill.name} | {status} | {risk} | {findings} | {suppressed} | {inspection} |"
        summary.append(row)
        print(row, flush=True)

    if not skills:
        summary = ["## SkillSpector results", "", "No changed source skills to scan."]
    else:
        summary.extend([
            "", "Exit 0: scanner risk threshold passed; findings may remain.",
            "Exit 1: scanner risk failure. Exit 2: scan or report error.",
            "Full findings, suppression reasons and inspection limitations are in the JSON reports.",
        ])
    body = "\n".join(summary) + "\n"
    (output_dir / "summary.md").write_text(body)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a") as stream:
            stream.write(body)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Scan source skills changed since this Git merge base")
    parser.add_argument("--output-dir", type=Path, default=Path("skillspector-reports"))
    args = parser.parse_args()
    changed = changed_paths(REPO, args.base_ref) if args.base_ref else None
    skills = select_skills(list(discover_source_skills().values()), changed)
    print(f"Selected {len(skills)} source skill(s)", flush=True)
    return scan_skills(skills, args.output_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
