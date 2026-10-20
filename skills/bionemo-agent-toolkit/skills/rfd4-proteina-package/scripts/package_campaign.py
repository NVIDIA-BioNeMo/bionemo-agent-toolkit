#!/usr/bin/env python
"""Build a simple shareable TAR of RFProteína designs and aligned refolds.

Usage: python package_campaign.py --database campaign.sqlite --criteria-set ID --output designs.tar
Arguments: Existing ledger, criteria-set ID, fresh output path; optional --package-name.
Output: A TAR containing the selected designs, aligned refolds, confidence files, and measured metrics.
Exit codes: 0 for success, 1 for missing/inconsistent data or runtime failure, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import biotite.structure as struc
import numpy as np
from atomworks.io import parse
from atomworks.io.utils.atom_array_plus import as_atom_array_plus
from atomworks.io.utils.compression import transfer_with_compression
from atomworks.io.utils.io_utils import to_cif_file
from biotite.structure import AtomArray

import rfproteina.conditions  # noqa: F401
from rfproteina.utils.parse_presets import ANNOTATED_CIF


def _safe_name(value: str) -> str:
    """Return a readable filename component without path or shell punctuation."""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return normalized or "unnamed"


def _load_cif(path: Path) -> AtomArray:
    """Load one CIF model with minimal structure preparation."""
    parsed = parse(path, config=ANNOTATED_CIF)
    assemblies = parsed.get("assemblies") or {}
    value = next(iter(assemblies.values())) if assemblies else parsed["asym_unit"]
    if isinstance(value, list | tuple) or hasattr(value, "stack_depth"):
        value = value[0]
    return as_atom_array_plus(value)


def _atom_key(array: AtomArray, index: int) -> tuple[str, int, str, str]:
    """Build a stable polymer atom key for correspondence matching."""
    categories = array.get_annotation_categories()
    insertion = str(array.ins_code[index]) if "ins_code" in categories else ""
    return (
        str(array.chain_id[index]),
        int(array.res_id[index]),
        insertion,
        str(array.atom_name[index]),
    )


def _matching_anchor_indices(
    reference: AtomArray, mobile: AtomArray, chains: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Match polymer anchors from every requested chain in both structures."""
    chain_set = set(chains)
    for label, array in (("design", reference), ("refold", mobile)):
        missing = chain_set - set(array.chain_id)
        if missing:
            raise ValueError(f"{label} is missing requested chain(s): {','.join(sorted(missing))}")
    priorities = (
        {"CA", "C4'"},
        {"N", "CA", "C", "O", "P", "C4'", "C3'", "C5'"},
    )
    for atom_names in priorities:
        ref_map = _anchor_map(reference, chain_set, atom_names)
        mobile_map = _anchor_map(mobile, chain_set, atom_names)
        common = sorted(ref_map.keys() & mobile_map.keys())
        covered_chains = {key[0] for key in common}
        if len(common) >= 3 and covered_chains == chain_set:
            return (
                np.asarray([ref_map[key] for key in common], dtype=int),
                np.asarray([mobile_map[key] for key in common], dtype=int),
            )
    raise ValueError(f"need at least three matching polymer anchors covering every requested chain: {','.join(chains)}")


def _anchor_map(array: AtomArray, chains: set[str], atom_names: set[str]) -> dict[tuple[str, int, str, str], int]:
    """Index unique selected polymer atoms by chain, residue, insertion, and name."""
    selected = np.isin(array.chain_id, list(chains)) & np.isin(array.atom_name, list(atom_names))
    mapping: dict[tuple[str, int, str, str], int] = {}
    for index in np.flatnonzero(selected):
        key = _atom_key(array, int(index))
        if key in mapping:
            raise ValueError(f"ambiguous alignment atom {key}")
        mapping[key] = int(index)
    return mapping


def align_refold(design_path: str | Path, refold_path: str | Path, output_path: str | Path, chains: str) -> Path:
    """Superimpose a refold on its design over recorded chains of interest."""
    chain_ids = [chain.strip() for chain in chains.split(",") if chain.strip()]
    if not chain_ids:
        raise ValueError("chain_of_interest is empty")
    design = _load_cif(Path(design_path))
    refold = _load_cif(Path(refold_path))
    reference_indices, mobile_indices = _matching_anchor_indices(design, refold, chain_ids)
    reference_coords = design.coord[reference_indices]
    mobile_coords = refold.coord[mobile_indices]
    if not np.isfinite(reference_coords).all() or not np.isfinite(mobile_coords).all():
        raise ValueError("alignment anchors contain non-finite coordinates")
    for coords in (reference_coords, mobile_coords):
        if np.linalg.matrix_rank(coords - coords.mean(axis=0)) < 2:
            raise ValueError("alignment requires at least three non-collinear anchors")
    _, transform = struc.superimpose(reference_coords, mobile_coords)
    aligned = transform.apply(refold)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    to_cif_file(aligned, destination, save_standard_annotations=False, extra_fields=[])
    return destination


def _connect(database: Path) -> sqlite3.Connection:
    """Open an existing reconciled campaign database with writes disabled."""
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _criteria(connection: sqlite3.Connection, criteria_set: str) -> list[sqlite3.Row]:
    """Return one criteria set in its declared waterfall order."""
    rows = connection.execute(
        "SELECT * FROM criteria WHERE criteria_set_id = ? ORDER BY position", (criteria_set,)
    ).fetchall()
    if not rows:
        raise ValueError(f"Unknown or empty criteria set: {criteria_set}")
    return rows


def _selected_designs(connection: sqlite3.Connection, criteria_set: str) -> list[dict[str, Any]]:
    """Return all passers with direct input/config/design paths."""
    rows = connection.execute(
        """
        SELECT dc.*, pe.id AS passer_evaluation_id
        FROM design_catalog dc
        JOIN latest_passer_evaluations pe ON pe.design_id = dc.design_id
        WHERE pe.criteria_set_id = ? AND pe.passed = 1 AND pe.status = 'complete'
        ORDER BY dc.input_name, dc.design_id
        """,
        (criteria_set,),
    ).fetchall()
    if not rows:
        raise ValueError(f"Criteria set {criteria_set} has no passers")
    return [dict(row) for row in rows]


def _criterion_columns(criteria: Sequence[sqlite3.Row]) -> dict[str, str]:
    """Assign explicit unique CSV columns to criterion metric values."""
    base_names = [str(row["metric_name"]) for row in criteria]
    duplicates = {name for name, count in Counter(base_names).items() if count > 1}
    columns = {}
    for row in criteria:
        name = str(row["metric_name"])
        if name in duplicates:
            role = row["oracle_role"] or row["label"]
            name = f"{role}.{name}"
        columns[str(row["id"])] = name
    if len(set(columns.values())) != len(columns):
        raise ValueError("criteria do not resolve to unique metrics.csv column names")
    return columns


def _criterion_results(
    connection: sqlite3.Connection, criteria_set: str
) -> tuple[dict[tuple[str, str], sqlite3.Row], dict[str, str]]:
    """Return exact evidence values and passer-evaluation ownership per design."""
    rows = connection.execute(
        """
        SELECT pe.design_id, pe.id AS passer_evaluation_id, cr.*
        FROM latest_passer_evaluations pe
        JOIN criterion_results cr ON cr.passer_evaluation_id = pe.id
        WHERE pe.criteria_set_id = ?
        """,
        (criteria_set,),
    ).fetchall()
    results = {(str(row["design_id"]), str(row["criterion_id"])): row for row in rows}
    evaluations = {str(row["design_id"]): str(row["passer_evaluation_id"]) for row in rows}
    return results, evaluations


def _predictions(connection: sqlite3.Connection, design_id: str) -> list[sqlite3.Row]:
    """Return every produced oracle prediction linked to one design."""
    return connection.execute(
        """
        SELECT
            p.id AS prediction_id,
            p.seed,
            p.sample_index,
            p.rank,
            e.id AS evaluation_id,
            e.role,
            e.backend,
            a.relative_path AS prediction_path,
            confidence.relative_path AS confidence_path
        FROM oracle_predictions p
        JOIN oracle_evaluations e ON e.id = p.evaluation_id
        JOIN artifacts a ON a.id = p.structure_artifact_id
        LEFT JOIN artifacts confidence ON confidence.id = p.confidence_artifact_id
        WHERE e.design_id = ? AND p.status = 'completed'
        ORDER BY e.role, e.backend, p.rank, p.id
        """,
        (design_id,),
    ).fetchall()


def _write_metrics(
    path: Path,
    designs: Sequence[dict[str, Any]],
    criteria: Sequence[sqlite3.Row],
    columns: dict[str, str],
    results: dict[tuple[str, str], sqlite3.Row],
) -> None:
    """Write one design row with actual criterion values and packaged refold names."""
    base = ["input_cif", "design_id", "design_cif", "search_config", "refolds"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=base + [columns[str(row["id"])] for row in criteria])
        writer.writeheader()
        for design in designs:
            row = {
                "input_cif": design["package_input"],
                "design_id": design["design_id"],
                "design_cif": design["package_design"],
                "search_config": design["config_name"],
                "refolds": ";".join(design["package_refolds"]),
            }
            for criterion in criteria:
                evidence = results.get((design["design_id"], str(criterion["id"])))
                if evidence is None or evidence["actual_value"] is None:
                    raise ValueError(
                        f"Selected design {design['design_id']} lacks actual value for criterion {criterion['id']}"
                    )
                row[columns[str(criterion["id"])]] = evidence["actual_value"]
            writer.writerow(row)


def _waterfall_rows(
    design_ids: Iterable[str],
    criteria: Sequence[sqlite3.Row],
    results: dict[tuple[str, str], sqlite3.Row],
) -> list[dict[str, Any]]:
    """Compute a deterministic cumulative waterfall from recorded criterion evidence."""
    survivors = set(design_ids)
    rows = []
    for criterion in criteria:
        starting = len(survivors)
        passed = {
            design_id
            for design_id in survivors
            if (result := results.get((design_id, str(criterion["id"])))) is not None and result["passed"]
        }
        rows.append(
            {
                "label": criterion["label"],
                "metric": criterion["metric_name"],
                "definition": f"{criterion['comparison']} {criterion['threshold']:g}",
                "missing": criterion["missing_policy"],
                "starting": starting,
                "passed": len(passed),
                "failed": starting - len(passed),
                "remaining": len(passed),
            }
        )
        survivors = passed
    return rows


def _waterfall_table(rows: Sequence[dict[str, Any]]) -> str:
    """Format one cumulative waterfall as Markdown."""
    lines = [
        "| Filter | Metric | Definition | Missing | Starting | Passed | Failed | Remaining |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | `{row['metric']}` | `{row['definition']}` | {row['missing']} | "
            f"{row['starting']} | {row['passed']} | {row['failed']} | {row['remaining']} |"
        )
    return "\n".join(lines)


def _write_waterfall(
    path: Path,
    criteria_set: str,
    all_designs: Sequence[sqlite3.Row],
    criteria: Sequence[sqlite3.Row],
    results: dict[tuple[str, str], sqlite3.Row],
) -> None:
    """Write exact overall and per-input filter waterfalls."""
    by_input: dict[str, list[str]] = defaultdict(list)
    for row in all_designs:
        by_input[str(row["input_name"])].append(str(row["design_id"]))
    lines = [
        "# Filter waterfall",
        "",
        f"Criteria set: `{criteria_set}`. Values used for selected designs are in `metrics.csv`.",
        "",
        "## Overall",
        "",
        _waterfall_table(_waterfall_rows((row["design_id"] for row in all_designs), criteria, results)),
    ]
    for input_name, design_ids in sorted(by_input.items()):
        lines.extend(
            [
                "",
                f"## Input: {input_name}",
                "",
                _waterfall_table(_waterfall_rows(design_ids, criteria, results)),
            ]
        )
    path.write_text("\n".join(lines) + "\n")


def _write_readme(
    path: Path,
    package_name: str,
    criteria_set: str,
    designs: Sequence[dict[str, Any]],
    roles: set[str],
    backends: set[str],
) -> None:
    """Write the concise recipient guide."""
    inputs = {design["input_id"] for design in designs}
    lines = [
        f"# {package_name}",
        "",
        f"This package contains {len(designs)} RFProteína designs selected by criteria set "
        f"`{criteria_set}`, grouped under {len(inputs)} exact annotated-CIF inputs.",
        "",
        "Each design directory contains the generated design and every linked oracle refold. "
        "Refolds are superimposed onto that design using its recorded chain of interest; the "
        "design is the oracle input and remains in its original frame. Available confidence JSON "
        "is placed beside the corresponding refold.",
        "",
        "- `WATERFALL.md` gives the exact cumulative filters and thresholds.",
        "- `metrics.csv` gives the actual metric values used for selection, not Boolean filter flags.",
        "- `inputs/` contains the annotated CIFs.",
        "- `outputs/` groups designs and refolds by annotated-CIF input.",
        f"- Oracle roles: {', '.join(sorted(roles)) if roles else 'none'}.",
        f"- Oracle backends: {', '.join(sorted(backends)) if backends else 'none'}.",
        "",
        "Computational metrics and oracle confidence are proxies, not experimental validation.",
    ]
    path.write_text("\n".join(lines) + "\n")


def _write_tar(source: Path, output: Path) -> None:
    """Create a deterministically ordered TAR or gzip-compressed TAR."""
    output.parent.mkdir(parents=True, exist_ok=True)
    file_handle = output.open("wb")
    gzip_handle = None
    try:
        if output.name.endswith((".tar.gz", ".tgz")):
            gzip_handle = gzip.GzipFile(filename="", mode="wb", fileobj=file_handle, mtime=0)
            archive = tarfile.open(fileobj=gzip_handle, mode="w")  # noqa: SIM115
        elif output.name.endswith(".tar"):
            archive = tarfile.open(fileobj=file_handle, mode="w")  # noqa: SIM115
        else:
            raise ValueError("output must end in .tar, .tar.gz, or .tgz")
        with archive:
            for path in sorted([source, *source.rglob("*")], key=lambda item: item.as_posix()):
                info = archive.gettarinfo(str(path), arcname=str(path.relative_to(source.parent)))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if path.is_file():
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)
                else:
                    archive.addfile(info)
    finally:
        if gzip_handle is not None:
            gzip_handle.close()
        file_handle.close()


def _validate_tar(output: Path, package_name: str, expected_designs: int) -> None:
    """Reopen the archive and verify its required simple layout."""
    with tarfile.open(output, "r:*") as archive:
        names = set(archive.getnames())
    required = {
        f"{package_name}/README.md",
        f"{package_name}/WATERFALL.md",
        f"{package_name}/metrics.csv",
        f"{package_name}/inputs",
        f"{package_name}/outputs",
    }
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"finished archive lacks required paths: {missing}")
    design_files = [name for name in names if name.endswith("__design.cif")]
    if len(design_files) != expected_designs:
        raise ValueError(f"expected {expected_designs} design CIFs, found {len(design_files)}")


def build_package(database: str | Path, criteria_set: str, output: str | Path, package_name: str | None = None) -> Path:
    """Build and validate a database-free design package TAR."""
    database_path = Path(database).resolve()
    output_path = Path(output).resolve()
    if output_path.exists():
        raise FileExistsError(f"Package output already exists: {output_path}")
    root = database_path.parent
    connection = _connect(database_path)
    try:
        # Keep selection, evidence, and waterfall on one read-only snapshot.
        connection.execute("BEGIN")
        if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
            raise RuntimeError("Run the updated campaign_ledger.py evaluate-passers command before packaging to upgrade the ledger")
        criteria = _criteria(connection, criteria_set)
        columns = _criterion_columns(criteria)
        results, _ = _criterion_results(connection, criteria_set)
        designs = _selected_designs(connection, criteria_set)
        all_designs = connection.execute(
            """
            SELECT dc.design_id, dc.input_name
            FROM design_catalog dc
            JOIN latest_passer_evaluations pe ON pe.design_id = dc.design_id
            WHERE pe.criteria_set_id = ? ORDER BY dc.design_id
            """,
            (criteria_set,),
        ).fetchall()
        default_name = output_path.name.removesuffix(".tar.gz").removesuffix(".tgz").removesuffix(".tar")
        name = _safe_name(package_name or default_name)
        roles: set[str] = set()
        backends: set[str] = set()
        with tempfile.TemporaryDirectory(prefix="rfproteina_package_") as temporary:
            package_root = Path(temporary) / name
            inputs_dir = package_root / "inputs"
            outputs_dir = package_root / "outputs"
            inputs_dir.mkdir(parents=True)
            outputs_dir.mkdir()
            input_names: dict[str, str] = {}
            for design in designs:
                input_group = f"{_safe_name(design['input_name'])}__{_safe_name(design['input_id'])}"
                input_file = f"{input_group}.cif"
                if design["input_id"] not in input_names:
                    transfer_with_compression(root / design["input_cif_path"], inputs_dir / input_file)
                    input_names[design["input_id"]] = input_file
                design_dir = outputs_dir / input_group / _safe_name(design["design_id"])
                design_dir.mkdir(parents=True, exist_ok=True)
                design_filename = f"{_safe_name(design['design_id'])}__design.cif"
                design_destination = design_dir / design_filename
                transfer_with_compression(root / design["design_cif_path"], design_destination)
                design["package_input"] = f"inputs/{input_file}"
                design["package_design"] = design_destination.relative_to(package_root).as_posix()
                design["package_refolds"] = []
                for prediction in _predictions(connection, design["design_id"]):
                    role = _safe_name(prediction["role"])
                    backend = _safe_name(prediction["backend"])
                    prediction_id = _safe_name(prediction["prediction_id"])
                    stem = f"{_safe_name(design['design_id'])}__{role}__{backend}__{prediction_id}"
                    refold_destination = design_dir / f"{stem}__refold.cif"
                    align_refold(
                        design_destination,
                        root / prediction["prediction_path"],
                        refold_destination,
                        design["chain_of_interest"],
                    )
                    design["package_refolds"].append(refold_destination.relative_to(package_root).as_posix())
                    roles.add(str(prediction["role"]))
                    backends.add(str(prediction["backend"]))
                    if prediction["confidence_path"]:
                        confidence_destination = design_dir / f"{stem}__confidence.json"
                        shutil.copy2(root / prediction["confidence_path"], confidence_destination)
            _write_metrics(package_root / "metrics.csv", designs, criteria, columns, results)
            _write_waterfall(package_root / "WATERFALL.md", criteria_set, all_designs, criteria, results)
            _write_readme(package_root / "README.md", name, criteria_set, designs, roles, backends)
            try:
                _write_tar(package_root, output_path)
                _validate_tar(output_path, name, len(designs))
            except Exception:
                output_path.unlink(missing_ok=True)
                raise
    finally:
        connection.close()
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Build the package command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--criteria-set", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--package-name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build one package and print its path."""
    args = build_parser().parse_args(argv)
    output = build_package(args.database, args.criteria_set, args.output, args.package_name)
    print(json.dumps({"output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
