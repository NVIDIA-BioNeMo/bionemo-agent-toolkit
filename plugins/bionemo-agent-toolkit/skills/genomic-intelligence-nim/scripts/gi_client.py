"""Client for the Genomic Intelligence API.

Self-contained — this module has no dependencies beyond ``requests`` and is
imported by ``gi_predict.py`` (same directory). It wraps the hosted
``/v1/tasks/{task}/predict`` contract for all six DNA-sequence tasks
(promoter, splice, enhancer, chromatin, expression, annotation).

Auth resolution order:
1. Explicit ``api_key=`` constructor arg (``--api-key`` on the CLI).
2. ``GI_API_KEY`` environment variable.

If neither is supplied, ``resolve_api_key`` raises ``RuntimeError`` with
onboarding instructions. Request a partner key at
contact@genomicintelligence.ai, then ``export GI_API_KEY=gi_…``.

Base URL: ``GI_BASE_URL`` env, default ``https://api.genomicintelligence.ai``.

Contract reference: https://docs.genomicintelligence.ai
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://api.genomicintelligence.ai"

MISSING_KEY_MESSAGE = (
    "GI_API_KEY is not set. This skill calls the hosted Genomic "
    "Intelligence API (https://api.genomicintelligence.ai) and requires a "
    "partner bearer key.\n\n"
    "Request a key at contact@genomicintelligence.ai, then:\n"
    "    export GI_API_KEY=gi_yourkeyhere\n\n"
    "See references/authentication.md for details."
)


class GIError(RuntimeError):
    """Non-2xx response from the API. Mirrors the ``{error}`` envelope."""

    def __init__(self, status: int, body: Dict[str, Any]):
        err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
        self.status = status
        self.code = err.get("code", "http_error")
        self.message = err.get("message", "")
        self.request_id = err.get("request_id")
        self.details = err.get("details")
        super().__init__(
            f"[{status} {self.code}] {self.message} (request_id={self.request_id})"
        )


def resolve_api_key(explicit: Optional[str] = None) -> str:
    """Apply the auth resolution order documented at module top.

    Raises ``RuntimeError`` with onboarding instructions if no key is found.
    """
    if explicit:
        return explicit
    env = os.environ.get("GI_API_KEY")
    if env:
        return env
    raise RuntimeError(MISSING_KEY_MESSAGE)


class Client:
    """Thin synchronous client for /v1/tasks/{task}/predict."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = resolve_api_key(api_key)
        self.base_url = (
            base_url or os.environ.get("GI_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "BioNeMo-GI-Skill/0.1.0",
            }
        )

    def _check(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            body = resp.json()
        except ValueError:
            body = {"error": {"code": "non_json", "message": resp.text[:200]}}
        if not resp.ok:
            raise GIError(resp.status_code, body)
        return body

    def health(self) -> Dict[str, Any]:
        r = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
        return self._check(r)

    def predict(
        self,
        task: str,
        sequence: str,
        sequence_name: str = "sequence",
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"sequence": sequence, "sequence_name": sequence_name}
        if model is not None:
            body["model"] = model
        if options is not None:
            body["options"] = options
        r = self._session.post(
            f"{self.base_url}/v1/tasks/{task}/predict",
            json=body,
            timeout=self.timeout,
        )
        return self._check(r)

    def submit_async(
        self,
        task: str,
        sequence: str,
        sequence_name: str = "sequence",
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        body: Dict[str, Any] = {"sequence": sequence, "sequence_name": sequence_name}
        if model is not None:
            body["model"] = model
        if options is not None:
            body["options"] = options
        r = self._session.post(
            f"{self.base_url}/v1/tasks/{task}/predict",
            headers={"Prefer": "respond-async"},
            json=body,
            timeout=self.timeout,
        )
        body = self._check(r)
        return body["data"]["job_id"]

    def get_job(self, job_id: str) -> requests.Response:
        return self._session.get(
            f"{self.base_url}/v1/tasks/jobs/{job_id}", timeout=self.timeout
        )

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        max_wait: float = 30 * 60,
        on_progress=None,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + max_wait
        while True:
            r = self.get_job(job_id)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 202:
                if on_progress is not None:
                    try:
                        on_progress((r.json().get("data") or {}).get("progress") or {})
                    except Exception:
                        pass
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"job {job_id} did not finish within {max_wait}s"
                    )
                time.sleep(poll_interval)
                continue
            try:
                body = r.json()
            except ValueError:
                body = {"error": {"code": "non_json", "message": r.text[:200]}}
            raise GIError(r.status_code, body)


def read_fasta(path) -> Tuple[str, str]:
    """Tiny FASTA parser (single record). Returns (sequence_name, sequence).

    Concatenates all non-header lines; uppercases; strips whitespace and
    non-ACGTN characters. Sufficient for the bundled demo fixtures; users
    with multi-record FASTA should pass a single record at a time.
    """
    name = None
    seq_parts: list[str] = []
    with open(Path(path)) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is None:
                    name = line[1:].split()[0] or "sequence"
                continue
            seq_parts.append("".join(c for c in line.upper() if c in "ACGTN"))
    seq = "".join(seq_parts)
    return name or "sequence", seq
