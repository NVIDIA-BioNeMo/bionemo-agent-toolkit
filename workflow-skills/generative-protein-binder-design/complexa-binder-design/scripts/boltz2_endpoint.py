#!/usr/bin/env python3
"""Boltz-2 NIM endpoint resolution shared by the design scripts.

Centralized here so ``boltz2_refold.py`` and ``validate_binders.py`` don't each
carry their own copy of the endpoint logic. The local host/port is overridable
via ``$BOLTZ2_URL`` (e.g. a NIM on another container/host).

Usage: import validate_endpoint/open_prediction; no CLI.
Arguments: URL, hosted mode, request and timeout.
Output: validated URL or HTTP response; raises ValueError/HTTPError on rejection.
Exit codes: handled by the calling prediction CLI.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

HOSTED_URL = "https://health.api.nvidia.com/v1/biology/mit/boltz2/predict"


def _local_boltz2_url() -> str:
    """Resolve the local NIM endpoint (override via $BOLTZ2_URL)."""
    return os.environ.get("BOLTZ2_URL", "http://localhost:8000/biology/mit/boltz2/predict")


LOCAL_URL = _local_boltz2_url()


def validate_endpoint(url: str, *, hosted: bool = False) -> str:
    """Allow HTTP(S) services; send NVIDIA credentials only to the hosted API."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ("https", "http") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or any(ord(c) <= 32 or ord(c) == 127 for c in url)):
        raise ValueError("Boltz2 URL must be HTTP(S) with a host and without credentials, whitespace or fragments")
    if hosted and (parsed.scheme != "https" or parsed.hostname != "health.api.nvidia.com"
                   or parsed.port not in (None, 443)):
        raise ValueError("hosted credentials may only be sent to https://health.api.nvidia.com; use local mode for your own service")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Boltz2 redirects are disabled", headers, fp)


def open_prediction(request: urllib.request.Request, timeout: int):
    """Do not forward sequences or bearer credentials through HTTP redirects."""
    validate_endpoint(request.full_url, hosted=request.has_header("Authorization"))
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)
