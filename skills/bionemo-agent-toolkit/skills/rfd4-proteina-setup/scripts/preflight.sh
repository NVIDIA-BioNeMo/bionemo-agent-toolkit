#!/usr/bin/env bash
# Run checks in the selected model runtime without changing the checkout.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${RFPROTEINA_ROOT:-$PWD}"
data_args=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo-root)
            if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                printf '%s\n' 'FAIL: --repo-root requires a model checkout path.' >&2
                exit 2
            fi
            repo_root="$2"
            shift 2
            ;;
        --repo-root=*)
            repo_root="${1#*=}"
            if [ -z "$repo_root" ]; then
                printf '%s\n' 'FAIL: --repo-root requires a model checkout path.' >&2
                exit 2
            fi
            shift
            ;;
        --data-path)
            if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                printf '%s\n' 'FAIL: --data-path requires a data directory.' >&2
                exit 2
            fi
            data_args=(--data-path "$2")
            shift 2
            ;;
        --data-path=*)
            if [ -z "${1#*=}" ]; then
                printf '%s\n' 'FAIL: --data-path requires a data directory.' >&2
                exit 2
            fi
            data_args=(--data-path "${1#*=}")
            shift
            ;;
        -h|--help)
            printf '%s\n' \
                'Usage: preflight.sh [--repo-root PATH] [--data-path PATH]' \
                'Root: --repo-root, then RFPROTEINA_ROOT, then the working directory.' \
                'Data: --data-path, then DATA_PATH; relative paths use the model root.' \
                'Runtime: RFPROTEINA_PYTHON, then the checkout dispatcher, then .venv/bin/python.'
            exit 0
            ;;
        *)
            printf 'FAIL: Unknown argument: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

for required in .project-root pyproject.toml configs/inference.yaml; do
    if [ ! -f "$repo_root/$required" ]; then
        printf 'FAIL: Selected checkout %s is missing %s.\n' "$repo_root" "$required" >&2
        printf '%s\n' 'Set RFPROTEINA_ROOT or --repo-root to the model checkout; the skill catalog is separate.' >&2
        exit 1
    fi
done

# Resolve an explicit interpreter relative to the caller, before changing cwd.
model_python=""
if [ -n "${RFPROTEINA_PYTHON:-}" ]; then
    model_python="$(command -v -- "$RFPROTEINA_PYTHON")" || {
        printf '%s\n' 'FAIL: RFPROTEINA_PYTHON must name an executable model Python interpreter.' >&2
        exit 1
    }
    if [ ! -x "$model_python" ] || [ -d "$model_python" ]; then
        printf '%s\n' 'FAIL: RFPROTEINA_PYTHON must name an executable model Python interpreter.' >&2
        exit 1
    fi
    model_python="$(cd "$(dirname "$model_python")" && pwd)/$(basename "$model_python")"
fi

cd -- "$repo_root"
export RFPROTEINA_ROOT="$PWD"
export PYTHONDONTWRITEBYTECODE=1
if [ -n "$model_python" ]; then
    exec "$model_python" "$script_dir/preflight.py" --repo-root "$RFPROTEINA_ROOT" "${data_args[@]}"
elif [ -x "$RFPROTEINA_ROOT/scripts/rfproteina_exec.sh" ]; then
    exec "$RFPROTEINA_ROOT/scripts/rfproteina_exec.sh" training "$script_dir/preflight.py" --repo-root "$RFPROTEINA_ROOT" "${data_args[@]}"
elif [ -x "$RFPROTEINA_ROOT/.venv/bin/python" ]; then
    exec "$RFPROTEINA_ROOT/.venv/bin/python" "$script_dir/preflight.py" --repo-root "$RFPROTEINA_ROOT" "${data_args[@]}"
else
    printf 'FAIL: Model checkout found at %s, but its Python runtime is not installed.\n' "$RFPROTEINA_ROOT" >&2
    printf '%s\n' 'Run the checkout setup or set RFPROTEINA_PYTHON to its installed interpreter.' >&2
    exit 1
fi
