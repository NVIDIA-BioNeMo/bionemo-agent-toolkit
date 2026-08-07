#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# One-shot readiness check for the standalone (no-NIM) complexa-binder-design skill.
# Verifies the complexa CLI, repo/checkpoints, Python deps, ipSAE, AF2 status, and the
# validation endpoint env. Non-fatal: prints a checklist and a final verdict.
set +e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
COMPLEXA_BIN="${COMPLEXA_BIN:-complexa}"
ok=0; warn=0; err=0
pass(){ echo "  [OK]   $1"; ok=$((ok+1)); }
note(){ echo "  [warn] $1"; warn=$((warn+1)); }
fail(){ echo "  [FAIL] $1"; err=$((err+1)); }

echo "=== complexa-binder-design setup check ==="

# 1. complexa CLI
if command -v "$COMPLEXA_BIN" >/dev/null 2>&1; then pass "complexa CLI: $(command -v "$COMPLEXA_BIN")"
else fail "complexa CLI not found (set COMPLEXA_BIN or activate the Proteina-Complexa venv)"; fi

# 2. repo + config + checkpoints
if [ -n "$COMPLEXA_REPO" ] && [ -d "$COMPLEXA_REPO" ]; then
  pass "COMPLEXA_REPO=$COMPLEXA_REPO"
  cfg="${COMPLEXA_CONFIG:-configs/search_binder_local_pipeline.yaml}"
  [ -f "$COMPLEXA_REPO/$cfg" ] && pass "pipeline config: $cfg" || fail "pipeline config missing: $cfg"
  if ls "$COMPLEXA_REPO"/ckpts/complexa.ckpt >/dev/null 2>&1 && ls "$COMPLEXA_REPO"/ckpts/complexa_ae.ckpt >/dev/null 2>&1; then
    pass "checkpoints: complexa.ckpt + complexa_ae.ckpt"
  else note "checkpoints not in <repo>/ckpts (run 'complexa download --complexa-all' or set ++ckpt_path)"; fi
else fail "COMPLEXA_REPO unset or not a directory (needed for generation)"; fi

# 3. Python deps
$PY - <<'PY' 2>/dev/null && pass "python deps: numpy + gemmi + pyyaml" || fail "missing python deps (pip/uv pip install numpy gemmi pyyaml)"
import numpy, gemmi, yaml
PY

# 4. ipSAE vendored
[ -f "$SKILL_DIR/vendor/ipsae/ipsae.py" ] && pass "ipSAE present (vendor/ipsae/ipsae.py)" \
  || note "ipSAE not fetched yet — run: bash scripts/fetch_ipsae.sh"

# 5. GPU / CUDA (best-effort)
$PY - <<'PY' 2>/dev/null
import sys
try:
    import torch
    print("  [OK]   CUDA available" if torch.cuda.is_available() else "  [warn] torch present but CUDA not available")
except Exception:
    print("  [warn] torch not importable here (fine if you run complexa in its own venv)")
PY

# 6. AF2 reward status
if [ -n "$AF2_DIR" ] && [ -d "$AF2_DIR" ]; then pass "AF2_DIR set ($AF2_DIR) — reward-guided search + AF2 pre-gate enabled"
else note "AF2_DIR not set — use single-pass + AF2 bypass (~generation.reward_model.reward_models.af2folding); selection falls to Boltz2"; fi

# 7. analyze-stage tools (optional)
for t in FOLDSEEK_EXEC SC_EXEC DSSP_EXEC; do
  v="${!t}"; { [ -n "$v" ] && [ -x "$v" ]; } && pass "$t=$v" || note "$t not set (only needed for full 'complexa design' analyze/diversity)"
done

# 8. validation endpoint
if [ -n "$NVIDIA_API_KEY" ] || [ -n "$NGC_API_KEY" ]; then pass "NVIDIA_API_KEY/NGC_API_KEY set (hosted Boltz2/OF3 + NGC)"
else note "no NVIDIA_API_KEY/NGC_API_KEY — use a local Boltz2 NIM (--endpoint local) for Stage 3"; fi

echo "----------------------------------------------"
echo "  OK=$ok  warn=$warn  FAIL=$err"
[ "$err" -eq 0 ] && echo "  => READY (warnings are optional features)" || echo "  => NOT READY — fix [FAIL] items above"
exit 0
