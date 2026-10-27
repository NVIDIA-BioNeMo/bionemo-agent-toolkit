"""Offline regressions for executable, config, output and HTTP boundaries."""
import argparse
import contextlib
import hashlib
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import boltz2_endpoint as endpoint
import boltz2_refold as refold
import complexa_design as design
import execution
import pipeline
import refold_batch
import validate_binders as validator


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "checkout"
    (root / "configs").mkdir(parents=True)
    (root / design.DEFAULT_CONFIG).write_text("{}\n")
    binary = root / ".venv/bin/complexa"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    return root


def args(repo, **changes):
    values = dict(mode="generate", cli_bin=str(repo / ".venv/bin/complexa"),
                  config=design.DEFAULT_CONFIG, task_name="target_1", run_name="round-1",
                  algorithm="best-of-n", num_samples=8, seed=0, gen_njobs=1, eval_njobs=1,
                  ckpt_path=None, ckpt_name=None, autoencoder_ckpt_path=None,
                  override=[], af2_bypass=False, out=None, timeout=30)
    return argparse.Namespace(**(values | changes))


@pytest.mark.parametrize("change", [
    {"cli_bin": "/bin/sh"}, {"config": "../outside.yaml"},
    {"run_name": "../../outside"}, {"task_name": "${oc.env:HOME}"},
    {"algorithm": "best-of-n,single-pass"}, {"num_samples": -1},
    {"seed": -1}, {"gen_njobs": 0}, {"eval_njobs": 129},
    {"override": ["++generation._target_=os.system"]},
    {"override": ["++seed=${oc.env:SEED}"]},
    {"override": ["++seed=1,2"]},
    {"ckpt_name": "../other.ckpt"},
    {"ckpt_path": "${oc.env:CKPT}"},
    {"timeout": 86401},
])
def test_invalid_generation_stops_before_execution(repo, change):
    with mock.patch.object(design, "repo_root", return_value=repo), \
         mock.patch.object(design.subprocess, "run") as run:
        with pytest.raises((ValueError, FileNotFoundError)):
            design.cmd_run(args(repo, **change))
    run.assert_not_called()


def test_valid_command_and_bypass_preserve_literal_checkpoint_path(repo):
    command = design.build_argv(args(repo, af2_bypass=True, ckpt_path="two words",
                                      override=["++seed=17"]), repo)
    assert command[:3] == [str(repo / ".venv/bin/complexa"), "generate", str(repo / design.DEFAULT_CONFIG)]
    assert f'++ckpt_path="{repo}/two words"' in command
    assert command[-3:] == ["++seed=17", "++generation.search.algorithm=single-pass",
                            "~generation.reward_model.reward_models.af2folding"]


def test_symlinked_executable_and_config_cannot_escape_installation(repo, tmp_path):
    binary = repo / ".venv/bin/complexa"
    binary.unlink()
    binary.symlink_to(sys.executable)
    with pytest.raises(ValueError):
        execution.complexa_executable(str(binary), repo)
    outside = tmp_path / "outside.yaml"
    outside.write_text("{}")
    (repo / "configs/escape.yaml").symlink_to(outside)
    with pytest.raises(ValueError):
        execution.complexa_config("configs/escape.yaml", repo)


def test_generation_copies_only_inference_files_with_fixed_argv(repo, tmp_path):
    source = repo / "inference/run/design.pdb"
    source.parent.mkdir(parents=True)
    source.write_text("END\n")
    output = tmp_path / "results"
    with mock.patch.object(design, "repo_root", return_value=repo), \
         mock.patch.object(design.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as run:
        design.cmd_run(args(repo, out=str(output)))
    assert (output / "inference/design.pdb").read_text() == "END\n"
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 30
    outside = tmp_path / "other.pdb"
    outside.write_text("private data")
    (source.parent / "escape.pdb").symlink_to(outside)
    with pytest.raises(ValueError):
        design.discover_complex_pdbs(repo)


def test_copy_rejects_destination_symlink(repo, tmp_path):
    (repo / "inference").mkdir()
    (repo / "inference/design.pdb").write_text("END\n")
    output = tmp_path / "results"
    output.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (output / "inference").symlink_to(outside, target_is_directory=True)
    with mock.patch.object(design, "repo_root", return_value=repo), \
         mock.patch.object(design.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as run:
        with pytest.raises(ValueError):
            design.cmd_run(args(repo, out=str(output)))
    run.assert_not_called()
    assert list(outside.iterdir()) == []


def test_registration_rejects_traversal_and_asset_symlinks(repo, tmp_path):
    source = tmp_path / "target.pdb"
    source.write_text("END\n")
    with mock.patch.object(pipeline, "_complexa_repo", return_value=repo):
        with pytest.raises(ValueError):
            pipeline.register_complexa_target("../../outside", source, [])
        assets = repo / "assets"
        assets.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError):
            pipeline.register_complexa_target("target", source, [])
    assert not (tmp_path / "target_data").exists()


def test_legacy_submit_validates_environment_binary_before_execution(repo):
    with mock.patch.object(pipeline, "_complexa_repo", return_value=repo), \
         mock.patch.object(pipeline, "COMPLEXA_BIN", "/bin/sh"), \
         mock.patch.object(pipeline, "_run") as run:
        with pytest.raises(ValueError):
            list(pipeline.submit_complexa("target", "run"))
    run.assert_not_called()


@pytest.mark.parametrize("options", [
    ["--validate", "/tmp/untrusted_validator.py"],
    ["--url", "file:///tmp/endpoint"],
    ["--endpoint", "hosted", "--url", "https://example.com/predict"],
    ["--max-retries", "100"], ["--throttle", "nan"],
])
def test_refold_rejects_invalid_settings_before_prediction_or_writes(tmp_path, options):
    argv = ["boltz2_refold.py", "--run-dir", str(tmp_path / "run"), "--pdbs", "input.pdb",
            "--target-chain", "A", "--binder-chain", "B", "--endpoint", "local", *options]
    with mock.patch.object(sys, "argv", argv), mock.patch.object(refold, "boltz2_holo") as call:
        with pytest.raises(SystemExit) as error:
            refold.main()
    assert error.value.code == 2
    call.assert_not_called()
    assert not (tmp_path / "run").exists()


def test_hosted_auth_and_redirect_boundaries():
    for url in ("http://health.api.nvidia.com/predict", "https://health.api.nvidia.com.evil.invalid",
                "https://user:secret@health.api.nvidia.com/predict", "https://health.api.nvidia.com:444/predict"):
        with pytest.raises(ValueError):
            endpoint.validate_endpoint(url, hosted=True)
    assert endpoint.validate_endpoint(endpoint.HOSTED_URL, hosted=True) == endpoint.HOSTED_URL
    assert endpoint.validate_endpoint("http://nim:8000/predict") == "http://nim:8000/predict"
    req = urllib.request.Request(endpoint.HOSTED_URL)
    with pytest.raises(urllib.error.HTTPError):
        endpoint._NoRedirect().redirect_request(req, None, 302, "Moved", {}, "https://other.invalid")


def test_ipsae_tampering_stops_before_execution_or_scoring_writes(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = tmp_path / "vendor/ipsae/ipsae.py"
    script.parent.mkdir(parents=True)
    script.write_text("unexpected code\n")
    work = tmp_path / "work"
    work.mkdir()
    with mock.patch.object(validator, "__file__", str(scripts / "validate_binders.py")), \
         mock.patch.object(validator.subprocess, "run") as run:
        with pytest.raises(ValueError, match="pinned"):
            validator.run_ipsae(script, "cif", np.zeros((2, 2)), None, work)
    run.assert_not_called()
    assert list(work.iterdir()) == []


def test_matching_ipsae_uses_fixed_command_and_checks_exit_status(tmp_path):
    script = tmp_path / "vendor/ipsae/ipsae.py"
    script.parent.mkdir(parents=True)
    script.write_text("# synthetic test dependency\n")
    work = tmp_path / "work"
    work.mkdir()
    with mock.patch.object(validator, "__file__", str(tmp_path / "scripts/validate_binders.py")), \
         mock.patch.object(validator, "IPSAE_SHA256", hashlib.sha256(script.read_bytes()).hexdigest()), \
         mock.patch.object(validator.subprocess, "run", return_value=argparse.Namespace(returncode=1, stdout="", stderr="failed")) as run:
        with pytest.raises(RuntimeError):
            validator.run_ipsae(script, "cif", np.zeros((2, 2)), None, work)
    assert run.call_args.args[0][:2] == [sys.executable, str(script)]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 300


@pytest.mark.parametrize("flag,value", [("--pae-cutoff", "0"), ("--dist-cutoff", "101"), ("--contact-cutoff", "nan")])
def test_scoring_rejects_invalid_cutoffs(tmp_path, flag, value):
    with mock.patch.object(sys, "argv", ["validate_binders.py", "--run-dir", str(tmp_path), flag, value]):
        with pytest.raises(SystemExit) as error:
            validator.main()
    assert error.value.code == 2


def test_new_batch_logs_each_derived_file_deletion_and_retains_raw_evidence(tmp_path):
    paths = [tmp_path / "ranked_binders.json", tmp_path / "ranked_binders.csv",
             tmp_path / "validation/validation_scores.json", tmp_path / "validation/validation_scores.csv"]
    raw = tmp_path / "validation/raw/design.json"
    raw.parent.mkdir(parents=True)
    raw.write_text("original evidence")
    for path in paths:
        path.write_text("stale ranking")
    with contextlib.redirect_stderr(io.StringIO()) as output:
        refold_batch.start_batch(tmp_path, ["design"])
    for path in paths:
        assert str(path) in output.getvalue()
        assert not path.exists()
    assert raw.read_text() == "original evidence"
