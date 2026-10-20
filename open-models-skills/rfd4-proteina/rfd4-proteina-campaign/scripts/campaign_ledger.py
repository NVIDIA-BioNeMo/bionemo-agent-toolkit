#!/usr/bin/env python
"""Create and maintain a portable RFProteína campaign ledger.

The ledger stores immutable identities and relationships in SQLite while archiving
critical files in a content-addressed directory beside the database. Cluster jobs
emit JSONL events; one coordinator imports them transactionally and idempotently.

Usage: python campaign_ledger.py --help
Arguments: A subcommand and its required paths/IDs; use subcommand --help for options.
Output: SQLite records, archived artifacts, and JSON command results; export writes CSV.
Exit codes: 0 for success, 1 for failed reconciliation or runtime failure, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import operator
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
COMPARISONS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

SCHEMA = """
CREATE TABLE campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    rfproteina_revision TEXT,
    atomworks_revision TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    original_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(kind, sha256)
);

CREATE TABLE inputs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    name TEXT NOT NULL,
    annotated_cif_artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    parent_input_id TEXT REFERENCES inputs(id),
    intent TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(campaign_id, name)
);

CREATE TABLE config_snapshots (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    name TEXT NOT NULL,
    resolved_config_artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    source_config_artifact_id TEXT REFERENCES artifacts(id),
    overrides_json TEXT NOT NULL DEFAULT '[]',
    config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(campaign_id, name, config_hash)
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    input_id TEXT NOT NULL REFERENCES inputs(id),
    config_id TEXT NOT NULL REFERENCES config_snapshots(id),
    parent_run_id TEXT REFERENCES runs(id),
    phase TEXT NOT NULL,
    command TEXT NOT NULL,
    out_dir TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    cluster TEXT,
    partition TEXT,
    account TEXT,
    qos TEXT,
    priority TEXT,
    reservation TEXT,
    scheduler_constraint TEXT,
    gres TEXT,
    runtime TEXT,
    mem TEXT,
    cpus_per_task TEXT,
    slurm_extra_options TEXT,
    slurm_job_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    gpu_hours REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE designs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    structure_artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    parent_design_id TEXT REFERENCES designs(id),
    example_id TEXT,
    seed INTEGER,
    sample_index INTEGER,
    search_branch TEXT,
    search_checkpoint INTEGER,
    chain_of_interest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE TABLE oracle_evaluations (
    id TEXT PRIMARY KEY,
    design_id TEXT NOT NULL REFERENCES designs(id),
    backend TEXT NOT NULL,
    role TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE oracle_predictions (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES oracle_evaluations(id),
    structure_artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    confidence_artifact_id TEXT REFERENCES artifacts(id),
    seed INTEGER,
    sample_index INTEGER,
    rank INTEGER,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE TABLE metric_observations (
    id TEXT PRIMARY KEY,
    design_id TEXT NOT NULL REFERENCES designs(id),
    prediction_id TEXT REFERENCES oracle_predictions(id),
    name TEXT NOT NULL,
    value_real REAL,
    value_text TEXT,
    status TEXT NOT NULL,
    evaluator TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE INDEX metric_observations_design_name
ON metric_observations(design_id, name, observed_at);

CREATE TABLE criteria_sets (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE criteria (
    id TEXT PRIMARY KEY,
    criteria_set_id TEXT NOT NULL REFERENCES criteria_sets(id),
    position INTEGER NOT NULL,
    label TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    oracle_role TEXT,
    comparison TEXT NOT NULL,
    threshold REAL NOT NULL,
    missing_policy TEXT NOT NULL,
    UNIQUE(criteria_set_id, position)
);

CREATE TABLE passer_evaluations (
    id TEXT PRIMARY KEY,
    design_id TEXT NOT NULL REFERENCES designs(id),
    criteria_set_id TEXT NOT NULL REFERENCES criteria_sets(id),
    passed INTEGER NOT NULL,
    status TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    UNIQUE(design_id, criteria_set_id, revision)
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

CREATE TABLE imported_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE VIEW design_catalog AS
SELECT
    d.id AS design_id,
    d.example_id,
    d.chain_of_interest,
    d.parent_design_id,
    d.search_branch,
    d.search_checkpoint,
    r.id AS run_id,
    r.phase,
    r.status AS run_status,
    i.id AS input_id,
    i.name AS input_name,
    ia.relative_path AS input_cif_path,
    c.id AS config_id,
    c.name AS config_name,
    ca.relative_path AS resolved_config_path,
    da.relative_path AS design_cif_path
FROM designs d
JOIN runs r ON r.id = d.run_id
JOIN inputs i ON i.id = r.input_id
JOIN artifacts ia ON ia.id = i.annotated_cif_artifact_id
JOIN config_snapshots c ON c.id = r.config_id
JOIN artifacts ca ON ca.id = c.resolved_config_artifact_id
JOIN artifacts da ON da.id = d.structure_artifact_id;
"""

LATEST_PASSERS_VIEW = """
CREATE VIEW latest_passer_evaluations AS
SELECT p.* FROM passer_evaluations p
WHERE p.revision = (
    SELECT MAX(newer.revision) FROM passer_evaluations newer
    WHERE newer.design_id = p.design_id AND newer.criteria_set_id = p.criteria_set_id
);
"""


def _upgrade_v1(connection: sqlite3.Connection) -> None:
    """Retain v1 decisions and evidence while allowing new decision revisions."""
    # Rebuild with foreign keys temporarily disabled, following SQLite's
    # documented table-rebuild order; renaming the old table would retarget FKs.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE passer_evaluations_v2 (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL REFERENCES designs(id),
                    criteria_set_id TEXT NOT NULL REFERENCES criteria_sets(id),
                    passed INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision > 0),
                    UNIQUE(design_id, criteria_set_id, revision)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO passer_evaluations_v2
                SELECT id, design_id, criteria_set_id, passed, status, evaluated_at, 1
                FROM passer_evaluations
                """
            )
            connection.execute("DROP TABLE passer_evaluations")
            connection.execute("ALTER TABLE passer_evaluations_v2 RENAME TO passer_evaluations")
            connection.execute(LATEST_PASSERS_VIEW)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Campaign upgrade failed foreign-key checks; no changes were committed")
            connection.execute("PRAGMA user_version = 2")
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _now() -> str:
    """Return a stable UTC timestamp for ledger records."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    """Return a compact globally unique identifier with a readable prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sha256(path: Path) -> str:
    """Hash one file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def connect(database: str | Path) -> sqlite3.Connection:
    """Open a ledger, upgrading v1 decision history transactionally when needed."""
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Campaign database does not exist: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            _upgrade_v1(connection)
        elif version != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported campaign schema {version}; expected {SCHEMA_VERSION}")
    except Exception:
        connection.close()
        raise
    return connection


def initialize(
    root: str | Path,
    name: str,
    objective: str = "",
    campaign_id: str | None = None,
    rfproteina_revision: str | None = None,
    atomworks_revision: str | None = None,
) -> Path:
    """Create a new campaign root and return its SQLite path."""
    campaign_root = Path(root).resolve()
    database = campaign_root / "campaign.sqlite"
    if database.exists():
        raise FileExistsError(f"Campaign database already exists: {database}")
    for directory in ("artifacts/sha256", "runs", "exports", "reports"):
        (campaign_root / directory).mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA + LATEST_PASSERS_VIEW)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute(
            "INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?)",
            (
                campaign_id or _new_id("campaign"),
                name,
                objective,
                rfproteina_revision,
                atomworks_revision,
                _now(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return database


def _campaign_id(connection: sqlite3.Connection) -> str:
    """Return the only campaign ID in a per-campaign database."""
    rows = connection.execute("SELECT id FROM campaigns").fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"Expected one campaign row, found {len(rows)}")
    return str(rows[0]["id"])


def archive_artifact(
    connection: sqlite3.Connection,
    database: str | Path,
    source: str | Path,
    kind: str,
) -> str:
    """Archive a file by digest and return its artifact ID."""
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Artifact does not exist: {source_path}")
    root = Path(database).resolve().parent
    staging = root / "artifacts" / "sha256"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=staging, prefix=".archive-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        # A worker can replace its output during ingestion. Name and describe the
        # captured bytes, never an earlier or later version of the source path.
        shutil.copy2(source_path, temporary)
        digest = _sha256(temporary)
        size_bytes = temporary.stat().st_size
        existing = connection.execute("SELECT id FROM artifacts WHERE kind = ? AND sha256 = ?", (kind, digest)).fetchone()
        if existing:
            return str(existing["id"])
        suffix = "".join(source_path.suffixes)
        relative = Path("artifacts") / "sha256" / digest[:2] / f"{digest}{suffix}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    artifact_id = _new_id("artifact")
    connection.execute(
        "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            artifact_id,
            kind,
            relative.as_posix(),
            str(source_path),
            digest,
            size_bytes,
            _now(),
        ),
    )
    return artifact_id


def register_input(
    connection: sqlite3.Connection,
    database: str | Path,
    name: str,
    cif: str | Path,
    input_id: str | None = None,
    parent_input_id: str | None = None,
    intent: str = "",
) -> str:
    """Register one exact annotated-CIF input."""
    artifact_id = archive_artifact(connection, database, cif, "annotated_cif")
    registered_id = input_id or _new_id("input")
    connection.execute(
        "INSERT INTO inputs VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            registered_id,
            _campaign_id(connection),
            name,
            artifact_id,
            parent_input_id,
            intent,
            _now(),
        ),
    )
    return registered_id


def register_config(
    connection: sqlite3.Connection,
    database: str | Path,
    name: str,
    resolved_config: str | Path,
    config_id: str | None = None,
    source_config: str | Path | None = None,
    overrides: Sequence[str] = (),
) -> str:
    """Register an exact resolved config and optional source config."""
    resolved_artifact = archive_artifact(connection, database, resolved_config, "resolved_config")
    source_artifact = archive_artifact(connection, database, source_config, "source_config") if source_config else None
    config_hash = connection.execute("SELECT sha256 FROM artifacts WHERE id = ?", (resolved_artifact,)).fetchone()[0]
    registered_id = config_id or _new_id("config")
    connection.execute(
        "INSERT INTO config_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            registered_id,
            _campaign_id(connection),
            name,
            resolved_artifact,
            source_artifact,
            json.dumps(list(overrides), separators=(",", ":")),
            config_hash,
            _now(),
        ),
    )
    return registered_id


RUN_SCHEDULER_FIELDS = (
    "cluster",
    "partition",
    "account",
    "qos",
    "priority",
    "reservation",
    "scheduler_constraint",
    "gres",
    "runtime",
    "mem",
    "cpus_per_task",
    "slurm_extra_options",
    "slurm_job_id",
)


def plan_run(
    connection: sqlite3.Connection,
    *,
    input_id: str,
    config_id: str,
    phase: str,
    command: str,
    out_dir: str,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    **scheduler: str | None,
) -> str:
    """Register a run and the user's exact scheduler resolution before launch."""
    unknown = set(scheduler) - set(RUN_SCHEDULER_FIELDS)
    if unknown:
        raise ValueError(f"Unknown scheduler fields: {sorted(unknown)}")
    registered_id = run_id or _new_id("run")
    fields = {name: scheduler.get(name) for name in RUN_SCHEDULER_FIELDS}
    connection.execute(
        """
        INSERT INTO runs (
            id, campaign_id, input_id, config_id, parent_run_id, phase, command,
            out_dir, status, cluster, partition, account, qos, priority,
            reservation, scheduler_constraint, gres, runtime, mem, cpus_per_task,
            slurm_extra_options, slurm_job_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            registered_id,
            _campaign_id(connection),
            input_id,
            config_id,
            parent_run_id,
            phase,
            command,
            out_dir,
            *(fields[name] for name in RUN_SCHEDULER_FIELDS),
            _now(),
        ),
    )
    return registered_id


def register_design(
    connection: sqlite3.Connection,
    database: str | Path,
    *,
    design_id: str,
    run_id: str,
    cif_path: str | Path,
    chain_of_interest: str,
    parent_design_id: str | None = None,
    example_id: str | None = None,
    seed: int | None = None,
    sample_index: int | None = None,
    search_branch: str | None = None,
    search_checkpoint: int | None = None,
    status: str = "completed",
) -> str:
    """Register a materialized design or search checkpoint structure."""
    artifact_id = archive_artifact(connection, database, cif_path, "design_cif")
    connection.execute(
        "INSERT INTO designs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            design_id,
            run_id,
            artifact_id,
            parent_design_id,
            example_id,
            seed,
            sample_index,
            search_branch,
            search_checkpoint,
            chain_of_interest,
            status,
            _now(),
        ),
    )
    return design_id


def register_oracle_evaluation(connection: sqlite3.Connection, payload: Mapping[str, Any]) -> str:
    """Register one oracle invocation, including failures with no prediction."""
    evaluation_id = str(payload.get("evaluation_id") or _new_id("oracle_eval"))
    connection.execute(
        "INSERT INTO oracle_evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evaluation_id,
            payload["design_id"],
            payload["backend"],
            payload["role"],
            payload.get("model"),
            payload.get("status", "completed"),
            payload.get("error"),
            payload.get("started_at"),
            payload.get("finished_at"),
            _now(),
        ),
    )
    return evaluation_id


def register_oracle_prediction(
    connection: sqlite3.Connection,
    database: str | Path,
    payload: Mapping[str, Any],
    base_dir: Path,
) -> str:
    """Archive and register one prediction and its available confidence JSON."""
    prediction_id = str(payload.get("prediction_id") or _new_id("oracle_pred"))
    structure = _event_path(base_dir, payload["cif_path"])
    structure_artifact = archive_artifact(connection, database, structure, "oracle_prediction_cif")
    confidence_artifact = None
    if confidence := payload.get("confidence_path"):
        confidence_artifact = archive_artifact(
            connection, database, _event_path(base_dir, confidence), "oracle_confidence_json"
        )
    connection.execute(
        "INSERT INTO oracle_predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            prediction_id,
            payload["evaluation_id"],
            structure_artifact,
            confidence_artifact,
            payload.get("seed"),
            payload.get("sample_index"),
            payload.get("rank"),
            payload.get("status", "completed"),
            _now(),
        ),
    )
    return prediction_id


def record_metrics(connection: sqlite3.Connection, payload: Mapping[str, Any]) -> list[str]:
    """Record actual metric values with explicit missing or failure states."""
    observed_at = str(payload.get("observed_at") or _now())
    evaluator = str(payload.get("evaluator") or "unspecified")
    metric_ids = []
    for name, raw in payload["values"].items():
        status = "computed"
        value = raw
        if isinstance(raw, Mapping):
            status = str(raw.get("status", "computed"))
            value = raw.get("value")
        value_real = float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
        value_text = None if value is None or value_real is not None else str(value)
        if value is None and status == "computed":
            status = "missing"
        metric_id = _new_id("metric")
        connection.execute(
            "INSERT INTO metric_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric_id,
                payload["design_id"],
                payload.get("prediction_id"),
                name,
                value_real,
                value_text,
                status,
                evaluator,
                observed_at,
            ),
        )
        metric_ids.append(metric_id)
    return metric_ids


def _event_path(base_dir: Path, value: str | Path) -> Path:
    """Resolve an event path relative to the immutable event file."""
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def ingest_events(connection: sqlite3.Connection, database: str | Path, events_file: str | Path) -> dict[str, int]:
    """Import one JSONL worker event stream transactionally and idempotently."""
    event_path = Path(events_file).resolve()
    counts = {"imported": 0, "skipped": 0}
    with event_path.open() as handle, connection:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            event_id = str(payload.get("event_id") or "")
            event_type = str(payload.get("type") or "")
            if not event_id or not event_type:
                raise ValueError(f"{event_path}:{line_number}: event_id and type are required")
            if connection.execute("SELECT 1 FROM imported_events WHERE event_id = ?", (event_id,)).fetchone():
                counts["skipped"] += 1
                continue
            _apply_event(connection, database, payload, event_path.parent)
            connection.execute(
                "INSERT INTO imported_events VALUES (?, ?, ?, ?)",
                (event_id, event_type, json.dumps(payload, sort_keys=True), _now()),
            )
            counts["imported"] += 1
    return counts


def _apply_event(
    connection: sqlite3.Connection,
    database: str | Path,
    payload: Mapping[str, Any],
    base_dir: Path,
) -> None:
    """Apply one validated worker event to the ledger."""
    event_type = payload["type"]
    if event_type == "design":
        register_design(
            connection,
            database,
            design_id=payload["design_id"],
            run_id=payload["run_id"],
            cif_path=_event_path(base_dir, payload["cif_path"]),
            chain_of_interest=payload["chain_of_interest"],
            parent_design_id=payload.get("parent_design_id"),
            example_id=payload.get("example_id"),
            seed=payload.get("seed"),
            sample_index=payload.get("sample_index"),
            search_branch=payload.get("search_branch"),
            search_checkpoint=payload.get("search_checkpoint"),
            status=payload.get("status", "completed"),
        )
    elif event_type == "oracle_evaluation":
        register_oracle_evaluation(connection, payload)
    elif event_type == "oracle_prediction":
        register_oracle_prediction(connection, database, payload, base_dir)
    elif event_type == "metrics":
        record_metrics(connection, payload)
    elif event_type == "run_status":
        # Bind values and keep SQL identifiers fixed. Membership preserves the
        # difference between an omitted field and an explicit JSON null.
        updates = {
            "status": "UPDATE runs SET status = ? WHERE id = ?",
            "started_at": "UPDATE runs SET started_at = ? WHERE id = ?",
            "finished_at": "UPDATE runs SET finished_at = ? WHERE id = ?",
            "gpu_hours": "UPDATE runs SET gpu_hours = ? WHERE id = ?",
        }
        if not any(field in payload for field in updates):
            raise ValueError("run_status event has no status fields")
        for field, statement in updates.items():
            if field in payload:
                connection.execute(statement, (payload[field], payload["run_id"]))
    else:
        raise ValueError(f"Unsupported event type: {event_type}")


def register_criteria(connection: sqlite3.Connection, definition: Mapping[str, Any]) -> str:
    """Register an immutable criteria set from a JSON-compatible mapping."""
    criteria_set_id = str(definition.get("id") or _new_id("criteria"))
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"))
    existing = connection.execute(
        "SELECT definition_json FROM criteria_sets WHERE id = ?", (criteria_set_id,)
    ).fetchone()
    if existing:
        if existing["definition_json"] != canonical:
            raise ValueError(f"Criteria set {criteria_set_id} already exists with a different definition")
        return criteria_set_id
    entries = definition.get("criteria")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Criteria definition needs a non-empty criteria list")
    with connection:
        connection.execute(
            "INSERT INTO criteria_sets VALUES (?, ?, ?, ?, ?)",
            (criteria_set_id, _campaign_id(connection), definition.get("name", criteria_set_id), canonical, _now()),
        )
        for position, item in enumerate(entries, start=1):
            comparison = item["operator"]
            missing_policy = item.get("missing", "fail")
            if comparison not in COMPARISONS:
                raise ValueError(f"Unsupported comparison: {comparison}")
            if missing_policy not in {"fail", "error"}:
                raise ValueError(f"Unsupported missing policy: {missing_policy}")
            criterion_id = str(item.get("id") or f"{criteria_set_id}:{position}")
            connection.execute(
                "INSERT INTO criteria VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    criterion_id,
                    criteria_set_id,
                    position,
                    item.get("label", item["metric"]),
                    item["metric"],
                    item.get("oracle_role"),
                    comparison,
                    float(item["threshold"]),
                    missing_policy,
                ),
            )
    return criteria_set_id


def _metric_for_criterion(connection: sqlite3.Connection, design_id: str, criterion: sqlite3.Row) -> sqlite3.Row | None:
    """Return the latest matching observation, including missing or failed states."""
    query = """
        SELECT m.*
        FROM metric_observations m
        LEFT JOIN oracle_predictions p ON p.id = m.prediction_id
        LEFT JOIN oracle_evaluations e ON e.id = p.evaluation_id
        WHERE m.design_id = ? AND m.name = ?
    """
    params: list[Any] = [design_id, criterion["metric_name"]]
    if criterion["oracle_role"]:
        query += " AND e.role = ?"
        params.append(criterion["oracle_role"])
    query += " ORDER BY m.observed_at DESC, m.rowid DESC LIMIT 1"
    return connection.execute(query, params).fetchone()


def evaluate_passers(connection: sqlite3.Connection, criteria_set_id: str) -> dict[str, int]:
    """Append a decision when a design's evidence for immutable criteria changes."""
    criteria = connection.execute(
        "SELECT * FROM criteria WHERE criteria_set_id = ? ORDER BY position", (criteria_set_id,)
    ).fetchall()
    if not criteria:
        raise ValueError(f"Unknown or empty criteria set: {criteria_set_id}")
    designs = connection.execute("SELECT id FROM designs ORDER BY id").fetchall()
    counts = {"evaluated": 0, "passed": 0, "failed": 0}
    with connection:
        for design in designs:
            results = []
            for criterion in criteria:
                observation = _metric_for_criterion(connection, design["id"], criterion)
                if observation is None or observation["status"] != "computed" or observation["value_real"] is None:
                    if criterion["missing_policy"] == "error":
                        raise ValueError(f"Design {design['id']} lacks computed metric {criterion['metric_name']}")
                    results.append((criterion, observation, None, "missing", False))
                    continue
                actual = float(observation["value_real"])
                passed = bool(COMPARISONS[criterion["comparison"]](actual, criterion["threshold"]))
                results.append((criterion, observation, actual, "computed", passed))
            previous = connection.execute(
                "SELECT id, revision FROM latest_passer_evaluations WHERE design_id = ? AND criteria_set_id = ?",
                (design["id"], criteria_set_id),
            ).fetchone()
            if previous:
                previous_evidence = dict(connection.execute(
                    "SELECT criterion_id, metric_observation_id FROM criterion_results WHERE passer_evaluation_id = ?",
                    (previous["id"],),
                ).fetchall())
                current_evidence = {
                    criterion["id"]: observation["id"] if observation else None
                    for criterion, observation, *_ in results
                }
                if previous_evidence == current_evidence:
                    continue
            overall = all(result[4] for result in results)
            evaluation_id = _new_id("passer_eval")
            revision = previous["revision"] + 1 if previous else 1
            connection.execute(
                "INSERT INTO passer_evaluations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (evaluation_id, design["id"], criteria_set_id, int(overall), "complete", _now(), revision),
            )
            for criterion, observation, actual, status, passed in results:
                connection.execute(
                    "INSERT INTO criterion_results VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        evaluation_id,
                        criterion["id"],
                        observation["id"] if observation else None,
                        actual,
                        status,
                        int(passed),
                    ),
                )
            counts["evaluated"] += 1
            counts["passed" if overall else "failed"] += 1
    return counts


def reconcile(connection: sqlite3.Connection, database: str | Path) -> list[str]:
    """Return integrity problems without changing or deleting campaign records."""
    root = Path(database).resolve().parent
    problems = []
    for artifact in connection.execute("SELECT * FROM artifacts ORDER BY id"):
        path = root / artifact["relative_path"]
        if not path.is_file():
            problems.append(f"missing artifact {artifact['id']}: {artifact['relative_path']}")
        elif _sha256(path) != artifact["sha256"]:
            problems.append(f"checksum mismatch {artifact['id']}: {artifact['relative_path']}")
    empty_evaluations = connection.execute(
        """
        SELECT e.id FROM oracle_evaluations e
        LEFT JOIN oracle_predictions p ON p.evaluation_id = e.id
        WHERE e.status = 'completed'
        GROUP BY e.id HAVING COUNT(p.id) = 0
        """
    ).fetchall()
    problems.extend(f"completed oracle evaluation has no prediction: {row['id']}" for row in empty_evaluations)
    incomplete_evidence = connection.execute(
        """
        SELECT p.id, COUNT(r.criterion_id) AS observed, COUNT(c.id) AS expected
        FROM passer_evaluations p
        JOIN criteria c ON c.criteria_set_id = p.criteria_set_id
        LEFT JOIN criterion_results r
          ON r.passer_evaluation_id = p.id AND r.criterion_id = c.id
        GROUP BY p.id HAVING observed != expected
        """
    ).fetchall()
    problems.extend(f"incomplete passer evidence: {row['id']}" for row in incomplete_evidence)
    return problems


def export_metrics(connection: sqlite3.Connection, output: str | Path) -> Path:
    """Write one wide row per design with the latest actual value of every metric."""
    catalog = [dict(row) for row in connection.execute("SELECT * FROM design_catalog ORDER BY design_id")]
    observations = connection.execute(
        """
        SELECT m.* FROM metric_observations m
        WHERE m.rowid = (
            SELECT newest.rowid FROM metric_observations newest
            WHERE newest.design_id = m.design_id AND newest.name = m.name
            ORDER BY newest.observed_at DESC, newest.rowid DESC LIMIT 1
        )
        """
    ).fetchall()
    by_design: dict[str, dict[str, Any]] = {row["design_id"]: row for row in catalog}
    metric_names = sorted({row["name"] for row in observations})
    for observation in observations:
        value = observation["value_real"] if observation["value_real"] is not None else observation["value_text"]
        by_design[observation["design_id"]][observation["name"]] = value
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_columns = list(catalog[0]) if catalog else ["design_id"]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=base_columns + metric_names)
        writer.writeheader()
        writer.writerows(by_design.values())
    return output_path


def show_design(connection: sqlite3.Connection, design_id: str) -> dict[str, Any]:
    """Return complete human-auditable lineage for one design."""
    catalog = connection.execute("SELECT * FROM design_catalog WHERE design_id = ?", (design_id,)).fetchone()
    if catalog is None:
        raise ValueError(f"Unknown design: {design_id}")
    evaluations = []
    for evaluation in connection.execute(
        "SELECT * FROM oracle_evaluations WHERE design_id = ? ORDER BY created_at", (design_id,)
    ):
        item = dict(evaluation)
        item["predictions"] = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM oracle_predictions WHERE evaluation_id = ? ORDER BY id", (evaluation["id"],)
            )
        ]
        evaluations.append(item)
    metrics = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM metric_observations WHERE design_id = ? ORDER BY name, observed_at", (design_id,)
        )
    ]
    passers = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM passer_evaluations WHERE design_id = ? ORDER BY evaluated_at, rowid", (design_id,)
        )
    ]
    return {"design": dict(catalog), "oracle_evaluations": evaluations, "metrics": metrics, "passers": passers}


def _json_print(value: Any) -> None:
    """Print deterministic machine-readable command output."""
    print(json.dumps(value, indent=2, sort_keys=True))


def _add_database(parser: argparse.ArgumentParser) -> None:
    """Add the common campaign database argument."""
    parser.add_argument("--database", required=True, type=Path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command_name", required=True)

    command = commands.add_parser("init", help="initialize a campaign directory")
    command.add_argument("root", type=Path)
    command.add_argument("--name", required=True)
    command.add_argument("--objective", default="")
    command.add_argument("--campaign-id")
    command.add_argument("--rfproteina-revision")
    command.add_argument("--atomworks-revision")

    command = commands.add_parser("register-input", help="archive and register an annotated CIF")
    _add_database(command)
    command.add_argument("--name", required=True)
    command.add_argument("--cif", required=True, type=Path)
    command.add_argument("--input-id")
    command.add_argument("--parent-input-id")
    command.add_argument("--intent", default="")

    command = commands.add_parser("register-config", help="archive an exact resolved config")
    _add_database(command)
    command.add_argument("--name", required=True)
    command.add_argument("--resolved-config", required=True, type=Path)
    command.add_argument("--source-config", type=Path)
    command.add_argument("--config-id")
    command.add_argument("--override", action="append", default=[])

    command = commands.add_parser("plan-run", help="record a run before submission")
    _add_database(command)
    command.add_argument("--input-id", required=True)
    command.add_argument("--config-id", required=True)
    command.add_argument("--phase", required=True)
    command.add_argument("--command", required=True)
    command.add_argument("--out-dir", required=True)
    command.add_argument("--run-id")
    command.add_argument("--parent-run-id")
    for field in RUN_SCHEDULER_FIELDS:
        command.add_argument(f"--{field.replace('_', '-')}")

    command = commands.add_parser("ingest-events", help="transactionally import worker JSONL events")
    _add_database(command)
    command.add_argument("events", type=Path)

    command = commands.add_parser("register-criteria", help="register an immutable criteria JSON file")
    _add_database(command)
    command.add_argument("definition", type=Path)

    command = commands.add_parser("evaluate-passers", help="evaluate all designs against a criteria set")
    _add_database(command)
    command.add_argument("--criteria-set", required=True)

    command = commands.add_parser("reconcile", help="verify archived files and record relationships")
    _add_database(command)

    command = commands.add_parser("export", help="write a wide actual-metrics CSV")
    _add_database(command)
    command.add_argument("--output", required=True, type=Path)

    command = commands.add_parser("show-design", help="show complete lineage for one design")
    _add_database(command)
    command.add_argument("design_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ledger command and return a process status."""
    args = build_parser().parse_args(argv)
    if args.command_name == "init":
        database = initialize(
            args.root,
            args.name,
            args.objective,
            args.campaign_id,
            args.rfproteina_revision,
            args.atomworks_revision,
        )
        _json_print({"database": str(database)})
        return 0

    connection = connect(args.database)
    try:
        if args.command_name == "register-input":
            with connection:
                result = register_input(
                    connection,
                    args.database,
                    args.name,
                    args.cif,
                    args.input_id,
                    args.parent_input_id,
                    args.intent,
                )
            _json_print({"input_id": result})
        elif args.command_name == "register-config":
            with connection:
                result = register_config(
                    connection,
                    args.database,
                    args.name,
                    args.resolved_config,
                    args.config_id,
                    args.source_config,
                    args.override,
                )
            _json_print({"config_id": result})
        elif args.command_name == "plan-run":
            scheduler = {field: vars(args)[field] for field in RUN_SCHEDULER_FIELDS}
            with connection:
                result = plan_run(
                    connection,
                    input_id=args.input_id,
                    config_id=args.config_id,
                    phase=args.phase,
                    command=args.command,
                    out_dir=args.out_dir,
                    run_id=args.run_id,
                    parent_run_id=args.parent_run_id,
                    **scheduler,
                )
            _json_print({"run_id": result, "scheduler": scheduler})
        elif args.command_name == "ingest-events":
            _json_print(ingest_events(connection, args.database, args.events))
        elif args.command_name == "register-criteria":
            with args.definition.open() as handle:
                definition = json.load(handle)
            _json_print({"criteria_set_id": register_criteria(connection, definition)})
        elif args.command_name == "evaluate-passers":
            _json_print(evaluate_passers(connection, args.criteria_set))
        elif args.command_name == "reconcile":
            problems = reconcile(connection, args.database)
            _json_print({"ok": not problems, "problems": problems})
            return int(bool(problems))
        elif args.command_name == "export":
            _json_print({"output": str(export_metrics(connection, args.output))})
        elif args.command_name == "show-design":
            _json_print(show_design(connection, args.design_id))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
