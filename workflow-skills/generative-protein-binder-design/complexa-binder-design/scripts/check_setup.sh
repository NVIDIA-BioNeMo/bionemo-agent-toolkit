#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# One-shot readiness check for the standalone (no-NIM) complexa-binder-design skill.
# Verifies the complexa CLI, repo/checkpoints, Python deps, ipSAE, AF2 status, and the
# validation endpoint env. Exit 1 when required prerequisites are missing.
set +e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
COMPLEXA_BIN="${COMPLEXA_BIN:-complexa}"
prepare_only=0; af2_bypass=0; endpoint=hosted
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prepare-only) prepare_only=1; shift ;;
    --af2-bypass) af2_bypass=1; shift ;;
    --endpoint)
      if [ "$#" -lt 2 ] || { [ "$2" != hosted ] && [ "$2" != local ]; }; then
        echo "--endpoint requires hosted or local" >&2; exit 2
      fi
      endpoint="$2"; shift 2 ;;
    *) echo "Usage: check_setup.sh [--prepare-only] [--af2-bypass] [--endpoint hosted|local]" >&2; exit 2 ;;
  esac
done
ok=0; warn=0; err=0
pass(){ echo "  [OK]   $1"; ok=$((ok+1)); }
note(){ echo "  [warn] $1"; warn=$((warn+1)); }
fail(){ echo "  [FAIL] $1"; err=$((err+1)); }

echo "=== complexa-binder-design setup check ==="

# Preparation does not depend on generation, weights, credentials or a GPU.
"$PY" - <<'PY' 2>/dev/null && pass "python deps: numpy + biotite + pyyaml" || fail "missing python deps (install the pinned requirements.txt)"
import numpy, biotite, yaml
PY
if [ "$prepare_only" -eq 1 ]; then
  if [ "$err" -eq 0 ]; then echo "  => PREPARATION PREREQUISITES PRESENT (no inference checked)"; exit 0; fi
  echo "  => NOT READY for target preparation"; exit 1
fi

# 1. complexa CLI
if command -v "$COMPLEXA_BIN" >/dev/null 2>&1; then pass "complexa CLI: $(command -v "$COMPLEXA_BIN")"
else fail "complexa CLI not found (set COMPLEXA_BIN or activate the Proteina-Complexa venv)"; fi

# 2. repo + config + checkpoints
if [ -n "$COMPLEXA_REPO" ] && [ -d "$COMPLEXA_REPO" ]; then
  pass "COMPLEXA_REPO=$COMPLEXA_REPO"
  cfg="${COMPLEXA_CONFIG:-configs/search_binder_local_pipeline.yaml}"
  [ -f "$COMPLEXA_REPO/$cfg" ] && pass "pipeline config: $cfg" || fail "pipeline config missing: $cfg"
  if [ -s "$COMPLEXA_REPO/ckpts/complexa.ckpt" ] && [ -s "$COMPLEXA_REPO/ckpts/complexa_ae.ckpt" ]; then
    pass "checkpoints: complexa.ckpt + complexa_ae.ckpt"
  else fail "default checkpoints missing/empty in <repo>/ckpts; configure weights before generation (verify any custom checkpoint overrides separately)"; fi
else fail "COMPLEXA_REPO unset or not a directory (needed for generation)"; fi

# 4. ipSAE vendored
[ -f "$SKILL_DIR/vendor/ipsae/ipsae.py" ] && pass "ipSAE present (hash is enforced when scoring)" \
  || fail "ipSAE not fetched yet — run: bash scripts/fetch_ipsae.sh before structural scoring"

# 5. CUDA is required for local generation, not an optional warning. Probe the
# active generation interpreter with a bounded subprocess; never install torch.
"$PY" - <<'PY' >/dev/null 2>&1 && pass "CUDA available in selected Python environment" || fail "CUDA unavailable/unverified; activate the generation environment on a GPU host"
import subprocess, sys
try:
    result = subprocess.run([sys.executable, "-c", "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)"],
                            timeout=15, check=False)
    raise SystemExit(result.returncode)
except (OSError, subprocess.TimeoutExpired):
    raise SystemExit(1)
PY

# 6. AF2 reward status
if [ "$af2_bypass" -eq 1 ]; then note "AF2 bypass selected; pass --af2-bypass to the generation driver too"
elif [ -n "$AF2_DIR" ] && [ -d "$AF2_DIR" ]; then pass "AF2_DIR set (verify configured reward weights before launch)"
else fail "AF2_DIR not set; configure the reward weights or explicitly select --af2-bypass"; fi

# 7. analyze-stage tools (optional)
for t in FOLDSEEK_EXEC SC_EXEC DSSP_EXEC; do
  v="${!t}"; { [ -n "$v" ] && [ -x "$v" ]; } && pass "$t=$v" || note "$t not set (only needed for full 'complexa design' analyze/diversity)"
done

# 8. validation endpoint
if [ "$endpoint" = local ]; then note "local validation selected; endpoint health must be checked before submitting predictions"
elif [ -n "$NVIDIA_API_KEY" ] || [ -n "$NGC_API_KEY" ]; then pass "hosted validation credential present (value not displayed)"
else fail "hosted validation credential missing; configure it or explicitly select --endpoint local"; fi

echo "----------------------------------------------"
echo "  OK=$ok  warn=$warn  FAIL=$err"
if [ "$err" -eq 0 ]; then
  echo "  => PREREQUISITES PRESENT — model configuration and endpoint health still require verification"
  exit 0
fi
echo "  => NOT READY — dependent stages must not run"
exit 1
