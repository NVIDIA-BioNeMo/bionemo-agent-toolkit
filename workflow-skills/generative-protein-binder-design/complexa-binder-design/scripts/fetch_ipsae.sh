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

# Update revision and digest together after reviewing the upstream change.
IPSAE_REVISION=6174cf9e71cb1bd660cc805856a18c4871a6dec3
IPSAE_SHA256=10cf9b08c68c91e06cb28526cf2026f47a3980c9048fd3226d13e3304eaf1c27
URL="https://raw.githubusercontent.com/dunbracklab/IPSAE/${IPSAE_REVISION}/ipsae.py"
DOWNLOAD="$(mktemp "${DEST}.XXXXXX")"
trap 'rm -f "$DOWNLOAD"' EXIT
curl -fsSL --connect-timeout 15 --max-time 120 "$URL" -o "$DOWNLOAD"
printf '%s  %s\n' "$IPSAE_SHA256" "$DOWNLOAD" | sha256sum --check --status
mv "$DOWNLOAD" "$DEST"
echo "Saved verified ipSAE ($IPSAE_REVISION) -> $DEST"
echo "ipSAE is MIT-licensed; keep vendor/ipsae/README.md attribution."
