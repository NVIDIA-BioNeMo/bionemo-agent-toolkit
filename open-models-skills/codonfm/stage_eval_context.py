# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Refresh the identical public source fixtures given to both Harbor conditions.

Run after changing src/, Dockerfile, run_dev.sh, or requirements.txt. These
small deterministic ZIPs contain code, not skills, answers, weights, or deps.
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_context():
    paths = sorted((ROOT / "src").rglob("*.py"))
    paths += [ROOT / name for name in ("Dockerfile", "run_dev.sh", "requirements.txt")]
    contents = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}
    contents["source-manifest.json"] = (json.dumps({
        "repository": "https://github.com/NVIDIA-BioNeMo/CodonFM",
        "purpose": "Public source snapshot for input preparation and API inspection; no weights or dependencies included",
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())},
    }, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def main():
    data = build_context()
    for skill in sorted((ROOT / "skills").glob("codonfm-*")):
        dest = skill / "evals/files/codonfm_source.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"{dest.relative_to(ROOT)}: {len(data)} bytes")


if __name__ == "__main__":
    main()
