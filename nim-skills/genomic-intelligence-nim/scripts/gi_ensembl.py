"""Ensembl REST helpers: resolve a gene symbol or genomic region to reference sequence.

Ported from the Genomic Intelligence MCP server (`gi_mcp/_ensembl.py`) and
de-coupled from it — only dependency is ``requests``. Same public REST API the
Web UI's GeneSearch uses (rest.ensembl.org); no API key required.

Three flows used by the skill's acquisition CLI (``gi_fetch.py``):
  - fetch_by_symbol(symbol)               → full gene-body sequence
  - fetch_region_by_coords("chr:start-end") → region sequence
  - fetch_gene_window_for_expression(symbol) → exactly 9,198 bp centred on the TSS

Base URL: ``GI_ENSEMBL_URL`` env, default ``https://rest.ensembl.org``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

# Expression model window — mirrors gpu_service expression exact_bp (2 * 4599).
EXPRESSION_SEQUENCE_LENGTH = 9_198

DEFAULT_ENSEMBL_URL = "https://rest.ensembl.org"
_USER_AGENT = "BioNeMo-GI-Skill/0.1.0"


def ensembl_base_url() -> str:
    return os.environ.get("GI_ENSEMBL_URL", DEFAULT_ENSEMBL_URL).rstrip("/")


class EnsemblError(RuntimeError):
    pass


@dataclass
class GeneLocus:
    ensembl_id: str
    seq_region: str  # e.g. "17"
    start: int
    end: int
    strand: int  # +1 or -1
    species: str
    display_name: str
    # Canonical-transcript boundaries (when resolved via expand=1). Gene-level
    # start/end can sit far from the real TSS — HBB's gene end is 2,324 bp from
    # its canonical TSS, ACTB's is 33,301 bp — so expression windowing must use
    # the canonical transcript, not the gene body.
    canonical_start: Optional[int] = None
    canonical_end: Optional[int] = None

    @property
    def tss(self) -> int:
        """Transcription start site: transcript start on +strand, end on -strand.

        Prefers the canonical transcript boundary when available; falls back to
        the gene body otherwise.
        """
        start = self.canonical_start if self.canonical_start is not None else self.start
        end = self.canonical_end if self.canonical_end is not None else self.end
        return start if self.strand >= 0 else end


def _get(path: str, *, headers: Optional[dict] = None, params: Optional[dict] = None,
         timeout: float = 30.0) -> requests.Response:
    """GET against the Ensembl REST base, mapping transport failures to EnsemblError."""
    base_headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        base_headers.update(headers)
    url = f"{ensembl_base_url()}{path}"
    try:
        return requests.get(url, headers=base_headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise EnsemblError(
            f"could not reach Ensembl at {ensembl_base_url()} ({type(exc).__name__})"
        ) from exc


def lookup_symbol(symbol: str, species: str = "human", expand: bool = False) -> GeneLocus:
    """Resolve a gene symbol to its genomic locus.

    With ``expand=True`` the gene's transcripts are pulled too, and the
    canonical transcript's boundaries are recorded on the locus (used for
    TSS-accurate expression windowing).
    """
    r = _get(
        f"/lookup/symbol/{species}/{symbol}",
        params={"expand": 1 if expand else 0},
    )
    if r.status_code == 404:
        raise EnsemblError(f"gene symbol {symbol!r} not found in {species}")
    if not r.ok:
        hint = ""
        if r.status_code == 400:
            # A 400 here is almost always an unrecognised species token: Ensembl
            # wants the production name (lowercase, underscored), so 'drosophila'
            # / 'Drosophila melanogaster' fail where 'drosophila_melanogaster'
            # works. Point the caller at the canonical form.
            hint = (
                " — check the species token: Ensembl expects a production name "
                "(lowercase, underscored), e.g. 'drosophila_melanogaster', "
                "'mus_musculus', not 'drosophila' or 'Drosophila melanogaster'"
            )
        raise EnsemblError(
            f"Ensembl lookup failed ({r.status_code}) for {symbol!r} "
            f"in species {species!r}{hint}"
        )
    d = r.json()
    canonical_start: Optional[int] = None
    canonical_end: Optional[int] = None
    if expand:
        transcripts = d.get("Transcript") or []
        canonical = next((t for t in transcripts if t.get("is_canonical") == 1), None)
        if canonical is not None:
            canonical_start = int(canonical["start"])
            canonical_end = int(canonical["end"])
    return GeneLocus(
        ensembl_id=d["id"],
        seq_region=str(d["seq_region_name"]),
        start=int(d["start"]),
        end=int(d["end"]),
        strand=int(d.get("strand", 1)),
        species=species,
        display_name=d.get("display_name", symbol),
        canonical_start=canonical_start,
        canonical_end=canonical_end,
    )


def fetch_region(seq_region: str, start: int, end: int, species: str = "human",
                 strand: int = 1) -> str:
    """Fetch raw nucleotide sequence for a 1-based inclusive region."""
    region = f"{seq_region}:{start}..{end}:{strand}"
    r = _get(f"/sequence/region/{species}/{region}", headers={"Accept": "text/x-fasta"})
    if not r.ok:
        raise EnsemblError(f"Ensembl sequence fetch failed ({r.status_code}) for {region}")
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith(">")]
    return "".join(lines).upper()


# Coordinate string → (chrom, start, end). Lenient like the Web UI's GeneSearch
# (commas / en–em dashes / `..` / optional `chr`).
_REGION_RE = re.compile(r"^(?:chr)?([A-Za-z0-9]+):(\d+)(?:-(\d+))?$", re.IGNORECASE)


def parse_region(text: str) -> Tuple[str, int, int]:
    """Parse 'chr8:127,680,000-127,800,000' → ('8', 127680000, 127800000).

    Accepts commas, en/em-dashes and ``..`` (normalised to ``-``), an optional
    ``chr`` prefix, and spaces around separators. A bare position (no end)
    defaults to a 1,000 bp window. Raises EnsemblError if unparseable.
    """
    normalized = (
        text.replace(",", "")
        .replace("–", "-")  # en dash
        .replace("—", "-")  # em dash
        .replace("..", "-")
    )
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s*:\s*", ":", normalized).strip()
    m = _REGION_RE.match(normalized)
    if not m:
        raise EnsemblError(
            f"could not parse genomic region {text!r}; expected e.g. "
            "'chr8:127,680,000-127,800,000'"
        )
    chrom = m.group(1)
    start = int(m.group(2))
    end = int(m.group(3)) if m.group(3) else start + 1000
    if start < 1:
        raise EnsemblError(f"region start must be >= 1 (got {start})")
    if end < start:
        raise EnsemblError(f"region end ({end:,}) is before start ({start:,})")
    return chrom, start, end


def fetch_region_by_coords(region: str, species: str = "human", strand: int = 1,
                           flank_bp: int = 0) -> Tuple[str, dict]:
    """Coordinate string → reference sequence + meta. Plus strand by default."""
    chrom, raw_start, raw_end = parse_region(region)
    start = max(1, raw_start - flank_bp)
    end = raw_end + flank_bp
    seq = fetch_region(chrom, start, end, species, strand=strand)
    meta = {
        "region": f"{chrom}:{start}-{end}",
        "strand": strand,
        "species": species,
        "length": len(seq),
    }
    return seq, meta


def fetch_by_symbol(symbol: str, species: str = "human", flank_bp: int = 0) -> Tuple[str, dict]:
    """Symbol → full gene-body sequence (optionally flanked). Returns (seq, meta)."""
    locus = lookup_symbol(symbol, species)
    start = max(1, locus.start - flank_bp)
    end = locus.end + flank_bp
    seq = fetch_region(locus.seq_region, start, end, species, strand=locus.strand)
    meta = {
        "ensembl_id": locus.ensembl_id,
        "region": f"{locus.seq_region}:{start}-{end}",
        "strand": locus.strand,
        "species": species,
        "gene": locus.display_name,
    }
    return seq, meta


def fetch_gene_window_for_expression(symbol: str, species: str = "human") -> Tuple[str, dict]:
    """Symbol → exactly EXPRESSION_SEQUENCE_LENGTH bp centred on the TSS.

    The expression model demands a precise window. We take the TSS from the
    gene's *canonical transcript* (expand=1) — gene-body boundaries can sit
    thousands of bp from the real TSS (HBB: 2,324 bp; ACTB: 33,301 bp), which
    would mis-centre the window and tank the prediction — and grab half the
    window on each side (the +1 keeps the total at exactly 9,198 bp).
    """
    locus = lookup_symbol(symbol, species, expand=True)
    tss = locus.tss
    half = EXPRESSION_SEQUENCE_LENGTH // 2  # 4599
    start = tss - half
    end = tss + half - 1  # inclusive → (tss+4598) - (tss-4599) + 1 = 9198
    if start < 1:
        raise EnsemblError(
            f"{symbol} TSS too close to chromosome start to extract a "
            f"{EXPRESSION_SEQUENCE_LENGTH} bp window"
        )
    seq = fetch_region(locus.seq_region, start, end, species, strand=locus.strand)
    if len(seq) != EXPRESSION_SEQUENCE_LENGTH:
        raise EnsemblError(
            f"expected {EXPRESSION_SEQUENCE_LENGTH} bp, Ensembl returned {len(seq)}"
        )
    meta = {
        "ensembl_id": locus.ensembl_id,
        "tss": tss,
        "tss_source": "canonical-transcript" if locus.canonical_start is not None else "gene-body",
        "region": f"{locus.seq_region}:{start}-{end}",
        "strand": locus.strand,
        "species": species,
        "gene": locus.display_name,
        "window": "TSS-centred",
    }
    return seq, meta
