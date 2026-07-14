#!/usr/bin/env python3
"""Keep the generated plugin payload in sync with the source skills.

The installable plugin under ``plugins/bionemo-agent-toolkit/`` is a *generated*
copy of the source skills, and the marketplace catalogs ship whatever is in that
payload. Nothing in the repo regenerates it automatically, so it silently drifts
(e.g. a skill added to source but never added to the plugin).

This script enforces two invariants:

  1. COVERAGE  — every distributable source skill is listed in ``skills.sh.json``.
  2. FRESHNESS — for every listed skill, the plugin payload folder is an exact
                 copy of the source skill folder minus ``evals/``.

Modes:
  --check  (CI + local)  exit non-zero and report if anything is out of sync.
  --write  (contributor) rebuild the payload to match ``skills.sh.json``.
           (Coverage gaps are NOT auto-fixed — adding a skill to a grouping in
           skills.sh.json is a human decision; --check will tell you.)

Usage:
  python scripts/plugin_sync.py --check
  python scripts/plugin_sync.py --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_SKILLS = REPO / "plugins" / "bionemo-agent-toolkit" / "skills"
CONFIG = REPO / "skills.sh.json"

# Source roots that hold distributable skills.
SOURCE_ROOTS = ["nim-skills", "library-skills", "open-models-skills", "workflows"]
# Path segments that never contain a distributable skill.
EXCLUDE_SEGMENTS = {"plugins", "vendor", "evals", "node_modules", ".git"}
# Files/dirs ignored when copying/comparing (never part of the payload).
# `.skillsource.json` is skills.sh metadata that the generator strips from the payload.
JUNK = {".DS_Store", "__pycache__", ".skillsource.json"}
# Subdirectories of a skill that are stripped from the plugin payload.
STRIP_FROM_PAYLOAD = {"evals"}


def _excluded(path: Path) -> bool:
    return any(seg in EXCLUDE_SEGMENTS for seg in path.parts)


def discover_source_skills() -> dict[str, Path]:
    """Map skill name -> source dir. A skill is a SKILL.md dir with no
    descendant SKILL.md dir (containers/index skills are excluded)."""
    candidates: list[Path] = []
    for root in SOURCE_ROOTS:
        root_path = REPO / root
        if not root_path.exists():
            continue
        for skill_md in root_path.rglob("SKILL.md"):
            rel = skill_md.relative_to(REPO)
            if _excluded(rel.parent) or _excluded(rel):
                continue
            candidates.append(skill_md.parent)

    # Drop containers: a candidate that is an ancestor of another candidate.
    skills: dict[str, Path] = {}
    for c in candidates:
        if any(other != c and c in other.parents for other in candidates):
            continue  # container / index skill, not distributable
        if c.name in skills:
            raise SystemExit(f"ERROR: duplicate skill name '{c.name}': "
                             f"{skills[c.name]} vs {c}")
        skills[c.name] = c
    return skills


def config_skill_names() -> list[str]:
    data = json.loads(CONFIG.read_text())
    names: list[str] = []
    for group in data.get("groupings", []):
        names.extend(group.get("skills", []))
    names.extend(data.get("notGrouped", []) if isinstance(data.get("notGrouped"), list) else [])
    return names


def _file_map(root: Path, strip_top: set[str]) -> dict[str, str]:
    """relpath -> sha256 for files under root, skipping junk and stripped top dirs."""
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] in strip_top:
            continue
        if any(part in JUNK for part in rel.parts):
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def compare(source_dir: Path, payload_dir: Path) -> list[str]:
    """Return list of human-readable differences (empty == in sync)."""
    if not payload_dir.exists():
        return [f"missing from plugin payload entirely"]
    src = _file_map(source_dir, STRIP_FROM_PAYLOAD)
    dst = _file_map(payload_dir, set())
    diffs = []
    for rel in sorted(set(src) - set(dst)):
        diffs.append(f"missing in payload: {rel}")
    for rel in sorted(set(dst) - set(src)):
        diffs.append(f"extra in payload:   {rel}")
    for rel in sorted(set(src) & set(dst)):
        if src[rel] != dst[rel]:
            diffs.append(f"content differs:    {rel}")
    return diffs


def check() -> int:
    source = discover_source_skills()
    listed = config_skill_names()
    listed_set = set(listed)
    payload_dirs = {p.name for p in PLUGIN_SKILLS.iterdir() if p.is_dir()} if PLUGIN_SKILLS.exists() else set()

    problems: list[str] = []

    # 1. Coverage: source skills missing from skills.sh.json
    missing_cfg = sorted(set(source) - listed_set)
    for name in missing_cfg:
        problems.append(f"[coverage] source skill '{name}' ({source[name].relative_to(REPO)}) "
                        f"is NOT listed in skills.sh.json")

    # 2. Stale config: listed names with no source skill
    for name in sorted(listed_set - set(source)):
        problems.append(f"[stale-config] skills.sh.json lists '{name}' but no source skill exists")

    # 3. Orphan payload: payload folders not listed in config
    for name in sorted(payload_dirs - listed_set):
        problems.append(f"[orphan] plugin payload has '{name}' but it is not in skills.sh.json")

    # 4. Freshness: each listed+existing skill must match source minus evals
    for name in listed:
        if name not in source:
            continue  # already reported as stale-config
        diffs = compare(source[name], PLUGIN_SKILLS / name)
        for d in diffs:
            problems.append(f"[freshness] {name}: {d}")

    if problems:
        print("Plugin sync check FAILED:\n")
        for p in problems:
            print(f"  - {p}")
        print("\nFix:")
        if missing_cfg:
            print("  * Add the [coverage] skills to a grouping in skills.sh.json (pick the right group).")
        print("  * Then run:  python scripts/plugin_sync.py --write   (and commit the result)")
        return 1

    print(f"Plugin sync OK — {len(listed)} skills, payload matches source (minus evals/).")
    return 0


def write() -> int:
    source = discover_source_skills()
    listed = config_skill_names()
    listed_set = set(listed)
    PLUGIN_SKILLS.mkdir(parents=True, exist_ok=True)

    def _ignore(_dir, names):
        return {n for n in names if n in STRIP_FROM_PAYLOAD or n in JUNK}

    rebuilt = 0
    for name in listed:
        src = source.get(name)
        if src is None:
            print(f"  ! skip '{name}': listed in skills.sh.json but no source skill found")
            continue
        dst = PLUGIN_SKILLS / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=_ignore)
        rebuilt += 1

    # Remove payload folders no longer listed.
    removed = 0
    for p in list(PLUGIN_SKILLS.iterdir()):
        if p.is_dir() and p.name not in listed_set:
            shutil.rmtree(p)
            removed += 1
            print(f"  - removed orphan payload: {p.name}")

    print(f"Rebuilt {rebuilt} skill(s) in the payload; removed {removed} orphan(s).")

    uncovered = sorted(set(source) - listed_set)
    if uncovered:
        print("\nNOTE: these source skills are NOT in skills.sh.json and were "
              "therefore NOT added to the plugin:")
        for name in uncovered:
            print(f"  - {name} ({source[name].relative_to(REPO)})")
        print("Add them to a grouping in skills.sh.json (a human choice), then re-run --write.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="verify sync; non-zero exit if out of sync")
    g.add_argument("--write", action="store_true", help="rebuild the plugin payload from source + skills.sh.json")
    args = ap.parse_args()
    return check() if args.check else write()


if __name__ == "__main__":
    sys.exit(main())
