#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 NVIDIA Corporation. All rights reserved.
#
# FORK of NVIDIA/skills' prune-orphans.sh, adapted for this repo's GROUPED,
# multi-root layout. Differences from upstream:
#   - Upstream scans a single flat `skills/*/` root. We scan the SOURCED group
#     roots in PRUNE_ROOTS (the wholly-native roots nim-skills/ and workflows/
#     are never scanned, so they can't be pruned).
#   - catalog_dir values are full grouped paths (e.g. library-skills/nvMolKit),
#     kept at DEPTH 1 under their group root, so the scan and the expected-set
#     comparison both use full relative paths.
#
# Prunes any dir directly under a PRUNE_ROOTS root that is neither declared in
# components.d/*.yml (as a catalog_dir) nor listed in catalog-exceptions.yml.
# The deletion lands in the sync commit, visible in the PR diff.
#
# Safety rails (unchanged from upstream):
#   - If any components.d / exceptions file fails to parse, pruning is skipped
#     for the whole run (a parse error would make skills look unregistered).
#   - If more than PRUNE_CAP dirs would be pruned, nothing is deleted; the list
#     is written to the overflow file and surfaced as a workflow warning.

set -euo pipefail

PRUNE_ROOTS="${PRUNE_ROOTS:-library-skills open-models-skills}"
PRUNE_CAP="${PRUNE_CAP:-5}"
EXCEPTIONS_FILE="catalog-exceptions.yml"
pruned="${PRUNED_OUT:-/tmp/pruned-orphans.txt}"
overflow="${PRUNED_OVERFLOW_OUT:-/tmp/pruned-orphans-overflow.txt}"
: > "$pruned"
rm -f "$overflow"

expected=$(mktemp "${PRUNE_TMPDIR:-/tmp}/prune-expected.XXXXXX")

# 1. Declared set — every catalog_dir across components.d/*.yml (full paths).
for f in components.d/*.yml; do
  if ! yq e 'true' "$f" > /dev/null 2>&1; then
    echo "::warning::${f} failed to parse — skipping orphan pruning this run"
    exit 0
  fi
  yq -r '.skills[]?.catalog_dir // ""' "$f" | grep -v '^$' >> "$expected" || true
done

# 2. Exceptions — dirs allowed to exist without a registration (full paths).
if [ -f "$EXCEPTIONS_FILE" ]; then
  if ! yq e 'true' "$EXCEPTIONS_FILE" > /dev/null 2>&1; then
    echo "::warning::${EXCEPTIONS_FILE} failed to parse — skipping orphan pruning this run"
    exit 0
  fi
  yq -r '.exceptions[]?.dir // ""' "$EXCEPTIONS_FILE" | grep -v '^$' >> "$expected" || true
fi

if [ ! -s "$expected" ]; then
  echo "::warning::declared skill set is empty — skipping orphan pruning this run"
  exit 0
fi

# 3. Collect orphans: depth-1 dirs under each sourced root not in expected.
orphans=$(mktemp "${PRUNE_TMPDIR:-/tmp}/prune-orphans.XXXXXX")
for root in $PRUNE_ROOTS; do
  [ -d "$root" ] || continue
  for d in "$root"/*/; do
    [ -d "$d" ] || continue
    rel="${d%/}"                       # e.g. library-skills/nvMolKit
    if ! grep -qxF "$rel" "$expected"; then
      echo "$rel" >> "$orphans"
    fi
  done
done

count=$(wc -l < "$orphans" | tr -d ' ')
if [ "$count" -eq 0 ]; then
  echo "No orphaned skill dirs."
  exit 0
fi

# 4. Cap check.
if [ "$count" -gt "$PRUNE_CAP" ]; then
  cp "$orphans" "$overflow"
  echo "::warning::${count} orphaned skill dirs exceed the prune cap (${PRUNE_CAP}) — nothing deleted. Dirs:"
  cat "$orphans"
  exit 0
fi

# 5. Prune.
while read -r rel; do
  git rm -rq "$rel"
  echo "$rel" >> "$pruned"
  echo "  ✂ pruned $rel (no components.d registration)"
done < "$orphans"
