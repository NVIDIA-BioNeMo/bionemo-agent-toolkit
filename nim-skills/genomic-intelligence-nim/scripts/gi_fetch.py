#!/usr/bin/env python3
"""Resolve a gene or genomic region to a FASTA file, via Ensembl.

This is the *acquisition* half of the skill. The agent calls it when the
user names a gene or locus instead of supplying a FASTA — it fetches reference
sequence from Ensembl (public, no API key) and writes a single-record FASTA that
``gi_predict.py --input`` then consumes.

Modes (mutually exclusive):
    --gene SYMBOL              full gene-body sequence (e.g. TP53)
    --region chr17:7.6M-7.7M   sequence for a coordinate range
    --gene SYMBOL --for-expression
                              EXACTLY 9,198 bp centred on the canonical TSS —
                              the only window the expression model accepts

Examples:
    python scripts/gi_fetch.py --gene TP53 --out tp53.fa
    python scripts/gi_fetch.py --region chr17:7,661,779-7,687,546 --out region.fa
    python scripts/gi_fetch.py --gene HBB --for-expression --out hbb_tss.fa

On success the FASTA path is printed to stdout (so the agent can pipe it into
gi_predict.py); a one-line provenance summary goes to stderr.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from gi_ensembl import (  # noqa: E402
    EnsemblError,
    fetch_by_symbol,
    fetch_gene_window_for_expression,
    fetch_region_by_coords,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch reference sequence from Ensembl and write a FASTA."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--gene", type=str, help="Gene symbol, e.g. TP53.")
    src.add_argument("--region", type=str, help="Coordinate range, e.g. chr17:7,661,779-7,687,546.")
    p.add_argument(
        "--for-expression",
        action="store_true",
        help="With --gene: return exactly 9,198 bp centred on the canonical TSS "
        "(required by the expression task). Ignored with --region.",
    )
    p.add_argument(
        "--species",
        type=str,
        default="human",
        help="Ensembl production name (default: human; e.g. mus_musculus, drosophila_melanogaster).",
    )
    p.add_argument("--flank-bp", type=int, default=0, help="Extra bp on each side (gene/region only).")
    p.add_argument("--strand", type=int, default=1, choices=(1, -1), help="Strand for --region (default 1).")
    p.add_argument("--out", type=Path, required=True, help="Output FASTA path to write.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.region:
            if args.for_expression:
                print(
                    "[gi-fetch] --for-expression needs --gene (TSS centring requires a "
                    "gene's canonical transcript, not a raw region).",
                    file=sys.stderr,
                )
                return 1
            seq, meta = fetch_region_by_coords(
                args.region, species=args.species, strand=args.strand, flank_bp=args.flank_bp
            )
            header = f"{meta['region']}|{args.species}|strand:{meta['strand']}"
        elif args.for_expression:
            seq, meta = fetch_gene_window_for_expression(args.gene, species=args.species)
            header = (
                f"{meta['gene']}|{meta['ensembl_id']}|{meta['region']}|{args.species}|"
                f"strand:{meta['strand']}|TSS:{meta['tss']}|{meta['tss_source']}"
            )
        else:
            seq, meta = fetch_by_symbol(args.gene, species=args.species, flank_bp=args.flank_bp)
            header = (
                f"{meta['gene']}|{meta['ensembl_id']}|{meta['region']}|{args.species}|"
                f"strand:{meta['strand']}"
            )
    except EnsemblError as e:
        print(f"[gi-fetch] {e}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    wrapped = "\n".join(seq[i : i + 70] for i in range(0, len(seq), 70))
    args.out.write_text(f">{header}\n{wrapped}\n")

    print(
        f"[gi-fetch] wrote {len(seq):,} bp → {args.out}  ({header})",
        file=sys.stderr,
    )
    # stdout = just the path, so the agent can chain: FASTA=$(gi_fetch ...)
    print(str(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
