#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# Fetch the Dunbrack ipSAE script (MIT) into vendor/ipsae/ipsae.py.
# ipSAE is third-party and NOT redistributed with this skill; this script pulls it
# from the canonical source so validate_binders.py can compute ipSAE_min.
#
# Source : https://github.com/dunbracklab/IPSAE  (ipsae.py)
# License: MIT (Roland L. Dunbrack Jr., Fox Chase Cancer Center)
# Paper  : Dunbrack, bioRxiv 2025.02.10.637595
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$SKILL_DIR/vendor/ipsae/ipsae.py"
mkdir -p "$(dirname "$DEST")"

for ref in main master; do
  URL="https://raw.githubusercontent.com/dunbracklab/IPSAE/${ref}/ipsae.py"
  echo "Trying $URL ..."
  if curl -fsSL "$URL" -o "$DEST"; then
    echo "Saved ipSAE -> $DEST"
    echo "Remember: ipSAE is MIT-licensed; keep vendor/ipsae/README.md attribution."
    exit 0
  fi
done

echo "ERROR: could not download ipsae.py. Download it manually from" >&2
echo "       https://github.com/dunbracklab/IPSAE and place it at $DEST" >&2
exit 1
