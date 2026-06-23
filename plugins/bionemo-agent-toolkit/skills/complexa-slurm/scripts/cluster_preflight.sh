#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

# cluster_preflight.sh — SLURM-aware extension of _shared/scripts/preflight.sh.
#
# Verifies the cluster half of the Proteina-Complexa toolchain: .env Section 5
# variables, SSH reachability, sbatch availability, partition existence,
# optional shared-asset paths. Emits cluster_preflight.json with the same JSON
# shape as preflight.json plus a "cluster" block.
#
# Loads .env using the same approach as slurm_helper.sh / preflight.sh so the
# three stay consistent.
#
# Usage:
#   bash cluster_preflight.sh                  # writes ./cluster_preflight.json + prints
#   bash cluster_preflight.sh --quiet          # writes only
#   bash cluster_preflight.sh --out PATH       # writes to PATH instead
#   bash cluster_preflight.sh --help

set -euo pipefail

# Bash 4+ guard (uses `declare -A` below; macOS bash 3.2 errors otherwise).
if (( ${BASH_VERSINFO[0]:-0} < 4 )); then
    echo "cluster_preflight.sh needs bash 4+; this is bash ${BASH_VERSION:-3.x}." >&2
    echo "  brew install bash && /opt/homebrew/bin/bash $0 $*" >&2
    exit 3
fi

QUIET=0
OUT="./cluster_preflight.json"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet) QUIET=1; shift ;;
        --out)   OUT="${2:-}"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown flag: $1" >&2; usage; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers (mirrored from _shared/scripts/preflight.sh)
# ---------------------------------------------------------------------------

json_str() {
    local v="${1-}"
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys; sys.stdout.write(json.dumps(sys.argv[1]))' "$v"
    else
        printf '"%s"' "$(printf '%s' "$v" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
    fi
}
json_bool() { [[ "${1:-false}" == "true" ]] && printf 'true' || printf 'false'; }

# ---------------------------------------------------------------------------
# Source .env in a subshell, pull the CLUSTER_* keys we need
# ---------------------------------------------------------------------------

ENV_FILE="$PWD/.env"
ENV_LOADED=false
MISSING=()

declare -A CV=(
    [CLUSTER_USER]="" [CLUSTER_HOST]="" [CLUSTER_HOST_DC]="" [CLUSTER_SSH_KEY]=""
    [CLUSTER_ACCOUNT]="" [CLUSTER_PARTITION]="" [CLUSTER_RUNTIME]=""
    [CLUSTER_ROOT_REMOTE]="" [CLUSTER_DATA_PATH]="" [CLUSTER_CACHE_DIR]=""
    [CLUSTER_SHARED_MODELS_PATH]="" [CLUSTER_CKPT_PATH]=""
    [CLUSTER_CONTAINER_IMAGE]="" [CLUSTER_CONTAINER_WORKSPACE]=""
    [CLUSTER_DOCKER_MOUNTS]="" [CLUSTER_UV_VENV]=""
)

if [[ -f "$ENV_FILE" ]]; then
    ENV_LOADED=true
    set +u
    DUMP=$(bash -c '
        set -a
        # shellcheck disable=SC1090
        source "'"$ENV_FILE"'" 2>/dev/null || true
        set +a
        for k in CLUSTER_USER CLUSTER_HOST CLUSTER_HOST_DC CLUSTER_SSH_KEY \
                 CLUSTER_ACCOUNT CLUSTER_PARTITION CLUSTER_RUNTIME \
                 CLUSTER_ROOT_REMOTE CLUSTER_DATA_PATH CLUSTER_CACHE_DIR \
                 CLUSTER_SHARED_MODELS_PATH CLUSTER_CKPT_PATH \
                 CLUSTER_CONTAINER_IMAGE CLUSTER_CONTAINER_WORKSPACE \
                 CLUSTER_DOCKER_MOUNTS CLUSTER_UV_VENV; do
            printf "%s\t%s\n" "$k" "${!k-}"
        done
    ' 2>/dev/null || true)
    set -u
    while IFS=$'\t' read -r k v; do
        [[ -n "$k" ]] && CV[$k]="$v"
    done <<<"$DUMP"
fi

# Required for any cluster launch (binder/monomer/train, default SSH submit path)
for req in CLUSTER_USER CLUSTER_HOST CLUSTER_ACCOUNT CLUSTER_PARTITION \
           CLUSTER_ROOT_REMOTE CLUSTER_DATA_PATH CLUSTER_RUNTIME; do
    [[ -z "${CV[$req]:-}" ]] && MISSING+=("$req")
done

# Runtime-specific required vars
case "${CV[CLUSTER_RUNTIME]:-}" in
    docker)
        [[ -z "${CV[CLUSTER_CONTAINER_IMAGE]:-}" ]]      && MISSING+=("CLUSTER_CONTAINER_IMAGE")
        [[ -z "${CV[CLUSTER_CONTAINER_WORKSPACE]:-}" ]]  && MISSING+=("CLUSTER_CONTAINER_WORKSPACE")
        ;;
    uv)
        [[ -z "${CV[CLUSTER_UV_VENV]:-}" ]]   && MISSING+=("CLUSTER_UV_VENV")
        [[ -z "${CV[CLUSTER_CACHE_DIR]:-}" ]] && MISSING+=("CLUSTER_CACHE_DIR")
        ;;
    *) ;;  # unknown / empty runtime — already flagged by required-block above
esac

MISSING_JSON="[]"
if [[ ${#MISSING[@]} -gt 0 ]]; then
    parts=()
    for m in "${MISSING[@]}"; do parts+=("$(json_str "$m")"); done
    MISSING_JSON="[$(IFS=,; echo "${parts[*]}")]"
fi

# ---------------------------------------------------------------------------
# Build SSH options (mirrors load_config in slurm_helper.sh)
# ---------------------------------------------------------------------------

SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null"
KEY="${CV[CLUSTER_SSH_KEY]:-}"
KEY="${KEY/#\~/$HOME}"
if [[ -n "$KEY" && -f "$KEY" ]]; then
    SSH_OPTS="$SSH_OPTS -i $KEY -o IdentitiesOnly=yes"
fi

# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

SSH_OK=false
SBATCH_OK=false
SBATCH_PATH=""
PARTITION_OK=false
PARTITION_NODES=""
CKPT_REMOTE_OK="null"
SHARED_REMOTE_OK="null"

if [[ -n "${CV[CLUSTER_USER]:-}" && -n "${CV[CLUSTER_HOST]:-}" ]]; then
    TARGET="${CV[CLUSTER_USER]}@${CV[CLUSTER_HOST]}"
    if ssh $SSH_OPTS "$TARGET" true >/dev/null 2>&1; then
        SSH_OK=true
        # sbatch present?
        SBATCH_PATH=$(ssh $SSH_OPTS "$TARGET" 'command -v sbatch' 2>/dev/null || true)
        [[ -n "$SBATCH_PATH" ]] && SBATCH_OK=true
        # Partition exists?
        if [[ -n "${CV[CLUSTER_PARTITION]:-}" ]]; then
            PART_OUT=$(ssh $SSH_OPTS "$TARGET" "sinfo -p ${CV[CLUSTER_PARTITION]} -h" 2>/dev/null || true)
            if [[ -n "$PART_OUT" ]]; then
                PARTITION_OK=true
                PARTITION_NODES=$(printf '%s\n' "$PART_OUT" | wc -l | tr -d ' ')
            fi
        fi
        # Optional shared paths
        if [[ -n "${CV[CLUSTER_CKPT_PATH]:-}" ]]; then
            ssh $SSH_OPTS "$TARGET" "[ -d '${CV[CLUSTER_CKPT_PATH]}' ]" 2>/dev/null \
                && CKPT_REMOTE_OK=true || CKPT_REMOTE_OK=false
        fi
        if [[ -n "${CV[CLUSTER_SHARED_MODELS_PATH]:-}" ]]; then
            ssh $SSH_OPTS "$TARGET" "[ -d '${CV[CLUSTER_SHARED_MODELS_PATH]}' ]" 2>/dev/null \
                && SHARED_REMOTE_OK=true || SHARED_REMOTE_OK=false
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Git SHA (local)
# ---------------------------------------------------------------------------

GIT_SHA="unknown"
if command -v git >/dev/null 2>&1; then
    GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
fi

# ---------------------------------------------------------------------------
# Assemble JSON
# ---------------------------------------------------------------------------

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

ENV_JSON=$(printf '{".env_loaded":%s,".env_path":%s,"missing_required":%s}' \
    "$(json_bool "$ENV_LOADED")" "$(json_str "$ENV_FILE")" "$MISSING_JSON")

VARS_JSON="{"
first=1
for k in CLUSTER_USER CLUSTER_HOST CLUSTER_HOST_DC CLUSTER_ACCOUNT CLUSTER_PARTITION \
         CLUSTER_RUNTIME CLUSTER_ROOT_REMOTE CLUSTER_DATA_PATH CLUSTER_CACHE_DIR \
         CLUSTER_SHARED_MODELS_PATH CLUSTER_CKPT_PATH CLUSTER_CONTAINER_IMAGE \
         CLUSTER_CONTAINER_WORKSPACE CLUSTER_DOCKER_MOUNTS CLUSTER_UV_VENV \
         CLUSTER_SSH_KEY; do
    [[ $first -eq 0 ]] && VARS_JSON+=","
    VARS_JSON+="$(json_str "$k"):$(json_str "${CV[$k]:-}")"
    first=0
done
VARS_JSON+="}"

# CKPT_REMOTE_OK / SHARED_REMOTE_OK are null/true/false text already
CLUSTER_JSON=$(printf '{"ssh_ok":%s,"sbatch_ok":%s,"sbatch_path":%s,"partition_ok":%s,"partition_node_count":%s,"ckpt_path_exists":%s,"shared_models_path_exists":%s,"vars":%s}' \
    "$(json_bool "$SSH_OK")" \
    "$(json_bool "$SBATCH_OK")" \
    "$(json_str "$SBATCH_PATH")" \
    "$(json_bool "$PARTITION_OK")" \
    "${PARTITION_NODES:-null}" \
    "$CKPT_REMOTE_OK" \
    "$SHARED_REMOTE_OK" \
    "$VARS_JSON")

DOC=$(printf '{"timestamp":%s,"env":%s,"cluster":%s,"git_sha":%s}' \
    "$(json_str "$TS")" "$ENV_JSON" "$CLUSTER_JSON" "$(json_str "$GIT_SHA")")

PRETTY="$DOC"
if command -v jq >/dev/null 2>&1; then
    PRETTY=$(printf '%s' "$DOC" | jq . 2>/dev/null || printf '%s' "$DOC")
elif command -v python3 >/dev/null 2>&1; then
    PRETTY=$(printf '%s' "$DOC" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))' 2>/dev/null || printf '%s' "$DOC")
fi

printf '%s\n' "$PRETTY" > "$OUT"
[[ "$QUIET" == "1" ]] || printf '%s\n' "$PRETTY"
