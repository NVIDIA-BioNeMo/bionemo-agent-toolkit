# SPDX-FileCopyrightText: Copyright (c) 2026 SyntheticGestalt. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Verify every ZAO skill conforms to the agentskills.io spec + the project's
additional metadata requirements.

Skill layout (agentskills.io spec):
  skills/<skill-name>/SKILL.md   (one directory per skill)

Frontmatter requirements:
  Spec-required (agentskills.io):
    - name           (string, kebab-case, matches the parent directory name)
    - description    (string, non-empty, 1-1024 chars)
  Spec-optional but encouraged:
    - license        (string)
    - compatibility  (string, <=500 chars, environment / target-agent notes)
  Project-required (under `metadata:`):
    - owner          (string, email-like)
    - classification ("atomic-skill" | "workflow-skill")
    - risk_tier      ("skill")
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise ValueError("file does not start with `---` frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter has no closing `---` delimiter")
    parsed = yaml.safe_load(text[4:end])
    if not isinstance(parsed, dict):
        raise ValueError(f"frontmatter did not parse as a mapping: {type(parsed).__name__}")
    return parsed


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_spec_required_fields(skill_path: Path) -> None:
    fm = _parse_frontmatter(skill_path.read_text())
    assert isinstance(fm.get("name"), str) and fm["name"], f"{skill_path.parent.name}: `name` missing/empty"
    assert isinstance(fm.get("description"), str) and fm["description"], (
        f"{skill_path.parent.name}: `description` missing/empty"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_name_matches_directory(skill_path: Path) -> None:
    fm = _parse_frontmatter(skill_path.read_text())
    assert fm["name"] == skill_path.parent.name, (
        f"{skill_path}: name='{fm['name']}' != parent dir '{skill_path.parent.name}'"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_name_is_kebab_case_with_prefix(skill_path: Path) -> None:
    name = _parse_frontmatter(skill_path.read_text())["name"]
    assert 1 <= len(name) <= 64, f"{skill_path}: name length {len(name)} out of 1-64"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), (
        f"{skill_path}: name='{name}' violates kebab-case rule"
    )
    assert name.startswith("zao-"), (
        f"{skill_path}: name='{name}' lacks zao-* prefix — required for discoverability"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_description_length(skill_path: Path) -> None:
    desc = _parse_frontmatter(skill_path.read_text())["description"]
    assert 1 <= len(desc) <= 1024, f"{skill_path}: description length {len(desc)} out of 1-1024"


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_metadata_block(skill_path: Path) -> None:
    md = _parse_frontmatter(skill_path.read_text()).get("metadata")
    assert isinstance(md, dict), f"{skill_path}: frontmatter missing `metadata:` mapping"
    owner = md.get("owner")
    assert isinstance(owner, str) and "@" in owner and "." in owner.split("@", 1)[1], (
        f"{skill_path}: metadata.owner='{owner}' doesn't look like an email/alias"
    )
    assert md.get("classification") in {"atomic-skill", "workflow-skill"}, (
        f"{skill_path}: metadata.classification='{md.get('classification')}'"
    )
    assert md.get("risk_tier") == "skill", (
        f"{skill_path}: metadata.risk_tier='{md.get('risk_tier')}' (expected 'skill')"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_optional_recommended_fields(skill_path: Path) -> None:
    fm = _parse_frontmatter(skill_path.read_text())
    assert fm.get("license"), f"{skill_path}: `license` field missing or empty"
    assert fm.get("compatibility"), f"{skill_path}: `compatibility` field missing or empty"
    assert len(fm["compatibility"]) <= 500, (
        f"{skill_path}: compatibility length {len(fm['compatibility'])} > 500"
    )


def test_skill_files_under_token_budget() -> None:
    for skill_path in SKILL_FILES:
        text = skill_path.read_text()
        n_lines = text.count("\n") + 1
        approx_tokens = len(text) // 4
        assert n_lines <= 500, f"{skill_path}: {n_lines} lines > 500 (cap)"
        assert approx_tokens <= 5000, f"{skill_path}: ~{approx_tokens} tokens > 5000 (cap)"


def test_skills_directory_layout_matches_spec() -> None:
    stray_md = list(SKILLS_DIR.glob("*.md"))
    assert not stray_md, f"stray .md files at {SKILLS_DIR} (spec requires <skill-name>/SKILL.md): {stray_md}"
    assert SKILL_FILES, f"No skills discovered under {SKILLS_DIR}/*/SKILL.md"
