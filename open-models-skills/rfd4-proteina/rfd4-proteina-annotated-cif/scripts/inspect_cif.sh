#!/usr/bin/env bash
# Inspect structure, chemistry, and conditions without modifying the CIF.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${RFPROTEINA_ROOT:-$PWD}"

if [ "$#" -ne 1 ]; then
    echo "usage: inspect_cif.sh <file.cif>" >&2
    exit 2
fi

export ALLOW_BIOTITE_CCD="${ALLOW_BIOTITE_CCD:-True}"
if [ -z "${RFPROTEINA_PYTHON:-}" ]; then
    RFPROTEINA_PYTHON="$REPO_ROOT/.venv/bin/python"
    if [ ! -x "$RFPROTEINA_PYTHON" ]; then
        RFPROTEINA_PYTHON="python"
    fi
fi
exec "$RFPROTEINA_PYTHON" "$SCRIPT_DIR/inspect_cif.py" "$1"
