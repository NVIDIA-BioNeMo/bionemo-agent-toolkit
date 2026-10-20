"""Setup regression tests; test doubles do not exercise model installation or CUDA."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


SKILL = Path(__file__).resolve().parents[1] / "open-models-skills/rfd4-proteina/rfd4-proteina-setup"
WRAPPER = SKILL / "scripts/preflight.sh"
CHECKER = SKILL / "scripts/preflight.py"


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location("setup_preflight", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def model(tmp_path):
    root = tmp_path / "model checkout"
    (root / "configs").mkdir(parents=True)
    (root / ".project-root").touch()
    (root / "pyproject.toml").write_text('[project]\nname = "rfproteina-test"\n')
    (root / "configs/inference.yaml").write_text(
        "ckpt_name: flow.ckpt\nautoencoder_ckpt_path: ae.ckpt\n"
    )
    (root / "setup.sh").write_text("# Test source marker; not an installer.\n")
    return root


@pytest.fixture
def caller(tmp_path):
    root = tmp_path / "skill catalog"
    (root / ".git").mkdir(parents=True)
    (root / ".git/config").write_text("preserve Git metadata\n")
    (root / ".gitignore").write_text("preserve ignored files\n")
    (root / "design.cif").write_text("preserve existing design\n")
    return root


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def recording_python(path, exit_code=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "print(json.dumps({'cwd': os.getcwd(), 'args': sys.argv[1:], "
        "'root': os.environ.get('RFPROTEINA_ROOT')}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    path.chmod(0o755)


def wrapper(caller, *, root=None, python=None, args=()):
    env = dict(os.environ)
    env.pop("RFPROTEINA_ROOT", None)
    env.pop("RFPROTEINA_PYTHON", None)
    if root is not None:
        env["RFPROTEINA_ROOT"] = str(root)
    if python is not None:
        env["RFPROTEINA_PYTHON"] = str(python)
    return subprocess.run(
        ["bash", str(WRAPPER), *args], cwd=caller, env=env,
        text=True, capture_output=True,
    )


def test_native_runtime_without_dispatcher_preserves_separate_catalog(model, caller):
    recording_python(model / ".venv/bin/python")
    before = snapshot(caller), snapshot(model)
    result = wrapper(caller, root=model)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "cwd": str(model), "root": str(model),
        "args": [str(CHECKER), "--repo-root", str(model)],
    }
    assert (snapshot(caller), snapshot(model)) == before


@pytest.mark.parametrize("equals", [False, True])
def test_cli_root_overrides_environment_before_selecting_runtime(model, caller, equals):
    recording_python(model / ".venv/bin/python")
    args = [f"--repo-root={model}"] if equals else ["--repo-root", str(model)]
    result = wrapper(caller, root=caller / "missing", args=args)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["root"] == str(model)


def test_explicit_interpreter_resolves_before_chdir_and_propagates_failure(model, caller):
    recording_python(model / ".venv/bin/python", exit_code=90)
    recording_python(model / "scripts/rfproteina_exec.sh", exit_code=91)
    recording_python(caller / "chosen python", exit_code=73)
    before = snapshot(caller), snapshot(model)
    result = wrapper(caller, root=model, python="./chosen python")
    assert result.returncode == 73
    assert json.loads(result.stdout)["args"] == [str(CHECKER), "--repo-root", str(model)]
    assert (snapshot(caller), snapshot(model)) == before


def test_bad_explicit_interpreter_does_not_fall_back(model, caller):
    recording_python(model / ".venv/bin/python")
    result = wrapper(caller, root=model, python=caller / "missing python")
    assert result.returncode == 1
    assert "RFPROTEINA_PYTHON" in result.stderr
    assert result.stdout == ""


def test_missing_runtime_is_distinct_from_missing_model(model, caller):
    before = snapshot(caller), snapshot(model)
    result = wrapper(caller, root=model)
    assert result.returncode == 1
    assert "Model checkout found" in result.stderr
    assert "runtime is not installed" in result.stderr
    assert (snapshot(caller), snapshot(model)) == before


def test_catalog_is_not_accepted_as_model(caller):
    before = snapshot(caller)
    result = wrapper(caller, root=caller)
    assert result.returncode == 1
    assert "missing .project-root" in result.stderr
    assert snapshot(caller) == before


def test_wrapper_help_does_not_need_checkout(caller):
    assert wrapper(caller, args=["--help"]).returncode == 0


@pytest.mark.parametrize("args", [
    ["--repo-root"], ["--repo-root="], ["--data-path"], ["--data-path="], ["--unknown"],
])
def test_wrapper_invalid_arguments_are_usage_errors(caller, args):
    assert wrapper(caller, args=args).returncode == 2


@pytest.mark.parametrize("exported,explicit,expected", [
    ("exported data", None, "exported data"),
    ("exported data", "chosen data", "chosen data"),
    (None, "chosen data", "chosen data"),
])
def test_data_path_precedence(checker, model, monkeypatch, exported, explicit, expected):
    monkeypatch.delenv("DATA_PATH", raising=False)
    if exported is not None:
        monkeypatch.setenv("DATA_PATH", exported)
    assert checker.data_path(model, explicit) == model / expected


@pytest.mark.parametrize("equals", [False, True])
def test_wrapper_forwards_data_path_without_resolving_it_against_catalog(model, caller, equals):
    recording_python(model / ".venv/bin/python")
    args = ["--data-path=weights with spaces"] if equals else ["--data-path", "weights with spaces"]
    result = wrapper(caller, root=model, args=args)
    assert result.returncode == 0
    assert json.loads(result.stdout)["args"] == [
        str(CHECKER), "--repo-root", str(model), "--data-path", "weights with spaces",
    ]


@pytest.mark.parametrize("setting", [None, ""])
def test_missing_data_path_does_not_load_project_credential_files(checker, model, monkeypatch, setting):
    monkeypatch.delenv("DATA_PATH", raising=False)
    if setting is not None:
        monkeypatch.setenv("DATA_PATH", setting)
    (model / ".env").write_text("DATA_PATH=legacy\n")
    (model / ".env.local").write_text("DATA_PATH=local\n")
    before = snapshot(model)
    with pytest.raises(RuntimeError, match="Set DATA_PATH"):
        checker.data_path(model)
    assert snapshot(model) == before


def test_absolute_data_path_is_preserved(checker, model, tmp_path):
    absolute = tmp_path / "separate weights"
    assert checker.data_path(model, str(absolute)) == absolute


@pytest.mark.parametrize("failure", ["cuda", "empty", "missing"])
def test_failed_gpu_or_weights_never_reports_success(checker, model, monkeypatch, capsys, failure):
    from types import SimpleNamespace

    conditions = SimpleNamespace(__file__="test-double/conditions.py")
    monkeypatch.setitem(sys.modules, "rfproteina", SimpleNamespace(conditions=conditions))
    monkeypatch.setitem(sys.modules, "rfproteina.conditions", conditions)
    monkeypatch.setitem(sys.modules, "atomworks", SimpleNamespace(__file__="test-double/atomworks.py"))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: failure != "cuda", get_device_name=lambda index: "test double")))
    monkeypatch.setenv("DATA_PATH", "data")
    for directory, name in [("flow_checkpoints", "flow.ckpt"), ("ae_checkpoints", "ae.ckpt")]:
        file = model / "data" / directory / name
        file.parent.mkdir(parents=True)
        file.write_bytes(b"test checkpoint bytes")
    flow = model / "data/flow_checkpoints/flow.ckpt"
    if failure == "empty":
        flow.write_bytes(b"")
    elif failure == "missing":
        flow.unlink()
    before = snapshot(model)
    assert checker.main(["--repo-root", str(model)]) == 1
    assert os.environ["DATA_PATH"] == str(model / "data")
    output = capsys.readouterr().out
    assert "PREFLIGHT PASSED" not in output
    assert "FAIL:" in output
    assert snapshot(model) == before


@pytest.mark.parametrize("state", ["missing-source", "no-gpu-tool", "gpu-error", "no-devices", "ready"])
def test_live_eval_admission_checks_actual_prerequisites(model, tmp_path, state):
    config = yaml.safe_load((SKILL / "evals/config.yml").read_text())
    commands = config["harbor"]["pre_agent_setup"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if state != "no-gpu-tool":
        gpu_tool = bin_dir / "nvidia-smi"
        gpu_tool.write_text("#!/bin/sh\n" + {
            "gpu-error": "exit 1\n",
            "no-devices": "exit 0\n",
        }.get(state, "printf '%s\\n' 'unit-test device response'\n"))
        gpu_tool.chmod(0o755)
    root = tmp_path / "not-provisioned" if state == "missing-source" else model
    before = snapshot(model)
    result = subprocess.run(
        ["/bin/sh", "-c", "\n".join(commands)], text=True, capture_output=True,
        env={"RFPROTEINA_ROOT": str(root), "PATH": str(bin_dir)},
    )
    assert result.returncode == (0 if state == "ready" else 1), result.stderr
    if state != "ready":
        assert "EVAL ENVIRONMENT ERROR" in result.stderr
    assert snapshot(model) == before
    assert not (model / ".venv").exists()
    assert not (model / "runs").exists()
