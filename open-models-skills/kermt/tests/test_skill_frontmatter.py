# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Verify every skill conforms to agentskills.io spec + the project's
additional metadata requirements.

Skill layout (agentskills.io spec):
  agent/skills/<skill-name>/SKILL.md   (one directory per skill)

Frontmatter requirements:
  Spec-required (agentskills.io):
    - name           (string, kebab-case, matches the parent directory name)
    - description    (string, non-empty)
  Spec-optional but encouraged:
    - license        (string)
    - compatibility  (string, environment / target-agent notes)
  Project-required (under `metadata:`):
    - owner          (string, looks like an email or alias)
    - classification ("atomic-skill" | "workflow-skill")
    - risk_tier      ("skill")

This test parses the frontmatter with PyYAML (the spec uses standard YAML so
the hand-rolled parser would no longer suffice once `metadata:` introduces
nested keys).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "agent" / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(text: str) -> dict:
    """Extract and parse the YAML frontmatter block (between the first two
    `---` lines)."""
    if not text.startswith("---\n"):
        raise ValueError("file does not start with `---` frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter has no closing `---` delimiter")
    body = text[4:end]
    parsed = yaml.safe_load(body)
    if not isinstance(parsed, dict):
        raise ValueError(f"frontmatter did not parse as a mapping: {type(parsed).__name__}")
    return parsed


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_spec_required_fields(skill_path: Path) -> None:
    """agentskills.io spec: name + description are required."""
    fm = _parse_frontmatter(skill_path.read_text())

    assert "name" in fm, f"{skill_path.parent.name}: frontmatter missing required `name`"
    assert isinstance(fm["name"], str) and fm["name"], f"{skill_path.parent.name}: `name` empty"
    assert "description" in fm, f"{skill_path.parent.name}: frontmatter missing required `description`"
    assert isinstance(fm["description"], str) and fm["description"], (
        f"{skill_path.parent.name}: `description` empty"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_name_matches_directory(skill_path: Path) -> None:
    """Spec: name field must match the parent directory name."""
    fm = _parse_frontmatter(skill_path.read_text())
    expected = skill_path.parent.name
    assert fm["name"] == expected, (
        f"{skill_path}: name='{fm['name']}' does not match parent dir '{expected}' "
        "(spec rule: name must equal directory name)"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_name_is_kebab_case(skill_path: Path) -> None:
    """Spec: name is 1-64 chars, lowercase alphanumeric + hyphens,
    no leading/trailing/consecutive hyphens. We further require the
    `kermt-` prefix for discoverability."""
    fm = _parse_frontmatter(skill_path.read_text())
    name = fm["name"]
    assert 1 <= len(name) <= 64, f"{skill_path}: name length {len(name)} out of 1-64"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), (
        f"{skill_path}: name='{name}' violates kebab-case rule "
        "(lowercase alphanumeric + single hyphens, no leading/trailing/consecutive)"
    )
    assert name.startswith("kermt-"), (
        f"{skill_path}: name='{name}' lacks kermt-* prefix — required for discoverability"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_description_length(skill_path: Path) -> None:
    """Spec: description must be 1-1024 characters."""
    fm = _parse_frontmatter(skill_path.read_text())
    desc = fm["description"]
    assert 1 <= len(desc) <= 1024, (
        f"{skill_path}: description length {len(desc)} out of spec 1-1024"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_metadata_block(skill_path: Path) -> None:
    """Project convention: `metadata:` map must carry owner / classification /
    risk_tier. (These don't live at the top level because the spec's top-level
    fields are name / description / license / compatibility / metadata /
    allowed-tools only.)"""
    fm = _parse_frontmatter(skill_path.read_text())
    assert "metadata" in fm, f"{skill_path}: frontmatter missing `metadata:` map"
    md = fm["metadata"]
    assert isinstance(md, dict), f"{skill_path}: metadata must be a mapping, got {type(md).__name__}"

    assert "owner" in md, f"{skill_path}: metadata.owner missing"
    owner = md["owner"]
    assert isinstance(owner, str) and "@" in owner and "." in owner.split("@", 1)[1], (
        f"{skill_path}: metadata.owner='{owner}' doesn't look like an email/alias"
    )

    assert "classification" in md, f"{skill_path}: metadata.classification missing"
    assert md["classification"] in {"atomic-skill", "workflow-skill"}, (
        f"{skill_path}: metadata.classification='{md['classification']}' "
        "(expected atomic-skill or workflow-skill)"
    )

    assert "risk_tier" in md, f"{skill_path}: metadata.risk_tier missing"
    assert md["risk_tier"] == "skill", (
        f"{skill_path}: metadata.risk_tier='{md['risk_tier']}' (expected 'skill')"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parent.name}/SKILL.md")
def test_skill_optional_recommended_fields(skill_path: Path) -> None:
    """`license` and `compatibility` are spec-optional but the project recommends
    populating both for public-release skills."""
    fm = _parse_frontmatter(skill_path.read_text())
    assert "license" in fm and fm["license"], (
        f"{skill_path}: `license` field missing or empty (recommended for public release)"
    )
    assert "compatibility" in fm and fm["compatibility"], (
        f"{skill_path}: `compatibility` field missing or empty (recommended; "
        "should document docker / GPU / target-agent requirements)"
    )
    assert len(fm["compatibility"]) <= 500, (
        f"{skill_path}: compatibility length {len(fm['compatibility'])} > 500 (spec cap)"
    )


def test_skill_files_under_token_budget() -> None:
    """SKILL.md files must be ≤500 lines and ≤5000 tokens (spec recommendation
    + BioNeMo R6). Token count is approximated as chars/4."""
    for skill_path in SKILL_FILES:
        text = skill_path.read_text()
        n_lines = text.count("\n") + 1
        approx_tokens = len(text) // 4
        assert n_lines <= 500, f"{skill_path}: {n_lines} lines > 500 (cap)"
        assert approx_tokens <= 5000, (
            f"{skill_path}: ~{approx_tokens} tokens > 5000 (cap)"
        )


def test_skills_directory_layout_matches_spec() -> None:
    """agentskills.io spec: each skill lives in its own directory containing
    SKILL.md. No stray *.md files at agent/skills/ root."""
    stray_md = [p for p in SKILLS_DIR.glob("*.md")]
    assert not stray_md, (
        f"Found stray .md files at {SKILLS_DIR} (spec requires <skill-name>/SKILL.md): {stray_md}"
    )
    assert SKILL_FILES, f"No skills discovered under {SKILLS_DIR}/*/SKILL.md"
