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

    @pytest.mark.parametrize("payload", [{}, [], {"meta": {}}, "text", None])
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
