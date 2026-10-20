"""Regression cases for campaign evidence, study configuration, and delivery.

Uses the helper-test dependencies plus Biotite 1.x, matching the package helper's
superimpose API. Model CIF parsing and GPU inference are outside this suite;
alignment uses real Biotite arrays and superposition.
"""

import ast
import csv
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tarfile
from types import ModuleType

import biotite.structure as struc
import numpy as np
import pandas as pd
import pytest
import yaml

from test_rosetta_helpers import SKILLS, ledger, load_helper  # noqa: F401 (pytest fixture)


@pytest.fixture
def campaign(ledger, tmp_path):
    helper, connection, database, run_id = ledger
    with connection:
        helper.register_design(connection, database, design_id="d1", run_id=run_id,
                               cif_path=tmp_path / "input.cif", chain_of_interest="A,B")
    helper.register_criteria(connection, {
        "id": "selection-v1", "criteria": [
            {"id": "quality", "metric": "quality", "operator": ">=", "threshold": 0.8},
        ],
    })
    return helper, connection, database


def record(campaign, value, **fields):
    helper, connection, _ = campaign
    with connection:
        return helper.record_metrics(connection, {
            "design_id": "d1", "values": {"quality": value},
            "observed_at": "2026-10-18T00:00:00+00:00", **fields,
        })[0]


@pytest.fixture
def package():
    # Load the production module except the unavailable model-specific imports.
    # Tests replace only CIF I/O when needed; SQL, correspondence, transforms,
    # waterfall calculations, and archive construction remain production code.
    path = SKILLS / "rfd4-proteina-package/scripts/package_campaign.py"
    tree = ast.parse(path.read_text())
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module.startswith(("atomworks", "rfproteina"))
        or isinstance(node, ast.Import) and any(alias.name.startswith("rfproteina") for alias in node.names)
        or isinstance(node, ast.If)
    )]
    module = ModuleType("package_campaign_test")
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def test_retry_revises_decision_without_losing_missing_evidence(campaign):
    helper, connection, _ = campaign
    assert helper.evaluate_passers(connection, "selection-v1") == {"evaluated": 1, "passed": 0, "failed": 1}
    original = dict(connection.execute("SELECT * FROM passer_evaluations").fetchone())
    observation_id = record(campaign, 0.9)
    assert helper.evaluate_passers(connection, "selection-v1") == {"evaluated": 1, "passed": 1, "failed": 0}
    assert dict(connection.execute("SELECT * FROM passer_evaluations WHERE id = ?", (original["id"],)).fetchone()) == original
    evidence = connection.execute("SELECT * FROM criterion_results ORDER BY rowid").fetchall()
    assert [(row["metric_observation_id"], row["status"], row["passed"]) for row in evidence] == [
        (None, "missing", 0), (observation_id, "computed", 1),
    ]
    assert helper.evaluate_passers(connection, "selection-v1")["evaluated"] == 0
    # An unrelated metric cannot change this criteria set's evidence.
    record(campaign, 10, values={"unrelated": 10})
    assert helper.evaluate_passers(connection, "selection-v1")["evaluated"] == 0


def test_delivery_uses_latest_decision_and_exact_evidence(campaign, package):
    helper, connection, _ = campaign
    record(campaign, 0.95)
    helper.evaluate_passers(connection, "selection-v1")
    first = package._selected_designs(connection, "selection-v1")[0]["passer_evaluation_id"]
    record(campaign, {"status": "failed", "value": None})
    helper.evaluate_passers(connection, "selection-v1")
    with pytest.raises(ValueError, match="no passers"):
        package._selected_designs(connection, "selection-v1")
    record(campaign, 0.85)
    helper.evaluate_passers(connection, "selection-v1")
    selected = package._selected_designs(connection, "selection-v1")
    assert len(selected) == 1
    assert selected[0]["passer_evaluation_id"] != first
    results, owners = package._criterion_results(connection, "selection-v1")
    assert owners["d1"] == selected[0]["passer_evaluation_id"]
    assert results["d1", "quality"]["actual_value"] == 0.85
    assert connection.execute("SELECT COUNT(*) FROM passer_evaluations").fetchone()[0] == 3
    assert helper.reconcile(connection, campaign[2]) == []


def test_export_matches_evaluation_for_timestamp_ties(campaign, tmp_path, monkeypatch):
    helper, connection, _ = campaign
    ids = iter(["metric_z_old", "metric_a_correction", "metric_z_backfill"])
    monkeypatch.setattr(helper, "_new_id", lambda prefix: next(ids))
    record(campaign, 0.1)
    correction = record(campaign, 0.9)
    record(campaign, 0.2, observed_at="2026-10-17T00:00:00+00:00")
    criterion = connection.execute("SELECT * FROM criteria").fetchone()
    assert helper._metric_for_criterion(connection, "d1", criterion)["id"] == correction
    output = helper.export_metrics(connection, tmp_path / "metrics.csv")
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert float(rows[0]["quality"]) == 0.9


@pytest.mark.parametrize("change_before_copy", [True, False])
def test_archive_metadata_describes_copied_bytes(ledger, tmp_path, monkeypatch, change_before_copy):
    helper, connection, database, _ = ledger
    source = tmp_path / "worker.cif"
    source.write_bytes(b"initial worker output")
    original_copy = helper.shutil.copy2

    def changing_copy(src, dst):
        if change_before_copy:
            Path(src).write_bytes(b"replacement worker output with a different length")
        result = original_copy(src, dst)
        if not change_before_copy:
            Path(src).write_bytes(b"changed after snapshot")
        return result

    monkeypatch.setattr(helper.shutil, "copy2", changing_copy)
    with connection:
        artifact_id = helper.archive_artifact(connection, database, source, "worker_output")
    row = connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    archived = (database.parent / row["relative_path"]).read_bytes()
    digest = hashlib.sha256(archived).hexdigest()
    assert row["sha256"] == digest
    assert row["size_bytes"] == len(archived)
    assert Path(row["relative_path"]).name == f"{digest}.cif"
    assert helper.reconcile(connection, database) == []


def test_config_hash_comes_from_archived_snapshot(ledger, tmp_path, monkeypatch):
    helper, connection, database, _ = ledger
    source = tmp_path / "live-config.yaml"
    source.write_text("seed: 1\n")
    original_copy = helper.shutil.copy2

    def changing_copy(src, dst):
        result = original_copy(src, dst)
        Path(src).write_text("seed: 200\n")
        return result

    monkeypatch.setattr(helper.shutil, "copy2", changing_copy)
    with connection:
        config_id = helper.register_config(connection, database, "snapshot", source)
    row = connection.execute(
        "SELECT c.config_hash, a.sha256 FROM config_snapshots c "
        "JOIN artifacts a ON a.id = c.resolved_config_artifact_id WHERE c.id = ?", (config_id,),
    ).fetchone()
    assert row["config_hash"] == row["sha256"]


def test_archive_deduplicates_snapshot_and_cleans_staging(ledger, tmp_path, monkeypatch):
    helper, connection, database, _ = ledger
    source = tmp_path / "snapshot.cif"
    source.write_bytes(b"immutable snapshot")
    with connection:
        first = helper.archive_artifact(connection, database, source, "snapshot")
        second = helper.archive_artifact(connection, database, source, "snapshot")
    assert first == second
    assert not list((database.parent / "artifacts/sha256").glob(".archive-*"))

    def failed_copy(src, dst):
        Path(dst).write_bytes(b"incomplete")
        raise OSError("interrupted copy")

    count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    monkeypatch.setattr(helper.shutil, "copy2", failed_copy)
    with pytest.raises(OSError, match="interrupted copy"), connection:
        helper.archive_artifact(connection, database, source, "another")
    assert connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == count
    assert not list((database.parent / "artifacts/sha256").glob(".archive-*"))


def legacy_database(path, broken_evidence=False):
    # Original v1 table constraints and a minimal referenced evidence graph.
    # This fixture is independent of the new schema and its migration code.
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            PRAGMA user_version = 1;
            CREATE TABLE designs (id TEXT PRIMARY KEY);
            CREATE TABLE criteria_sets (id TEXT PRIMARY KEY);
            CREATE TABLE criteria (id TEXT PRIMARY KEY);
            CREATE TABLE metric_observations (id TEXT PRIMARY KEY);
            CREATE TABLE passer_evaluations (
                id TEXT PRIMARY KEY,
                design_id TEXT NOT NULL REFERENCES designs(id),
                criteria_set_id TEXT NOT NULL REFERENCES criteria_sets(id),
                passed INTEGER NOT NULL,
                status TEXT NOT NULL,
                evaluated_at TEXT NOT NULL,
                UNIQUE(design_id, criteria_set_id)
            );
            CREATE TABLE criterion_results (
                passer_evaluation_id TEXT NOT NULL REFERENCES passer_evaluations(id),
                criterion_id TEXT NOT NULL REFERENCES criteria(id),
                metric_observation_id TEXT REFERENCES metric_observations(id),
                actual_value REAL,
                status TEXT NOT NULL,
                passed INTEGER NOT NULL,
                PRIMARY KEY(passer_evaluation_id, criterion_id)
            );
            INSERT INTO designs VALUES ('d1');
            INSERT INTO criteria_sets VALUES ('v1');
            INSERT INTO criteria VALUES ('quality');
            INSERT INTO metric_observations VALUES ('observation');
            INSERT INTO passer_evaluations VALUES ('original', 'd1', 'v1', 1, 'complete', 'later');
        """)
        connection.execute("INSERT INTO criterion_results VALUES (?, 'quality', 'observation', 0.9, 'computed', 1)",
                           ("missing" if broken_evidence else "original",))


def test_v1_upgrade_preserves_ids_evidence_and_foreign_keys(tmp_path):
    helper = load_helper("campaign", "campaign_ledger.py")
    path = tmp_path / "v1.sqlite"
    legacy_database(path)
    connection = helper.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert tuple(connection.execute("SELECT * FROM criterion_results").fetchone()) == (
            "original", "quality", "observation", 0.9, "computed", 1,
        )
        assert connection.execute("SELECT id, revision FROM latest_passer_evaluations").fetchone()["id"] == "original"
        with connection:
            connection.execute("INSERT INTO passer_evaluations VALUES ('retry', 'd1', 'v1', 0, 'complete', 'earlier', 2)")
        assert connection.execute("SELECT id FROM latest_passer_evaluations").fetchone()[0] == "retry"
        assert connection.execute("SELECT COUNT(*) FROM passer_evaluations").fetchone()[0] == 2
    finally:
        connection.close()
    # Opening an already upgraded database is idempotent.
    connection = helper.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM passer_evaluations").fetchone()[0] == 2
    finally:
        connection.close()


def test_v1_upgrade_rolls_back_if_evidence_is_corrupt(tmp_path):
    helper = load_helper("campaign", "campaign_ledger.py")
    path = tmp_path / "broken.sqlite"
    legacy_database(path, broken_evidence=True)
    with pytest.raises(RuntimeError, match="foreign-key"):
        helper.connect(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT id FROM passer_evaluations").fetchone()[0] == "original"
        assert connection.execute("SELECT passer_evaluation_id FROM criterion_results").fetchone()[0] == "missing"
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'passer_evaluations_v2'").fetchone() is None
        assert "revision" not in [row[1] for row in connection.execute("PRAGMA table_info(passer_evaluations)")]


def test_delivery_tar_uses_current_values_and_counts_designs_once(campaign, package, tmp_path, monkeypatch):
    helper, connection, database = campaign
    for value in (0.9, 0.1, 0.85):
        record(campaign, value)
        helper.evaluate_passers(connection, "selection-v1")
    # No oracle predictions in this fixture; plain CIF copies need no model I/O.
    monkeypatch.setattr(package, "transfer_with_compression", shutil.copyfile, raising=False)
    before = database.read_bytes()
    output = package.build_package(database, "selection-v1", tmp_path / "delivery.tar")
    with tarfile.open(output) as archive:
        metrics = archive.extractfile("delivery/metrics.csv").read().decode()
        rows = list(csv.DictReader(metrics.splitlines()))
        assert len(rows) == 1
        assert float(rows[0]["quality"]) == 0.85
        waterfall = archive.extractfile("delivery/WATERFALL.md").read().decode()
        assert "| 1 | 1 | 0 | 1 |" in waterfall
        assert sum(name.endswith("__design.cif") for name in archive.getnames()) == 1
    assert database.read_bytes() == before


@pytest.mark.parametrize("nsteps", [None, 60, 80])
def test_study_config_grid_and_analysis_use_same_step_count(tmp_path, capsys, nsteps):
    configs = load_helper("commitment-curves", "make_configs.py")
    curve = load_helper("commitment-curves", "commitment_curve.py")
    spec = {
        "name": "study", "inputs": "inputs", "parents_dir": "parents", "out_root": "runs",
        "phase2": {"step": 5},
    }
    if nsteps is not None:
        spec["phase2"]["nsteps"] = nsteps
    nsteps = nsteps or 60
    source = tmp_path / "study.yaml"
    source.write_text(yaml.safe_dump(spec))
    configs.main(str(source), repo_root=str(tmp_path))
    experiment = yaml.safe_load((tmp_path / "configs/inference_experiment/study_sweep.yaml").read_text())
    assert experiment["generation"]["args"]["nsteps"] == nsteps
    sweep = yaml.safe_load((tmp_path / "configs/sweeps/study.yaml").read_text())
    frame = pd.DataFrame(sweep["sweep"])
    steps = curve.with_restart_step(frame, nsteps)["restart_step"].tolist()
    assert steps == list(range(nsteps - 5, -1, -5))
    assert f"--nsteps {nsteps}" in capsys.readouterr().out


def atoms(chain_ids, atom_names):
    array = struc.AtomArray(len(chain_ids))
    array.chain_id = np.asarray(chain_ids)
    array.atom_name = np.asarray(atom_names)
    array.res_id = np.arange(len(chain_ids)) + 1
    array.coord = np.asarray([[i % 3, i // 3, i % 2] for i in range(len(chain_ids))], dtype=float)
    return array


@pytest.mark.parametrize("missing_from_reference", [False, True])
def test_alignment_rejects_missing_requested_chain(package, missing_from_reference):
    complete = atoms(["A"] * 3 + ["B"] * 3, ["CA"] * 6)
    incomplete = complete[:3]
    reference, mobile = (incomplete, complete) if missing_from_reference else (complete, incomplete)
    with pytest.raises(ValueError, match="B"):
        package._matching_anchor_indices(reference, mobile, ["A", "B"])


def test_alignment_combines_protein_and_nucleic_acid_anchors(package, tmp_path, monkeypatch):
    reference = atoms(["A"] * 3 + ["B"] * 3, ["CA"] * 3 + ["C4'"] * 3)
    mobile = reference[::-1].copy()
    mobile.coord = mobile.coord @ np.asarray([[0, -1, 0], [1, 0, 0], [0, 0, 1]]) + [10, 20, 30]
    ref_idx, mobile_idx = package._matching_anchor_indices(reference, mobile, ["A", "B"])
    assert set(reference.chain_id[ref_idx]) == {"A", "B"}
    assert len(ref_idx) == len(mobile_idx) == 6
    monkeypatch.setattr(package, "_load_cif", lambda path: reference if path.name == "design.cif" else mobile)
    written = []
    monkeypatch.setattr(package, "to_cif_file", lambda array, *args, **kwargs: written.append(array), raising=False)
    package.align_refold("design.cif", "refold.cif", tmp_path / "aligned.cif", "A,B")
    np.testing.assert_allclose(written[0].coord[mobile_idx], reference.coord[ref_idx], atol=1e-5)
    # The archived input remains in the predictor's original frame.
    assert not np.allclose(mobile.coord[mobile_idx], reference.coord[ref_idx])


def test_alignment_rejects_nonmatching_chain_correspondence(package):
    reference = atoms(["A"] * 3 + ["B"] * 3, ["CA"] * 6)
    mobile = reference.copy()
    mobile.res_id[3:] += 100
    with pytest.raises(ValueError, match="every requested chain"):
        package._matching_anchor_indices(reference, mobile, ["A", "B"])


def test_alignment_fallback_and_duplicate_atom_detection(package):
    reference = atoms(["A", "A", "B"], ["N", "C", "P"])
    mobile = reference[::-1].copy()
    ref_idx, mobile_idx = package._matching_anchor_indices(reference, mobile, ["A", "B"])
    assert len(ref_idx) == 3
    assert set(reference.chain_id[ref_idx]) == {"A", "B"}
    np.testing.assert_array_equal(reference.coord[ref_idx], mobile.coord[mobile_idx])
    duplicate = reference[[0, 0, 1, 2]]
    with pytest.raises(ValueError, match="ambiguous"):
        package._matching_anchor_indices(duplicate, mobile, ["A", "B"])


def test_alignment_rejects_collinear_anchors(package, tmp_path, monkeypatch):
    array = atoms(["A"] * 3, ["CA"] * 3)
    array.coord = np.asarray([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
    monkeypatch.setattr(package, "_load_cif", lambda path: array)
    with pytest.raises(ValueError, match="non-collinear"):
        package.align_refold("design.cif", "refold.cif", tmp_path / "output.cif", "A")
