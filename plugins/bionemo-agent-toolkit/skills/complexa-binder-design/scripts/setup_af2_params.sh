#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# Set up AlphaFold2-Multimer params for Complexa's reward-guided search (best-of-n /
# beam-search / fk-steering / mcts). Downloads the public AF2 params (no auth) if
# missing and creates the `params/` subdir layout colabdesign expects.
#
# colabdesign resolves params from BOTH `<AF2_DIR>/params_model_*.npz` AND
# `<AF2_DIR>/params/...`, and `casp_model_names()` does `os.listdir(<AF2_DIR>/params)` —
# so the flat AF2 tar (which extracts `params_model_*.npz` at top level) needs a
# `params/` symlink dir or model enumeration fails. This script creates it.
#
# Usage:
#   bash setup_af2_params.sh [AF2_DIR]
#   # default AF2_DIR = ${COMPLEXA_REPO:-.}/community_models/ckpts/AF2
# Then:  export AF2_DIR=<printed path>
set -euo pipefail

AF2_DIR="${1:-${COMPLEXA_REPO:-.}/community_models/ckpts/AF2}"
TAR_URL="https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar"
mkdir -p "$AF2_DIR"

if ! ls "$AF2_DIR"/params_model_*_multimer_v3.npz >/dev/null 2>&1; then
  echo "Downloading AF2 params (~5 GB, public, no auth) -> $AF2_DIR ..."
  wget -q --show-progress -O "$AF2_DIR/af2.tar" "$TAR_URL"
  echo "Extracting ..."
  tar -xf "$AF2_DIR/af2.tar" -C "$AF2_DIR"
  rm -f "$AF2_DIR/af2.tar"
else
  echo "AF2 params already present in $AF2_DIR"
fi

# Create the params/ subdir colabdesign enumerates, symlinking the flat .npz files.
mkdir -p "$AF2_DIR/params"
( cd "$AF2_DIR/params" && ln -sf ../params_model_*.npz . )
n=$(ls "$AF2_DIR"/params/params_model_*.npz 2>/dev/null | wc -l)
echo "params/ symlinks: $n"

if ! ls "$AF2_DIR"/params/params_model_1_multimer_v3.npz >/dev/null 2>&1; then
  echo "ERROR: multimer_v3 params not found under $AF2_DIR/params" >&2
  exit 1
fi

ABS="$(cd "$AF2_DIR" && pwd)"
echo "AF2 ready. Export this for reward-guided search:"
echo "  export AF2_DIR=$ABS"
