"""Regression tests for catalog portability, ledger events, and analysis helpers.

Run with pytest, NumPy, pandas, SciPy, Matplotlib, Python Fire, and PyYAML.
GPU/model operations are not exercised by these tests.
"""

import ast
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


SKILLS = Path(__file__).resolve().parents[1] / "open-models-skills/rfd4-proteina"


def load_helper(skill, filename):
    path = SKILLS / f"rfd4-proteina-{skill}" / "scripts" / filename
    name = filename.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ledger(tmp_path):
    helper = load_helper("campaign", "campaign_ledger.py")
    database = helper.initialize(tmp_path / "campaign", "test")
    source = tmp_path / "input.cif"
    source.write_text("data_test\n")
    config = tmp_path / "config.yaml"
    config.write_text("num_replicates: 1\n")
    connection = helper.connect(database)
    with connection:
        input_id = helper.register_input(connection, database, "input", source)
        config_id = helper.register_config(connection, database, "config", config)
        run_id = helper.plan_run(
            connection, input_id=input_id, config_id=config_id, phase="pilot",
            command="rfd4-generate", out_dir="runs/pilot", partition="chosen",
        )
    yield helper, connection, database, run_id
    connection.close()


def ingest(ledger, path, **fields):
    helper, connection, database, run_id = ledger
    event = {"type": "run_status", "run_id": run_id, **fields}
    path.write_text(json.dumps(event) + "\n")
    return helper.ingest_events(connection, database, path)


def test_run_status_preserves_omitted_values_nulls_and_idempotency(ledger, tmp_path):
    _, connection, _, run_id = ledger
    events = tmp_path / "events.jsonl"
    assert ingest(ledger, events, event_id="start", status="running", started_at="start", gpu_hours=0) == {
        "imported": 1, "skipped": 0,
    }
    assert ingest(ledger, events, event_id="finish", status="completed", finished_at="end", gpu_hours=2.5)["imported"] == 1
    assert ingest(ledger, events, event_id="clear", finished_at=None)["imported"] == 1
    row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert (row["status"], row["started_at"], row["finished_at"], row["gpu_hours"], row["partition"]) == (
        "completed", "start", None, 2.5, "chosen",
    )
    assert ingest(ledger, events, event_id="clear", status="ignored") == {"imported": 0, "skipped": 1}


def test_run_status_binds_values_and_ignores_unknown_identifiers(ledger, tmp_path):
    _, connection, _, run_id = ledger
    value = "done'; DROP TABLE runs; --"
    ingest(ledger, tmp_path / "event.jsonl", event_id="literal", status=value,
           **{"partition = 'other' --": "ignored"})
    row = connection.execute("SELECT status, partition FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert tuple(row) == (value, "chosen")


def test_failed_event_rolls_back_all_updates(ledger, tmp_path):
    _, connection, _, run_id = ledger
    with pytest.raises(sqlite3.ProgrammingError):
        ingest(ledger, tmp_path / "bad.jsonl", event_id="bad", status="completed", gpu_hours=[])
    assert connection.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()[0] == "planned"
    assert connection.execute("SELECT COUNT(*) FROM imported_events").fetchone()[0] == 0
    with pytest.raises(ValueError, match="no status fields"):
        ingest(ledger, tmp_path / "empty.jsonl", event_id="empty", unexpected="value")


def test_package_connection_cannot_write_or_create_database(tmp_path):
    # Isolate the production SQLite helper from unavailable model/structure
    # dependencies. Execute its actual AST rather than a copy of the SQL logic.
    source = SKILLS / "rfd4-proteina-package/scripts/package_campaign.py"
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_connect")
    namespace = {"sqlite3": sqlite3, "Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    connect = namespace["_connect"]
    database = tmp_path / "campaign #1?.sqlite"
    with sqlite3.connect(database) as writer:
        writer.execute("CREATE TABLE evidence (value TEXT)")
        writer.execute("INSERT INTO evidence VALUES ('preserved')")
    before = database.read_bytes()
    reader = connect(database)
    try:
        assert reader.execute("SELECT value FROM evidence").fetchone()["value"] == "preserved"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.execute("DELETE FROM evidence")
    finally:
        reader.close()
    assert database.read_bytes() == before
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        connect(missing)
    assert not missing.exists()


@pytest.mark.parametrize("wrapper,args", [
    ("inspect_cif.sh", ["input with spaces.cif"]),
    ("check_annotated_cif.sh", ["input with spaces.cif", "--strict"]),
])
@pytest.mark.parametrize("explicit_python", [False, True])
def test_cif_wrappers_preserve_caller_paths(tmp_path, wrapper, args, explicit_python):
    model = tmp_path / "model checkout"
    interpreter = model / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "print(json.dumps({'cwd':os.getcwd(),'args':sys.argv[1:]}))\n"
    )
    interpreter.chmod(0o755)
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / args[0]).write_text("data_source\n")
    env = dict(os.environ, RFPROTEINA_ROOT=str(model))
    env.pop("RFPROTEINA_PYTHON", None)
    if explicit_python:
        env["RFPROTEINA_PYTHON"] = str(interpreter)
    script = SKILLS / "rfd4-proteina-annotated-cif/scripts" / wrapper
    result = subprocess.run(["bash", str(script), *args], cwd=caller, env=env,
                            text=True, capture_output=True, check=True)
    actual = json.loads(result.stdout)
    assert actual["cwd"] == str(caller)
    assert actual["args"] == [str(script.with_suffix(".py")), *args]
    assert (caller / args[0]).read_text() == "data_source\n"


def test_preflight_model_root_and_relative_data_path(tmp_path, monkeypatch):
    preflight = load_helper("setup", "preflight.py")
    model = tmp_path / "model"
    (model / "configs").mkdir(parents=True)
    (model / ".project-root").touch()
    (model / "pyproject.toml").write_text('[project]\nname = "rfproteina-test"\n')
    (model / "configs/inference.yaml").write_text("ckpt_name: flow.ckpt\nautoencoder_ckpt_path: ae.ckpt\n")
    for directory, filename in (("flow_checkpoints", "flow.ckpt"), ("ae_checkpoints", "ae.ckpt")):
        path = model / "data" / directory / filename
        path.parent.mkdir(parents=True)
        path.write_bytes(b"checkpoint test data")
    conditions = SimpleNamespace(__file__="model/conditions.py")
    monkeypatch.setitem(sys.modules, "rfproteina", SimpleNamespace(conditions=conditions))
    monkeypatch.setitem(sys.modules, "rfproteina.conditions", conditions)
    monkeypatch.setitem(sys.modules, "atomworks", SimpleNamespace(__file__="runtime/atomworks.py"))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: True, get_device_name=lambda index: "test GPU")))
    monkeypatch.setenv("DATA_PATH", "data")
    monkeypatch.setenv("RFPROTEINA_ROOT", str(model))
    monkeypatch.chdir(tmp_path)
    assert preflight.main([]) == 0
    (model / "data/flow_checkpoints/flow.ckpt").unlink()
    assert preflight.main([]) == 1
    assert preflight.main(["--repo-root", str(tmp_path / "missing")]) == 1


def test_preflight_wrapper_selects_the_model_runtime(tmp_path):
    model = tmp_path / "model checkout"
    dispatcher = model / "scripts/rfproteina_exec.sh"
    dispatcher.parent.mkdir(parents=True)
    (model / ".project-root").touch()
    (model / "pyproject.toml").write_text('[project]\nname = "rfproteina-test"\n')
    (model / "configs").mkdir()
    (model / "configs/inference.yaml").write_text("ckpt_name: flow.ckpt\n")
    dispatcher.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "print(json.dumps({'cwd':os.getcwd(),'args':sys.argv[1:]}))\n"
    )
    dispatcher.chmod(0o755)
    script = SKILLS / "rfd4-proteina-setup/scripts/preflight.sh"
    env = dict(os.environ, RFPROTEINA_ROOT=str(model))
    result = subprocess.run(["bash", str(script)], cwd=tmp_path, env=env,
                            text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == {
        "cwd": str(model),
        "args": ["training", str(script.with_suffix(".py")), "--repo-root", str(model)],
    }
    dispatcher.unlink()
    missing = subprocess.run(["bash", str(script)], cwd=tmp_path, env=env,
                             text=True, capture_output=True)
    assert missing.returncode == 1
    assert "Model checkout found" in missing.stderr
    assert "runtime is not installed" in missing.stderr


def test_preflight_help_needs_no_model_installation(tmp_path):
    script = SKILLS / "rfd4-proteina-setup/scripts/preflight.py"
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
                            text=True, capture_output=True, check=True)
    assert "--repo-root" in result.stdout


@pytest.mark.parametrize("name,expected", [
    ("min", [1.0, 2.0, 4.0]), ("max", [3.0, 2.0, 4.0]), ("mean", [2.0, 2.0, 4.0]),
])
def test_metric_reducers_preserve_missing_value_semantics(name, expected):
    curve = load_helper("commitment-curves", "commitment_curve.py")
    frame = pd.DataFrame({"a": [1.0, 2.0, np.nan], "b": [3.0, np.nan, 4.0]})
    assert curve.resolve_column(frame, f"{name}(a|b)").tolist() == expected
    with pytest.raises(KeyError):
        curve.resolve_column(frame, "min(a|missing)")
    with pytest.raises(KeyError):
        curve.resolve_column(frame, "eval(a)")


def test_distribution_fit_uses_supported_families():
    curve_dir = str(SKILLS / "rfd4-proteina-commitment-curves/scripts")
    sys.path.insert(0, curve_dir)
    try:
        distributions = load_helper("commitment-curves", "metric_distributions.py")
        values = np.random.default_rng(7).normal(size=100)
        assert distributions.fit_density(values) is not None
        assert distributions.fit_density(values[:2]) is None
    finally:
        sys.path.remove(curve_dir)
