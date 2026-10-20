#!/usr/bin/env bash
# Validate an annotated CIF without repairing it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

if [ "$#" -lt 1 ]; then
    echo "usage: check_annotated_cif.sh <file.cif> [--strict] [--quiet] [--skip_pipeline]" >&2
    exit 2
fi

export ALLOW_BIOTITE_CCD="${ALLOW_BIOTITE_CCD:-True}"
if [ -z "${RFPROTEINA_PYTHON:-}" ]; then
    RFPROTEINA_PYTHON="$REPO_ROOT/.venv/bin/python"
    if [ ! -x "$RFPROTEINA_PYTHON" ]; then
        RFPROTEINA_PYTHON="python"
    fi
fi
exec "$RFPROTEINA_PYTHON" skills/rfd4-proteina-annotated-cif/scripts/check_annotated_cif.py "$@"
