#!/usr/bin/env python3
"""Unified CLI for the Genomic Intelligence DNA-sequence tasks.

One entry point covers all six tasks exposed by the hosted
``/v1/tasks/{task}/predict`` contract:

    promoter · splice · enhancer · chromatin · expression · annotation

It parses a single-record FASTA, calls the API (sync, or async for
``annotation``), and writes ``report.md`` + ``result.json`` +
``reproducibility/`` to the output directory.

Usage:
    python scripts/gi_predict.py --task promoter --demo
    python scripts/gi_predict.py --task splice --input my.fa --output out/
    python scripts/gi_predict.py --task expression --demo --description "K562 cells"

Auth: set GI_API_KEY in the environment (see references/authentication.md).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Self-contained: import the sibling client module regardless of CWD.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from gi_client import Client, GIError, read_fasta  # noqa: E402

SKILL_DIR = SCRIPT_DIR.parent
DEMO_DIR = SKILL_DIR / "assets" / "demo"

DISCLAIMER = (
    "Genomic Intelligence is a research tool. It is not a medical device and "
    "does not provide clinical diagnoses. Consult a qualified professional "
    "before making any medical decisions."
)


class TaskSpec:
    """Per-task metadata: input bounds, async flag, demo fixture."""

    def __init__(
        self,
        min_bp: int,
        max_bp: int,
        async_mode: bool,
        demo: str,
        exact_bp: Optional[int] = None,
    ) -> None:
        self.min_bp = min_bp
        self.max_bp = max_bp
        self.async_mode = async_mode
        self.demo = demo
        self.exact_bp = exact_bp

    def validate(self, length: int) -> Optional[str]:
        if self.exact_bp is not None and length != self.exact_bp:
            return f"expects exactly {self.exact_bp:,} bp, got {length:,} bp"
        if length < self.min_bp:
            return f"sequence too short: {length:,} bp < {self.min_bp:,} bp minimum"
        if length > self.max_bp:
            return f"sequence too long: {length:,} bp > {self.max_bp:,} bp maximum"
        return None


# Bounds mirror gpu_service/config/models.yaml + core/limits.py. The expression
# task requires an exact 9,198 bp TSS-centred window; all others accept 1..500kb.
TASKS: Dict[str, TaskSpec] = {
    "promoter": TaskSpec(1, 500_000, False, "promoter_tp53.fa"),
    "splice": TaskSpec(1, 500_000, False, "splice_hbb.fa"),
    "enhancer": TaskSpec(1, 500_000, False, "enhancer_eve.fa"),
    "chromatin": TaskSpec(1, 500_000, False, "chromatin_active_promoter_chr19.fa"),
    "expression": TaskSpec(9_198, 9_198, False, "expression_hbb_k562.fa", exact_bp=9_198),
    "annotation": TaskSpec(1, 500_000, True, "annotation_tp53.fa"),
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Genomic Intelligence DNA-sequence prediction (one CLI, six tasks)."
    )
    p.add_argument(
        "--task",
        required=True,
        choices=sorted(TASKS),
        help="Which prediction task to run.",
    )
    p.add_argument("--input", type=Path, dest="input_file", help="Input FASTA (single record).")
    p.add_argument("--output", type=Path, default=None, help="Output directory (default: /tmp/gi-<task>).")
    p.add_argument("--demo", action="store_true", help="Run with the bundled example FASTA for the task.")
    p.add_argument("--model", type=str, default=None, help="Override the default model for the task.")
    p.add_argument(
        "--description",
        type=str,
        default=None,
        help="Cell type / assay context. REQUIRED by expression; ignored by other tasks.",
    )
    p.add_argument("--api-key", type=str, default=None, help="Override GI_API_KEY env.")
    p.add_argument("--base-url", type=str, default=None, help="Override GI_BASE_URL (default: https://api.genomicintelligence.ai).")
    return p.parse_args()


def _resolve_input(args: argparse.Namespace, spec: TaskSpec) -> Path:
    if args.demo or args.input_file is None:
        demo_path = DEMO_DIR / spec.demo
        if not demo_path.exists():
            print(f"Error: bundled demo fixture missing at {demo_path}", file=sys.stderr)
            sys.exit(1)
        return demo_path
    if not args.input_file.exists():
        print(f"Error: --input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    return args.input_file


# Per-item arrays that belong in result.json, not in the compact stdout payload.
_BULKY_SUMMARY_KEYS = {"regions", "sites", "transcripts", "raw_summary"}


def _summarize(task: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the most useful headline numbers per task from `data`."""
    data = body.get("data") or {}
    summary = data.get("summary") or {}
    out: Dict[str, Any] = {"task": task, "model": data.get("model")}
    if task == "promoter":
        out["promoter_windows"] = summary.get("promoter_windows")
        out["total_windows"] = summary.get("total_windows")
        out["regions"] = data.get("regions") or []
    elif task == "splice":
        out["sites_found"] = summary.get("total_sites", summary.get("sites_found"))
        out["donor_sites"] = summary.get("donor_sites")
        out["acceptor_sites"] = summary.get("acceptor_sites")
        out["sites"] = data.get("sites") or []
    elif task == "enhancer":
        out["windows_processed"] = summary.get("total_windows", summary.get("windows_processed"))
        out["dev_score_max"] = summary.get("dev_score_max")
        out["hk_score_max"] = summary.get("hk_score_max")
    elif task == "chromatin":
        out["windows_processed"] = summary.get("total_windows", summary.get("windows_processed"))
        out["total_annotations"] = summary.get("total_annotations")
    elif task == "expression":
        pred = data.get("prediction") or {}
        out["log_tpm"] = pred.get("expression_log_tpm")
        out["tpm"] = pred.get("expression_tpm")
    elif task == "annotation":
        out["transcripts_found"] = summary.get("total_transcripts", summary.get("transcripts_found"))
        out["transcripts"] = data.get("transcripts") or []
    out["raw_summary"] = summary
    return out


def _fmt(v: Any, spec: str = ".3f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) else str(v)


def _headline_lines(task: str, summary: Dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if task == "promoter":
        lines.append(
            f"- Promoter windows: **{summary.get('promoter_windows', 0)}** / "
            f"{summary.get('total_windows', 0)} total"
        )
        regions = summary.get("regions") or []
        if regions:
            lines += ["", "| Name | Start | End | Score |", "|---|---|---|---|"]
            for r in regions[:20]:
                lines.append(
                    f"| {r.get('name', '-')} | {r.get('start', '-')} | "
                    f"{r.get('end', '-')} | {_fmt(r.get('score', '-'))} |"
                )
    elif task == "splice":
        lines.append(
            f"- Splice sites found: **{summary.get('sites_found') or 0}** "
            f"({summary.get('donor_sites') or 0} donor + {summary.get('acceptor_sites') or 0} acceptor)"
        )
        sites = (summary.get("sites") or [])[:20]
        if sites:
            lines += ["", "| Name | Start | Type | Score |", "|---|---|---|---|"]
            for s in sites:
                lines.append(
                    f"| {s.get('name', '-')} | {s.get('start', '-')} | "
                    f"{s.get('site_type', '-')} | {_fmt(s.get('score', '-'))} |"
                )
    elif task == "enhancer":
        lines.append(f"- Windows processed: **{summary.get('windows_processed') or 0}**")
        dev, hk = summary.get("dev_score_max"), summary.get("hk_score_max")
        if dev is not None:
            lines.append(f"- Max developmental-enhancer score: **{_fmt(dev)}**")
        if hk is not None:
            lines.append(f"- Max housekeeping-enhancer score: **{_fmt(hk)}**")
    elif task == "chromatin":
        lines.append(f"- Windows processed: **{summary.get('windows_processed') or 0}**")
        lines.append(f"- Total annotations across all tracks: **{summary.get('total_annotations') or 0}**")
    elif task == "expression":
        log_tpm, tpm = summary.get("log_tpm"), summary.get("tpm")
        if log_tpm is not None:
            tail = f" ≈ {tpm:.2f} TPM" if isinstance(tpm, (int, float)) else ""
            lines.append(f"- Predicted expression: **{_fmt(log_tpm, '.4f')} log(TPM+1)**{tail}")
        else:
            lines.append("- See `result.json` for the full prediction payload.")
    elif task == "annotation":
        lines.append(f"- Transcripts found: **{summary.get('transcripts_found') or 0}**")
        tx = (summary.get("transcripts") or [])[:20]
        if tx:
            lines += ["", "| Name | Start | End | Strand | Score |", "|---|---|---|---|---|"]
            for t in tx:
                lines.append(
                    f"| {t.get('name', '-')} | {t.get('start', '-')} | "
                    f"{t.get('end', '-')} | {t.get('strand', '-')} | {_fmt(t.get('score', '-'))} |"
                )
    return lines


def _repro_command(
    task: str,
    input_path: Path,
    output_dir: Path,
    model: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Build the exact re-runnable invocation for reproducibility/command.sh.

    Emits --model and --description only when they were supplied, so a replay
    reproduces the original call: expression requires --description (no default),
    and a non-default --model must survive. Uses python3 and shell-quotes every
    value so paths/descriptions with spaces round-trip.
    """
    parts = [
        "python3 scripts/gi_predict.py",
        f"--task {task}",
        f"--input {shlex.quote(str(input_path))}",
        f"--output {shlex.quote(str(output_dir))}",
    ]
    if model:
        parts.append(f"--model {shlex.quote(model)}")
    if description is not None:
        parts.append(f"--description {shlex.quote(description)}")
    return " ".join(parts)


def _write_report(
    task: str,
    summary: Dict[str, Any],
    body: Dict[str, Any],
    output_dir: Path,
    input_path: Path,
    sequence_name: str,
    sequence_length: int,
    elapsed_ms: float,
    model: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps({"summary": summary, "full_response": body}, indent=2)
    )

    meta = body.get("meta") or {}
    report_model = summary.get("model") or "—"  # effective model for the report
    lines = [
        f"# Genomic Intelligence — {task} report",
        "",
        f"- **Sequence**: `{sequence_name}` ({sequence_length:,} bp)",
        f"- **Input file**: `{input_path}`",
        f"- **Model**: `{report_model}`",
        f"- **Inference time**: {_fmt(meta.get('inference_time_ms', elapsed_ms), '.0f')} ms",
        f"- **Request ID**: `{meta.get('request_id', '—')}`",
        f"- **Generated**: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Headline result",
        "",
        *_headline_lines(task, summary),
        "",
        "## Reproducibility",
        "",
        "- `reproducibility/command.sh` — exact invocation",
        "- `result.json` — full `{data, meta}` response from the API",
        "",
        "## API",
        "",
        f"`POST /v1/tasks/{task}/predict` on `https://api.genomicintelligence.ai` "
        "— see <https://docs.genomicintelligence.ai>.",
        "",
        "---",
        "",
        f"_{DISCLAIMER}_",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(lines))

    repro = output_dir / "reproducibility"
    repro.mkdir(exist_ok=True)
    cmd = _repro_command(task, input_path, output_dir, model, description) + "\n"
    (repro / "command.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + cmd)
    (repro / "command.sh").chmod(0o755)
    (repro / "environment.json").write_text(
        json.dumps(
            {
                "skill": "genomic-intelligence-nim",
                "skill_version": "0.1.0",
                "task": task,
                "api_base_url": os.environ.get("GI_BASE_URL", "https://api.genomicintelligence.ai"),
                "model": summary.get("model"),
                "request_id": meta.get("request_id"),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
        )
    )


def main() -> int:
    args = _parse_args()
    task = args.task
    spec = TASKS[task]
    output_dir = args.output or Path(f"/tmp/gi-{task}")

    input_path = _resolve_input(args, spec)
    sequence_name, sequence = read_fasta(input_path)
    if not sequence:
        print(f"Error: parsed an empty sequence from {input_path}", file=sys.stderr)
        return 1

    length_err = spec.validate(len(sequence))
    if length_err:
        print(f"[gi-{task}] invalid input — {length_err}", file=sys.stderr)
        if task == "expression":
            print(
                "  The expression model takes an exact 9,198 bp window centred on a TSS. "
                "See references/tasks.md#expression.",
                file=sys.stderr,
            )
        return 1

    if task == "expression" and not args.description:
        print(
            "[gi-expression] --description is required (e.g. \"K562 cells\"). "
            "It selects the expression context. See references/tasks.md#expression.",
            file=sys.stderr,
        )
        return 1

    try:
        client = Client(api_key=args.api_key, base_url=args.base_url)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    options: Dict[str, Any] = {}
    if args.description is not None:
        options["description"] = args.description

    print(
        f"[gi-{task}] sequence_name={sequence_name} length={len(sequence):,} bp "
        f"model={args.model or 'default'} mode={'async' if spec.async_mode else 'sync'}",
        file=sys.stderr,
    )
    started = time.monotonic()
    try:
        if spec.async_mode:
            job_id = client.submit_async(
                task, sequence=sequence, sequence_name=sequence_name,
                model=args.model, options=options or None,
            )
            print(f"[gi-{task}] submitted job_id={job_id}", file=sys.stderr)

            def _progress(p: Dict[str, Any]) -> None:
                pct, msg = p.get("percent"), p.get("message", "")
                if pct is not None:
                    print(f"  {pct:>3}% {msg}", file=sys.stderr)

            body = client.wait_for_job(job_id, on_progress=_progress)
        else:
            body = client.predict(
                task, sequence=sequence, sequence_name=sequence_name,
                model=args.model, options=options or None,
            )
    except GIError as e:
        print(f"[gi-{task}] API error: {e}", file=sys.stderr)
        return 2

    elapsed_ms = (time.monotonic() - started) * 1000.0
    summary = _summarize(task, body)
    _write_report(
        task, summary, body, output_dir, input_path, sequence_name, len(sequence),
        elapsed_ms, model=args.model, description=args.description,
    )
    print(f"[gi-{task}] OK — wrote {output_dir}/report.md ({elapsed_ms:.0f} ms wall)", file=sys.stderr)

    # stdout = a compact machine-readable summary so the agent gets the answer
    # inline without reading a file. The bulky per-item arrays (regions / sites /
    # transcripts) stay in result.json — only headline scalars go here.
    meta = body.get("meta") or {}
    headline = {k: v for k, v in summary.items() if k not in _BULKY_SUMMARY_KEYS}
    stdout_payload = {
        "ok": True,
        "task": task,
        "sequence_name": sequence_name,
        "sequence_length_bp": len(sequence),
        "model": summary.get("model"),
        "request_id": meta.get("request_id"),
        "inference_time_ms": meta.get("inference_time_ms"),
        "result": headline,
        "artifacts": {
            "output_dir": str(output_dir),
            "report": str(output_dir / "report.md"),
            "result_json": str(output_dir / "result.json"),
        },
    }
    print(json.dumps(stdout_payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
