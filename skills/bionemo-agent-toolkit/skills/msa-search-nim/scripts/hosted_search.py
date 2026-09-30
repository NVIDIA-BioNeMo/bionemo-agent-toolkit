#!/usr/bin/env python3
"""Run hosted MSA search with bounded retries and save actual A3M results.

Requires requests>=2.28 and NGC_API_KEY (or NVIDIA_API_KEY). The two attempts
use 10-second connect and 300-second read timeouts. A failed hosted service
must remain a failure; this client never substitutes a fabricated alignment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import requests


URL = "https://health.api.nvidia.com/v1/biology/colabfold/msa-search/predict"
DATABASES = ("Uniref30_2302", "colabfold_envdb_202108")
REQUEST_TIMEOUT = (10, 300)
MAX_ATTEMPTS = 2
RETRY_DELAY = 5
RETRYABLE_STATUS = {429, 502, 503, 504}


class SearchError(RuntimeError):
    """The hosted service did not produce the requested alignments."""


def search(sequence: str, databases: list[str], api_key: str) -> dict:
    """Return a validated response, or fail after at most two requests.

    Do not forward server error bodies or requests exceptions to stderr:
    those can contain sensitive request information. No redirects are followed
    with the Authorization header. Database names are also used as filenames,
    so only the documented database names are accepted.
    """
    if not api_key:
        raise SearchError("Set NGC_API_KEY or NVIDIA_API_KEY before running hosted search.")
    if not 1 <= len(sequence) <= 4096 or any(c not in "ACDEFGHIKLMNPQRSTVWYX" for c in sequence):
        raise SearchError("Sequence must contain 1–4096 uppercase amino-acid letters (including X).")
    if not databases or any(db not in DATABASES for db in databases):
        raise SearchError("Select one or both documented databases.")
    payload = {
        "sequence": sequence,
        "databases": list(dict.fromkeys(databases)),
        "e_value": 0.0001,
        "output_alignment_formats": ["a3m"],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    last_error = "No response received."
    for attempt in range(MAX_ATTEMPTS):
        response = None
        try:
            response = requests.post(
                URL, headers=headers, json=payload,
                timeout=REQUEST_TIMEOUT, allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError):
            last_error = "Hosted MSA request timed out or could not connect."
        except requests.RequestException:
            raise SearchError("Hosted MSA request failed before a usable response arrived.") from None
        else:
            try:
                if response.status_code == 200:
                    try:
                        result = response.json()
                    except ValueError:
                        raise SearchError("Hosted MSA returned invalid JSON.") from None
                    validate_alignments(result, payload["databases"])
                    return result
                last_error = f"Hosted MSA returned HTTP {response.status_code}."
                if response.status_code not in RETRYABLE_STATUS:
                    raise SearchError(last_error)
            finally:
                response.close()
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY)
    raise SearchError(
        f"{last_error} Stopped after {MAX_ATTEMPTS} attempts. "
        "No alignment was produced. Check hosted-service availability before retrying."
    )


def validate_alignments(result: object, databases: list[str]) -> None:
    """Require an actual, nonempty A3M result for every requested database."""
    alignments = result.get("alignments") if isinstance(result, dict) else None
    if not isinstance(alignments, dict):
        raise SearchError("Hosted MSA response has no alignments object.")
    for database in databases:
        formats = alignments.get(database)
        a3m = formats.get("a3m") if isinstance(formats, dict) else None
        alignment = a3m.get("alignment") if isinstance(a3m, dict) else None
        if not isinstance(alignment, str) or not alignment.lstrip().startswith(">"):
            raise SearchError(f"Hosted MSA returned no A3M alignment for {database}.")
        if not any(line.strip() and not line.startswith((">", "#")) for line in alignment.splitlines()):
            raise SearchError(f"Hosted MSA returned an empty A3M alignment for {database}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--databases", nargs="+", choices=DATABASES, default=list(DATABASES))
    parser.add_argument("--output-dir", type=Path, required=True, help="A new directory for this request")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("--output-dir must not already exist; use a new path for each request")
    try:
        result = search(
            args.sequence, args.databases,
            os.environ.get("NGC_API_KEY") or os.environ.get("NVIDIA_API_KEY", ""),
        )
        # Create output only after all requested alignments have been validated.
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "response.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        for database in dict.fromkeys(args.databases):
            alignment = result["alignments"][database]["a3m"]["alignment"]
            path = args.output_dir / f"{database}.a3m"
            path.write_text(alignment, encoding="utf-8")
            records = sum(line.startswith(">") for line in alignment.splitlines())
            print(f"{path}: {records} sequences")
    except SearchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("ERROR: Could not save the hosted response to the output directory.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
