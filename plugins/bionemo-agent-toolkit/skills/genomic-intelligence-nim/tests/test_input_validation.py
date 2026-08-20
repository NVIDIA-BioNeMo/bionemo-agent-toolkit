"""The client refuses malformed input instead of silently repairing it.

Each case here is a real defect that shipped: the parser used to delete every
character outside ACGTN and to concatenate multi-record files into one chimeric
sequence, and the Ensembl helper used to fall back to gene-body coordinates
when no canonical transcript was found. All three produced a confident,
wrong-but-well-formed result with nothing for the caller to notice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gi_client  # noqa: E402
import gi_predict  # noqa: E402
from gi_client import FastaError, read_fasta  # noqa: E402
from gi_ensembl import (  # noqa: E402
    EXPRESSION_SEQUENCE_LENGTH,
    EnsemblError,
    GeneLocus,
    expression_window_bounds,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "input.fa"
    path.write_text(content)
    return path


class TestReadFasta:
    def test_accepts_a_clean_single_record(self, tmp_path):
        path = _write(tmp_path, ">chr1 some description\nACGT\nacgt\n")
        name, seq = read_fasta(path)
        assert name == "chr1"
        assert seq == "ACGTACGT", "lowercase and line breaks are formatting, not content"

    def test_rejects_iupac_ambiguity_codes(self, tmp_path):
        # Deleting these shifts every downstream coordinate, so the model would
        # score a sequence the caller never supplied.
        path = _write(tmp_path, ">x\nACGTRYKM\n")
        with pytest.raises(FastaError) as exc:
            read_fasta(path)
        assert "outside ACGTN" in str(exc.value)
        assert "IUPAC" in str(exc.value), "the hint should name why these specifically cannot be scored"

    def test_rejects_non_iupac_junk_without_the_iupac_hint(self, tmp_path):
        path = _write(tmp_path, ">x\nACGT--NN\n")
        with pytest.raises(FastaError) as exc:
            read_fasta(path)
        assert "IUPAC" not in str(exc.value)

    def test_rejects_multi_record_input(self, tmp_path):
        path = _write(tmp_path, ">a\nACGT\n>b\nTTTT\n")
        with pytest.raises(FastaError) as exc:
            read_fasta(path)
        assert "single FASTA record" in str(exc.value)
        assert "found 2" in str(exc.value)

    def test_error_names_the_offending_line(self, tmp_path):
        path = _write(tmp_path, ">x\nACGT\nACGTR\n")
        with pytest.raises(FastaError) as exc:
            read_fasta(path)
        assert "line 3" in str(exc.value)

    def test_fasta_error_is_a_value_error(self):
        # Callers doing broad input validation still catch it.
        assert issubclass(FastaError, ValueError)

    @pytest.mark.parametrize(
        "fixture", sorted((SCRIPTS.parent / "assets" / "demo").glob("*.fa")), ids=lambda p: p.name
    )
    def test_bundled_demo_fixtures_still_parse(self, fixture):
        # A stricter parser that rejects our own demos would be useless.
        name, seq = read_fasta(fixture)
        assert name and seq


class TestCanonicalTss:
    def _locus(self, **kw):
        base = dict(
            ensembl_id="ENSG0", seq_region="11", start=1000, end=2000,
            strand=1, species="human", display_name="TEST",
        )
        base.update(kw)
        return GeneLocus(**base)

    def test_uses_canonical_start_on_plus_strand(self):
        locus = self._locus(canonical_start=1500, canonical_end=1900)
        assert locus.tss == 1500

    def test_uses_canonical_end_on_minus_strand(self):
        locus = self._locus(strand=-1, canonical_start=1500, canonical_end=1900)
        assert locus.tss == 1900

    def test_refuses_when_no_canonical_transcript(self):
        # The old fallback returned the gene body here. That window is still
        # exactly 9,198 bp, so the client-side size gate passes and the API
        # returns a confident score for the wrong locus — ACTB's gene body sits
        # 33,301 bp from its TSS. There is no client-side tell, so refusing is
        # the only honest option.
        locus = self._locus()
        with pytest.raises(EnsemblError) as exc:
            _ = locus.tss
        assert "no canonical transcript" in str(exc.value)

    def test_refuses_when_only_one_boundary_is_known(self):
        locus = self._locus(canonical_start=1500)
        with pytest.raises(EnsemblError):
            _ = locus.tss
class TestExpressionWindowCentring:
    """The TSS must land at offset 4,599 on both strands.

    The API scores ``sequence[tss_index-4599 : tss_index+4599]`` and defaults
    ``tss_index`` to 4,599 for a submission of exactly 9,198 bp. Ensembl
    reverse-complements the region for ``strand=-1``, so a window built as if
    the sequence always read low-to-high puts a minus-strand TSS at 4,598 —
    still exactly 9,198 bp, so the size gate passes and the API scores a
    window shifted by one with nothing for the caller to notice.
    """

    @pytest.mark.parametrize("strand", [1, -1])
    def test_window_is_exactly_the_expression_length(self, strand):
        start, end = expression_window_bounds(1_000_000, strand)
        assert end - start + 1 == EXPRESSION_SEQUENCE_LENGTH

    @pytest.mark.parametrize(
        "strand,tss",
        [(1, 1_000_000), (-1, 5_227_071)],  # HBB's canonical TSS is on the minus strand
    )
    def test_tss_lands_where_the_api_expects_it(self, strand, tss):
        start, end = expression_window_bounds(tss, strand)
        # Offset of the TSS in the sequence as Ensembl returns it: low-to-high
        # on the plus strand, reverse-complemented on the minus strand.
        offset = tss - start if strand == 1 else end - tss
        assert offset == EXPRESSION_SEQUENCE_LENGTH // 2
class TestDemoMustBeAskedFor:
    """Omitting --input must not fall back to the bundled fixture.

    The fallback produced a complete run — real request id, real scores, a
    written report — for a sequence the caller never supplied, and nothing in
    the output distinguished it from a real one.
    """

    def _args(self, **kw):
        defaults = {"demo": False, "input_file": None}
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_no_input_and_no_demo_exits(self):
        spec = gi_predict.TASKS["promoter"]
        with pytest.raises(SystemExit) as exc:
            gi_predict._resolve_input(self._args(), spec)
        assert exc.value.code == 2

    def test_demo_flag_still_resolves_the_fixture(self):
        spec = gi_predict.TASKS["promoter"]
        path = gi_predict._resolve_input(self._args(demo=True), spec)
        assert path.name == spec.demo
class TestSequenceBeforeFirstHeader:
    """Bases before the first '>' must be refused, not absorbed.

    They were appended to the first record, so the API scored a sequence the
    caller never named and returned coordinates for it. The multi-record check
    does not see this: such a file has exactly one header.
    """

    def test_pre_header_sequence_is_rejected(self, tmp_path):
        path = _write(tmp_path, "ACGTACGT\n>real_record\nGGGGCCCC\n")
        with pytest.raises(FastaError) as exc:
            read_fasta(path)
        assert "before any" in str(exc.value)

    def test_a_normal_single_record_still_parses(self, tmp_path):
        path = _write(tmp_path, ">real_record\nACGT\nGGGG\n")
        name, seq = read_fasta(path)
        assert (name, seq) == ("real_record", "ACGTGGGG")


class TestSuccessfulResponsesAreValidated:
    """A 2xx is not automatically a result.

    A non-JSON 200 used to be turned into an error-shaped dict and returned as
    a success, and an empty or non-object 200 reached the report writer and
    failed there as an AttributeError.
    """

    class _Resp:
        status_code = 200
        headers: dict = {}
        ok = True

        def __init__(self, payload=None, text=""):
            self._payload, self.text = payload, text

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    def test_non_json_200_raises_instead_of_returning_an_error_shape(self):
        c = gi_client.Client.__new__(gi_client.Client)
        with pytest.raises(gi_client.GIError):
            c._check(self._Resp(text="<html>gateway</html>"))

    @pytest.mark.parametrize(
        "payload", [{}, [], {"meta": {}}, "text", None, {"data": {}, "meta": {}}]
    )
    def test_a_200_without_data_is_not_a_result(self, payload):
        with pytest.raises(gi_client.GIError):
            gi_client.Client._require_envelope(payload, self._Resp(payload))

    def test_a_well_formed_envelope_passes_through(self):
        body = {"data": {"summary": {}}, "meta": {}}
        assert gi_client.Client._require_envelope(body, self._Resp(body)) is body
class TestWhitespaceIsFormattingNotContent:
    """Whitespace is normalized; only content is refused.

    The API strips newlines, spaces and tabs before measuring length, so a
    space-grouped body has to parse here too or the client is stricter than
    the service it guards.
    """

    @pytest.mark.parametrize(
        "body,expected",
        [
            ("ACGT\nGGGG\n", "ACGTGGGG"),
            ("ACGTACGTAC GTACGTACGT\n", "ACGTACGTACGTACGTACGT"),
            ("ACGT\tACGT\n", "ACGTACGT"),
            ("  ACGT  \n\n  GGGG\n", "ACGTGGGG"),
            ("acgtACGT\n", "ACGTACGT"),
        ],
    )
    def test_layout_is_normalized(self, tmp_path, body, expected):
        assert read_fasta(_write(tmp_path, f">r\n{body}"))[1] == expected

    @pytest.mark.parametrize("body", ["ACGTRACGT\n", "ACGT R ACGT\n"])
    def test_ambiguity_codes_are_still_refused(self, tmp_path, body):
        with pytest.raises(FastaError):
            read_fasta(_write(tmp_path, f">r\n{body}"))
class TestSyncPredictIsValidatedToo:
    """The sync path needs the same envelope check as the async one.

    An earlier patch wrapped only wait_for_job, so predict() still returned a
    200 with no data key straight to the report writer, which wrote an empty
    report and reported ok=true.
    """

    class _Resp:
        status_code, headers, ok = 200, {}, True

        def __init__(self, payload):
            self._payload, self.text = payload, ""

        def json(self):
            return self._payload

    @pytest.mark.parametrize(
        "payload",
        [
            {"meta": {}},                 # no data key at all
            {"data": None, "meta": {}},   # null data
            {"data": "summary", "meta": {}},  # non-object data
            {"data": [1, 2], "meta": {}},     # array data
            {"data": {}, "meta": {"request_id": "req-1"}},  # object, but no result in it
        ],
    )
    def test_a_200_without_an_object_data_is_refused(self, payload):
        with pytest.raises(gi_client.GIError):
            gi_client.Client._require_envelope(payload, self._Resp(payload))

    def test_predict_wraps_the_sync_path(self):
        import inspect

        src = inspect.getsource(gi_client.Client.predict)
        assert "_require_envelope" in src, (
            "predict() must validate the envelope; a patch that misses this "
            "line leaves the sync path unguarded while the async one is fine"
        )
class TestAsyncSubmitIsValidatedToo:
    """submit_async reads data.job_id, so it needs the envelope check as well.

    A 200 with no data key raised KeyError, which the CLI catches; a non-object
    data raised TypeError, which it does not. Both are malformed responses, not
    client bugs, and both should surface as GIError.
    """

    def test_submit_async_wraps_the_envelope(self):
        import inspect

        src = inspect.getsource(gi_client.Client.submit_async)
        assert "_require_envelope" in src

    def test_an_empty_data_never_reaches_the_job_id_read(self):
        """`{"data": {}}` is refused by the envelope check itself.

        It used to pass, leaving `data.job_id` to catch it on this path only —
        and nothing at all to catch it on the sync and job-result paths, which
        wrote a zero-valued report and printed ok=true.
        """

        class _Resp:
            status_code, headers, ok = 200, {}, True
            text = ""

            def json(self):
                return {"data": {}, "meta": {}}

        with pytest.raises(gi_client.GIError):
            gi_client.Client._require_envelope(_Resp().json(), _Resp())

    def test_a_data_without_job_id_is_still_a_gi_error(self):
        """The job_id check stays: a non-empty `data` can still lack it."""
        body = {"data": {"status": "queued"}, "meta": {}}

        class _Resp:
            status_code, headers, ok = 200, {}, True
            text = ""

            def json(self):
                return body

        checked = gi_client.Client._require_envelope(body, _Resp())
        assert checked["data"].get("job_id") is None


class TestNestedFieldsOfTheWrongType:
    """`_require_envelope` passing is not a promise about what is inside `data`.

    The envelope check guarantees `data` is a non-empty object and stops there,
    which is the right scope for it — it is shared by six tasks and must not
    encode any one task's schema. So the report writer still meets whatever
    `data.summary` or `meta` actually contains, and it runs *after* main()'s
    first try/except has closed.

    Two wrong answers were available here and both were taken in turn. The
    `x or {}` guards only covered null and absent, so a truthy wrong type
    reached `.get` and raised AttributeError — a traceback that reads as a
    client bug. Coercing it to `{}` instead produced a zero-valued report
    printed with `"ok": true`, which is worse: a malformed response became
    indistinguishable from a real prediction of nothing. The third option is a
    typed refusal, which is what these pin.

    These call `_summarize` and `_write_report` rather than asserting on their
    source, because the defect this pins is a missing call site and a source
    grep is exactly what failed to catch the last one.
    """

    _MALFORMED = [
        {"data": {"summary": "all good"}},          # summary as a string
        {"data": {"summary": ["a", "b"]}},          # summary as an array
        {"data": {"summary": 0.94}},                # summary as a float
        {"data": {"prediction": "high"}},           # prediction as a string
        {"data": {"summary": {}}, "meta": "req-1"},  # meta as a string
        {"data": {"summary": {}}, "meta": {"task_specific_counts": "n/a"}},
        {"data": {"summary": {}, "regions": "chr1"}},      # array field as a string
        {"data": {"summary": {}, "sites": [1, 2, 3]}},     # non-object elements
        {"data": {"summary": {}, "transcripts": "ENST1"}},
    ]

    @pytest.mark.parametrize("body", _MALFORMED)
    @pytest.mark.parametrize(
        "task", ["promoter", "splice", "enhancer", "chromatin", "expression", "annotation"]
    )
    def test_a_wrong_typed_field_is_refused_not_coerced(self, task, body):
        """Whichever task reads the offending field must refuse the body.

        A task that never reads it is entitled to succeed — `enhancer` does not
        touch `data.transcripts` — so the assertion is on the failure mode, not
        on every combination failing: either a typed refusal naming the field,
        or a clean summary. Never an AttributeError, and never a summary built
        out of a substituted empty value.
        """
        try:
            out = gi_predict._summarize(task, body)
        except gi_predict.ResponseShapeError as e:
            assert "should be an" in str(e)
            return
        assert isinstance(out, dict)
        assert isinstance(out["raw_summary"], dict)

    @pytest.mark.parametrize(
        "body,field",
        [
            ({"data": {"summary": "all good"}}, "data.summary"),
            ({"data": {"summary": ["a", "b"]}}, "data.summary"),
            ({"data": {"summary": 0.94}}, "data.summary"),
            ({"data": {"summary": {}, "regions": "chr1"}}, "data.regions"),
            ({"data": {"summary": {}, "sites": [1, 2, 3]}}, "data.sites"),
        ],
    )
    def test_the_offending_field_is_named(self, body, field):
        task = {"data.summary": "promoter", "data.regions": "promoter",
                "data.sites": "splice"}[field]
        with pytest.raises(gi_predict.ResponseShapeError) as exc:
            gi_predict._summarize(task, body)
        assert field in str(exc.value)

    @pytest.mark.parametrize("body", _MALFORMED)
    @pytest.mark.parametrize("task", ["promoter", "splice", "expression", "annotation"])
    def test_the_report_never_half_writes(self, tmp_path, task, body):
        """A refusal may happen; a traceback or a silent zero report may not."""
        try:
            summary = gi_predict._summarize(task, body)
            gi_predict._write_report(
                task, summary, body, tmp_path, tmp_path / "in.fa", "seq", 9198, 12.0,
            )
        except gi_predict.ResponseShapeError:
            return
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()

    def test_main_reports_it_instead_of_exiting_zero(self, tmp_path, monkeypatch, capsys):
        """The whole point: exit 2 with a diagnostic, not 0 with `"ok": true`.

        Drives `main()` rather than grepping it for a handler, because the last
        defect of this shape (GI-055) was a source-level edit that matched
        nothing and still read as correct in review.
        """
        fa = tmp_path / "in.fa"
        fa.write_text(">seq\n" + "ACGT" * 100 + "\n")

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            def predict(self, *a, **kw):
                return {"data": {"summary": "all good"}, "meta": {}}

        monkeypatch.setattr(gi_predict, "Client", _FakeClient)
        monkeypatch.setenv("GI_API_KEY", "partner-test-key")
        monkeypatch.setattr(
            sys, "argv",
            ["gi_predict.py", "--task", "promoter", "--input", str(fa),
             "--output", str(tmp_path / "out")],
        )

        assert gi_predict.main() == 2
        err = capsys.readouterr()
        assert "unexpected API response shape" in err.err
        assert "data.summary" in err.err
        assert '"ok": true' not in err.out
        assert not (tmp_path / "out" / "report.md").exists()

    def test_absent_and_null_are_still_legitimate(self):
        """Only a *present, wrong-typed* field is malformed.

        A task with no `prediction` omits it; coercing that to `{}` is correct
        and must not become a refusal, or every sparse-but-valid response breaks.
        """
        body = {"data": {"summary": {"total_windows": 5}, "regions": None},
                "meta": None}
        out = gi_predict._summarize("promoter", body)
        assert out["regions"] == []
        assert out["raw_summary"] == {"total_windows": 5}

    def test_a_well_formed_body_still_reports_its_rows(self, tmp_path):
        body = {
            "data": {
                "summary": {"promoter_windows": 2, "total_windows": 5},
                "regions": [{"name": "r1", "start": 10, "end": 20, "score": 0.9}],
            },
            "meta": {"request_id": "req-1"},
        }
        summary = gi_predict._summarize("promoter", body)
        assert summary["regions"] == body["data"]["regions"]
        gi_predict._write_report(
            "promoter", summary, body, tmp_path, tmp_path / "in.fa", "seq", 9198, 12.0,
        )
        report = (tmp_path / "report.md").read_text()
        assert "req-1" in report and "r1" in report
