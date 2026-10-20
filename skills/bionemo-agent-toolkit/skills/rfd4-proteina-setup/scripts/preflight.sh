#!/usr/bin/env bash
# Run dependency and checkpoint checks through the same runtime as model commands.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
exec "$repo_root/scripts/rfproteina_exec.sh" training "$script_dir/preflight.py"
