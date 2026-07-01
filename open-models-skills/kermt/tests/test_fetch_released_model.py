# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/fetch_released_model.py.

These mock `huggingface_hub.snapshot_download` (or simulate its absence), so
they need no network and run every time — they are NOT marked `slow`. The real
download is exercised separately by the opt-in `slow` e2e tests.

Covers: idempotent reuse, successful download, incomplete-bundle error,
stale-image (huggingface_hub missing) error, and the CLI + config-load path.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
frm = importlib.import_module("fetch_released_model")

CKPT = "kermt_contrastive_v2.0.pt"
VOCAB = [
    "pretrain_atom_vocab.json",
    "pretrain_bond_vocab.json",
    "pretrain_smiles_vocab.pkl",
]


def _make_bundle(d: Path, names: list[str]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"x")


def test_reuse_complete_bundle_no_download(tmp_path, monkeypatch):
    """A complete bundle is reused — snapshot_download must NOT be called."""
    _make_bundle(tmp_path, [CKPT, *VOCAB])

    def _boom(**kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("snapshot_download should not be called on reuse")

    monkeypatch.setattr("huggingface_hub.snapshot_download", _boom, raising=False)

    res = frm.fetch(
        out=tmp_path,
        repo_id="nvidia/NV-KERMT-70M-v2",
        revision="abc",
        ckpt_name=CKPT,
        vocab_files=VOCAB,
    )
    assert res["ok"] is True
    assert res["reused"] is True
    assert res["ckpt"] == str(tmp_path / CKPT)
    assert res["vocab_dir"] == str(tmp_path)
    assert set(res["files_present"]) == {CKPT, *VOCAB}


def test_download_populates_bundle(tmp_path, monkeypatch):
    """When the bundle is absent, snapshot_download is called and its output
    is validated and reported (reused: false)."""
    out = tmp_path / "NV-KERMT-70M-v2"
    called = {}

    def _fake(repo_id, revision, local_dir):
        called["repo_id"] = repo_id
        called["revision"] = revision
        _make_bundle(Path(local_dir), [CKPT, *VOCAB])

    monkeypatch.setattr("huggingface_hub.snapshot_download", _fake, raising=False)

    res = frm.fetch(
        out=out,
        repo_id="nvidia/NV-KERMT-70M-v2",
        revision="deadbeef",
        ckpt_name=CKPT,
        vocab_files=VOCAB,
    )
    assert res["ok"] is True
    assert res["reused"] is False
    assert called == {"repo_id": "nvidia/NV-KERMT-70M-v2", "revision": "deadbeef"}
    assert res["ckpt_bytes"] == 1  # the fake wrote 1 byte


def test_incomplete_download_errors(tmp_path, monkeypatch):
    """If the download leaves a vocab file missing, fetch reports ok: false
    naming the missing file — it does not silently succeed."""

    def _fake(repo_id, revision, local_dir):
        _make_bundle(
            Path(local_dir), [CKPT, VOCAB[0], VOCAB[1]]
        )  # smiles vocab missing

    monkeypatch.setattr("huggingface_hub.snapshot_download", _fake, raising=False)

    res = frm.fetch(
        out=tmp_path,
        repo_id="r",
        revision="v",
        ckpt_name=CKPT,
        vocab_files=VOCAB,
    )
    assert res["ok"] is False
    assert any(VOCAB[2] in e for e in res["errors"])


def test_missing_huggingface_hub_gives_rebuild_hint(tmp_path, monkeypatch):
    """A stale image without huggingface_hub yields a clean, actionable error
    pointing at kermt-setup — not a traceback."""
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # forces ImportError

    res = frm.fetch(
        out=tmp_path,
        repo_id="r",
        revision="v",
        ckpt_name=CKPT,
        vocab_files=VOCAB,
    )
    assert res["ok"] is False
    assert any("kermt-setup" in e for e in res["errors"])
    assert any("huggingface_hub" in e for e in res["errors"])


def test_cli_reuse_path_via_subprocess(tmp_path, run_agent_script):
    """End-to-end through the CLI + config load: a pre-populated bundle is
    reused and the script exits 0 with valid JSON."""
    _make_bundle(tmp_path, [CKPT, *VOCAB])
    code, payload = run_agent_script("fetch_released_model.py", "--out", str(tmp_path))
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["reused"] is True
    # config-derived defaults flowed through
    assert payload["repo_id"] == "nvidia/NV-KERMT-70M-v2"
    assert payload["ckpt_name"] == CKPT


def test_config_pin_matches_expected():
    """The shipped config pins the released repo + revision + bundle filenames."""
    cfg = json.loads(
        (SCRIPTS_DIR.parent / "config" / "released_model.json").read_text()
    )
    assert cfg["repo_id"] == "nvidia/NV-KERMT-70M-v2"
    assert cfg["ckpt_name"] == CKPT
    assert set(cfg["vocab_files"]) == set(VOCAB)
    assert len(cfg["revision"]) == 40  # pinned to a full commit sha
