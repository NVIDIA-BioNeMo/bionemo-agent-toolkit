#!/usr/bin/env python3
"""Unified CLI for the Genomic Intelligence DNA-sequence tasks.

One entry point covers all six tasks exposed by the hosted API. Each is its own
published operation at ``/v1/tasks/<task>/predict``, with a separate request
schema per task:

    promoter · splice · enhancer · chromatin · expression · annotation

It parses a single-record FASTA, calls the API, and writes ``report.md`` +
``result.json`` + ``reproducibility/`` to the output directory. Delivery is
synchronous except for ``annotation``, which defaults to async because it is
slow — the API accepts either mode on every task.

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
import requests  # noqa: E402  (transport errors surface at the call boundary)

from gi_client import Client, FastaError, GIError, read_fasta  # noqa: E402

SKILL_DIR = SCRIPT_DIR.parent
DEMO_DIR = SKILL_DIR / "assets" / "demo"

DISCLAIMER = (
    "Genomic Intelligence is a research tool. It is not a medical device and "
    "does not provide clinical diagnoses. Consult a qualified professional "
    "before making any medical decisions."
)


class TaskSpec:
    """Per-task metadata: input bounds, default delivery mode, demo fixture."""

    def __init__(
        self,
        min_bp: int,
        max_bp: int,
        async_default: bool,
        demo: str,
        window_bp: Optional[int] = None,
    ) -> None:
        self.min_bp = min_bp
        self.max_bp = max_bp
        # Delivery mode this runner picks by default. The API accepts BOTH
        # modes on every task (Prefer: respond-async is a per-request header),
        # so this is a latency choice, not a constraint.
        self.async_default = async_default
        self.demo = demo
        # Fixed scoring-window width, if the task has one (expression: 9,198 bp).
        # Anything longer than the window needs an explicit --tss-index.
        self.window_bp = window_bp

    def validate(self, length: int) -> Optional[str]:
        if length < self.min_bp:
            return f"sequence too short: {length:,} bp < {self.min_bp:,} bp minimum"
        if length > self.max_bp:
            return f"sequence too long: {length:,} bp > {self.max_bp:,} bp maximum"
        return None


# These bounds are a LOCAL MIRROR, not the authority. The authority is the
# `minLength`/`maxLength` published on each task's request schema in the live
# OpenAPI doc (https://api.genomicintelligence.ai/v1/openapi.json). Re-read it
# if a rejection here disagrees with the server.
#
# Each task has its own floor — the strictest its models need — enforced at
# request validation before any model loads. There are no per-model floors, so
# --model can never make a rejected length legal. The floor is admission control, NOT a statement about
# regime: a sequence above the floor but shorter than the selected model's
# `bio_spec.context_window_bp` is accepted and scored against a window padded out
# to the context window. Compare your length against `context_window_bp` (from
# GET /v1/tasks/{task}/models) to know whether the model saw real sequence or
# padding. Every task caps at 500,000 bp. Under-floor and over-max are both
# 422 validation_failed server-side — a 413 means the 16 MiB raw-body cap, never
# a long sequence.
PROMOTER_MIN_BP = 300
SPLICE_MIN_BP = 100
ENHANCER_MIN_BP = 50
CHROMATIN_MIN_BP = 200
ANNOTATION_MIN_BP = 1_000
MAX_BP = 500_000

# expression's floor is also the width of the single window the model scores:
# sequence[tss_index-4599 : tss_index+4599]. Send a pre-cut 9,198 bp window, or
# send up to 500 kb plus --tss-index and let the server slice.
#
# The default path is deliberately stricter than the API: with no --tss-index,
# this client requires *exactly* 9,198 bp rather than merely at-or-above the
# floor. That is the tripwire — the server will happily score a 9,198 bp window
# cut from the wrong place and return a confident 200, and there is no
# client-side tell for a mis-centred window. Requiring the exact width keeps the
# caller visibly responsible for TSS-centring. --tss-index is the explicit
# opt-in that widens the accepted range to the full 9,198–500,000 bp the API
# allows and hands the cut to the server; it is range-checked below, and what
# was actually scored is echoed back from response meta rather than assumed.
EXPRESSION_WINDOW_BP = 9_198
EXPRESSION_TSS_RADIUS = EXPRESSION_WINDOW_BP // 2  # 4,599

TASKS: Dict[str, TaskSpec] = {
    "promoter": TaskSpec(PROMOTER_MIN_BP, MAX_BP, False, "promoter_tp53.fa"),
    "splice": TaskSpec(SPLICE_MIN_BP, MAX_BP, False, "splice_hbb.fa"),
    "enhancer": TaskSpec(ENHANCER_MIN_BP, MAX_BP, False, "enhancer_eve.fa"),
    "chromatin": TaskSpec(CHROMATIN_MIN_BP, MAX_BP, False, "chromatin_active_promoter_chr19.fa"),
    "expression": TaskSpec(
        EXPRESSION_WINDOW_BP, MAX_BP, False, "expression_hbb_k562.fa",
        window_bp=EXPRESSION_WINDOW_BP,
    ),
    "annotation": TaskSpec(ANNOTATION_MIN_BP, MAX_BP, True, "annotation_tp53.fa"),
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
        help=(
            "Cell type / assay context. REQUIRED by expression; not accepted by "
            "any other task (their options objects are closed), so it is dropped "
            "with a warning if passed elsewhere."
        ),
    )
    p.add_argument(
        "--tss-index",
        type=int,
        default=None,
        dest="tss_index",
        help=(
            "expression only: 0-based TSS offset into the sequence (whitespace "
            "stripped). REQUIRED unless the sequence is exactly 9,198 bp. The "
            "server scores sequence[tss_index-4599 : tss_index+4599]."
        ),
    )
    p.add_argument("--api-key", type=str, default=None, help="Override GI_API_KEY env.")
    p.add_argument("--base-url", type=str, default=None, help="Override GI_BASE_URL (default: https://api.genomicintelligence.ai).")
    return p.parse_args()


def _resolve_input(args: argparse.Namespace, spec: TaskSpec) -> Path:
    # Running the demo has to be asked for. Falling back to it when --input is
    # simply absent produces a full report, with a real request id and real
    # scores, for a sequence the caller never supplied — and nothing in the
    # output says so.
    if not args.demo and args.input_file is None:
        print(
            "Error: no input. Pass --input <FASTA>, or --demo to run the "
            f"bundled {spec.demo} fixture.",
            file=sys.stderr,
        )
        sys.exit(2)
    if args.demo:
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


class ResponseShapeError(RuntimeError):
    """A 2xx body whose nested fields contradict their documented types.

    Distinct from `GIError`, which covers what the API itself reported. This is
    a well-formed envelope carrying a field the contract says is an object or an
    array and that arrived as something else.
    """


def _as_obj(v: Any, field: str) -> Dict[str, Any]:
    """Read a response field documented as an object.

    `_require_envelope` guarantees `data` is a non-empty object; it deliberately
    does not police per-task fields nested inside it, because it is shared by
    six tasks and must not encode any one task's schema. So the checking happens
    here.

    Absent or null is legitimate — a task that has no `prediction` omits it — and
    becomes `{}`. A field that is *present with the wrong type* is a malformed
    response and is reported as one.

    Two failure modes have to be avoided here, and they pull in opposite
    directions. The `x or {}` idiom this replaces handled null and absent but not
    a truthy wrong type: a `"summary"` arriving as a string passed `or {}`
    untouched and then raised AttributeError on `.get`, in the report writer,
    which runs after main()'s try/except has closed — a traceback that reads as a
    client bug. Substituting `{}` for it instead fixes the traceback and creates
    something worse: a zero-valued report printed with `"ok": true`, so a bad
    response is indistinguishable from a real prediction of nothing. Raise a
    typed error that main() turns into the same diagnostic it gives any other
    malformed response, and it is neither.
    """
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ResponseShapeError(
            f"{field} should be an object, got {type(v).__name__}"
        )
    return v


def _as_objs(v: Any, field: str) -> list:
    """Same, for a field documented as an array of objects.

    A truthy non-list (a bare string) is iterable, so `or []` let it through and
    the row loop iterated its characters; non-object elements fail the same way.
    Neither is silently dropped — an array whose elements are the wrong type is a
    malformed response, and a report missing rows it should have had is exactly
    the silent wrong answer this is here to prevent.
    """
    if v is None:
        return []
    if not isinstance(v, list):
        raise ResponseShapeError(
            f"{field} should be an array, got {type(v).__name__}"
        )
    for i, x in enumerate(v):
        if not isinstance(x, dict):
            raise ResponseShapeError(
                f"{field}[{i}] should be an object, got {type(x).__name__}"
            )
    return v


def _summarize(task: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the most useful headline numbers per task from `data`."""
    data = _as_obj(body.get("data"), "data")
    summary = _as_obj(data.get("summary"), "data.summary")
    out: Dict[str, Any] = {"task": task, "model": data.get("model")}
    if task == "promoter":
        out["promoter_windows"] = summary.get("promoter_windows")
        out["total_windows"] = summary.get("total_windows")
        out["regions"] = _as_objs(data.get("regions"), "data.regions")
    elif task == "splice":
        out["sites_found"] = summary.get("total_sites", summary.get("sites_found"))
        out["donor_sites"] = summary.get("donor_sites")
        out["acceptor_sites"] = summary.get("acceptor_sites")
        out["sites"] = _as_objs(data.get("sites"), "data.sites")
    elif task == "enhancer":
        out["windows_processed"] = summary.get("total_windows", summary.get("windows_processed"))
        out["dev_score_max"] = summary.get("dev_score_max")
        out["hk_score_max"] = summary.get("hk_score_max")
    elif task == "chromatin":
        out["windows_processed"] = summary.get("total_windows", summary.get("windows_processed"))
        out["total_annotations"] = summary.get("total_annotations")
    elif task == "expression":
        pred = _as_obj(data.get("prediction"), "data.prediction")
        out["log_tpm"] = pred.get("expression_log_tpm")
        out["tpm"] = pred.get("expression_tpm")
        # Windowing provenance: an in-range but *wrong* tss_index scores the
        # wrong 9,198 bp window and still returns 200, so surface what was
        # actually scored rather than trusting the request.
        counts = _as_obj(
            _as_obj(body.get("meta"), "meta").get("task_specific_counts"),
            "meta.task_specific_counts",
        )
        out["tss_index"] = counts.get("tss_index")
        out["scored_window"] = counts.get("scored_window")
    elif task == "annotation":
        out["transcripts_found"] = summary.get("total_transcripts", summary.get("transcripts_found"))
        out["transcripts"] = _as_objs(data.get("transcripts"), "data.transcripts")
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
        regions = _as_objs(summary.get("regions"), "data.regions")
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
        sites = _as_objs(summary.get("sites"), "data.sites")[:20]
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
        tx = _as_objs(summary.get("transcripts"), "data.transcripts")[:20]
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
    tss_index: Optional[int] = None,
) -> str:
    """Build the exact re-runnable invocation for reproducibility/command.sh.

    Emits --model, --description and --tss-index only when they were supplied,
    so a replay reproduces the original call: expression requires --description
    (no default) and --tss-index whenever the sequence is not exactly 9,198 bp,
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
    if tss_index is not None:
        parts.append(f"--tss-index {tss_index}")
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
    tss_index: Optional[int] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps({"summary": summary, "full_response": body}, indent=2)
    )

    meta = _as_obj(body.get("meta"), "meta")
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
    cmd = _repro_command(task, input_path, output_dir, model, description, tss_index) + "\n"
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
    try:
        sequence_name, sequence = read_fasta(input_path)
    except FastaError as e:
        print(f"[gi-{task}] invalid input — {e}", file=sys.stderr)
        return 1
    if not sequence:
        print(f"Error: parsed an empty sequence from {input_path}", file=sys.stderr)
        return 1

    length_err = spec.validate(len(sequence))
    if length_err:
        print(f"[gi-{task}] invalid input — {length_err}", file=sys.stderr)
        if task == "expression":
            print(
                "  The expression model scores exactly one 9,198 bp TSS-centred window "
                "(TSS ± 4,599), so 9,198 bp is a hard floor. Send a pre-cut window, or a "
                "longer locus plus --tss-index. See references/tasks.md#expression.",
                file=sys.stderr,
            )
        elif len(sequence) < spec.min_bp:
            print(
                f"  {task} needs at least {spec.min_bp:,} bp. This floor is published as "
                f"minLength on the endpoint's request schema; the server rejects a shorter "
                f"sequence with 422 validation_failed. See references/tasks.md.",
                file=sys.stderr,
            )
        return 1

    tss_index = args.tss_index
    if task == "expression":
        if tss_index is None:
            # Default path: exact window only. See the EXPRESSION_WINDOW_BP note
            # above for why this is stricter than the API's own floor.
            if len(sequence) != EXPRESSION_WINDOW_BP:
                print(
                    f"[gi-expression] --tss-index is required unless the sequence is "
                    f"exactly {EXPRESSION_WINDOW_BP:,} bp (got {len(sequence):,} bp). "
                    "It is the 0-based TSS offset into the sequence. "
                    "See references/tasks.md#expression.",
                    file=sys.stderr,
                )
                return 1
        else:
            lo, hi = EXPRESSION_TSS_RADIUS, len(sequence) - EXPRESSION_TSS_RADIUS
            if not (lo <= tss_index <= hi):
                print(
                    f"[gi-expression] --tss-index {tss_index:,} outside the allowed range "
                    f"[{lo:,}, {hi:,}] for a {len(sequence):,} bp sequence — the model needs "
                    f"a full ±{EXPRESSION_TSS_RADIUS:,} bp window around the TSS; submit more "
                    "flanking sequence.",
                    file=sys.stderr,
                )
                return 1
    elif tss_index is not None:
        print(f"[gi-{task}] --tss-index applies to expression only; ignoring it.", file=sys.stderr)
        tss_index = None

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
    # `options` is a closed (additionalProperties: false) object per task, and
    # only ExpressionOptions declares `description`. Forwarding it on any other
    # task is a hard 422 validation_failed (extra_forbidden), not a no-op — so
    # drop it locally rather than letting the server reject the call.
    options: Dict[str, Any] = {}
    if args.description is not None:
        if task == "expression":
            options["description"] = args.description
        else:
            print(
                f"[gi-{task}] --description applies to expression only; ignoring it "
                f"({task} rejects unknown options keys with 422).",
                file=sys.stderr,
            )

    print(
        f"[gi-{task}] sequence_name={sequence_name} length={len(sequence):,} bp "
        f"model={args.model or 'default'} mode={'async' if spec.async_default else 'sync'}",
        file=sys.stderr,
    )
    started = time.monotonic()
    try:
        if spec.async_default:
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
                model=args.model, options=options or None, tss_index=tss_index,
            )
    except GIError as e:
        print(f"[gi-{task}] API error: {e}", file=sys.stderr)
        return 2
    except requests.RequestException as e:
        # Connection refused, DNS failure, TLS error, read timeout — routine
        # for a hosted service and not the caller's bug. gi_ensembl already
        # maps these to a diagnostic; do the same here rather than exiting
        # with a traceback that reads like a client defect.
        print(f"[gi-{task}] network error reaching the API: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    except TimeoutError as e:
        # Raised by wait_for_job when a job outlives its poll deadline.
        print(f"[gi-{task}] timed out waiting for the job: {e}", file=sys.stderr)
        return 2
    except KeyError as e:
        # A 2xx whose body is missing a field we index (e.g. data.job_id on an
        # async submit). Malformed upstream response, not a usage error.
        print(f"[gi-{task}] unexpected API response shape: missing {e}", file=sys.stderr)
        return 2

    elapsed_ms = (time.monotonic() - started) * 1000.0
    # The report writer runs outside the block above, so its own view of a
    # malformed response needs its own handler. Without one a wrong-typed nested
    # field either raised a traceback or — once the helpers coerced it — printed
    # a zero-valued report with ok=true. Both are worse than exiting 2 with the
    # field named.
    try:
        summary = _summarize(task, body)
        meta = _as_obj(body.get("meta"), "meta")
        _write_report(
            task, summary, body, output_dir, input_path, sequence_name, len(sequence),
            elapsed_ms, model=args.model, description=args.description, tss_index=tss_index,
        )
    except ResponseShapeError as e:
        print(f"[gi-{task}] unexpected API response shape: {e}", file=sys.stderr)
        return 2
    print(f"[gi-{task}] OK — wrote {output_dir}/report.md ({elapsed_ms:.0f} ms wall)", file=sys.stderr)

    # stdout = a compact machine-readable summary so the agent gets the answer
    # inline without reading a file. The bulky per-item arrays (regions / sites /
    # transcripts) stay in result.json — only headline scalars go here.
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
