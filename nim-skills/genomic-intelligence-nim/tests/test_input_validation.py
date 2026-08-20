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
