#!/usr/bin/env python3
"""Boltz-2 NIM endpoint resolution shared by the design scripts.

Centralized here so ``boltz2_refold.py`` and ``validate_binders.py`` don't each
carry their own copy of the endpoint logic. The local host/port is overridable
via ``$BOLTZ2_URL`` (e.g. a NIM on another container/host).
"""
from __future__ import annotations

import os

HOSTED_URL = "https://health.api.nvidia.com/v1/biology/mit/boltz2/predict"


def _local_boltz2_url() -> str:
    """Resolve the local NIM endpoint (override via $BOLTZ2_URL)."""
    return os.environ.get("BOLTZ2_URL", "http://localhost:8000/biology/mit/boltz2/predict")


LOCAL_URL = _local_boltz2_url()
