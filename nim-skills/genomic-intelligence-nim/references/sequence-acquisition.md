# Sequence Acquisition (Ensembl)

The skill can turn a **gene symbol** or a **genomic region** into reference
sequence, so users don't have to bring a FASTA. This is handled by
`scripts/gi_fetch.py` (CLI) and `scripts/gi_ensembl.py` (the Ensembl REST
helpers it calls). Acquisition is separate from prediction: `gi_fetch.py` writes
a FASTA, then `gi_predict.py --input` consumes it.

**No API key** — Ensembl REST (`rest.ensembl.org`) is public. Only the
*prediction* step needs `GI_API_KEY`.

## Modes

```bash
# Full gene body (any task except expression)
python scripts/gi_fetch.py --gene TP53 --out tp53.fa

# Coordinate range
python scripts/gi_fetch.py --region chr17:7,661,779-7,687,546 --out region.fa

# 9,198 bp TSS-centred window (expression; or send a wider locus + --tss-index)
python scripts/gi_fetch.py --gene HBB --for-expression --out hbb_tss.fa
```

`--gene` and `--region` are mutually exclusive. The resolved FASTA path is
printed on **stdout**; a provenance line (length, Ensembl ID, region, strand)
goes to **stderr**. Chain it:

```bash
FASTA=$(python scripts/gi_fetch.py --gene TP53 --out tp53.fa)
python scripts/gi_predict.py --task promoter --input "$FASTA" --output out/
```

## TSS-centring (why `--for-expression` exists)

The expression model always scores **exactly 9,198 bp centred on the
transcription start site (TSS)**. You may either hand it a pre-cut 9,198 bp
window (what `--for-expression` builds) or hand it up to 500,000 bp plus
`--tss-index` and let the server slice. Either way you must know where the TSS
is — the endpoint never discovers it, never pads, and never
reverse-complements. You cannot reliably build this from gene-body coordinates:
the gene's annotated start/end can sit far from the real TSS — HBB's gene end is
2,324 bp from its canonical TSS, ACTB's is 33,301 bp. Mis-centring tanks the
prediction.

`--for-expression` resolves the gene's **canonical transcript** (Ensembl
`expand=1`), takes the TSS from it (transcript start on the + strand, end on the
− strand), and grabs 4,599 bp upstream + 4,598 bp downstream on the gene's
strand = 9,198 bp. It validates the returned length exactly. Because TSS
centring needs a transcript, `--for-expression` works only with `--gene`, never
`--region`.

## Species & assembly

- **Default: human, GRCh38** (Ensembl's current human assembly).
- Non-human: pass `--species <production_name>` — the Ensembl production name,
  which is lowercase and underscored: `mus_musculus`, `drosophila_melanogaster`,
  `saccharomyces_cerevisiae`. `mouse`, `Drosophila`, or `Drosophila melanogaster`
  will fail with a 400; the error message says so.
- The **enhancer** default model (DeepSTARR) is *Drosophila* — match the species
  to the model. See [tasks.md](tasks.md).

## Strand & coordinates

- `--region` defaults to `--strand 1` (plus). Pass `--strand -1` only for a
  strand-sensitive task on a known minus-strand locus. Gene fetch uses the
  gene's own strand automatically.
- Region strings are lenient: commas, `chr` prefix, en/em dashes, and `..` are
  all accepted (e.g. `chr8:127,680,000..127,800,000`). A bare position with no
  end defaults to a 1,000 bp window.
- `--flank-bp N` adds N bp on each side of a gene body or region (not used with
  `--for-expression`).

## When to skip acquisition

Supply a FASTA directly to `gi_predict.py --input` when the sequence is **not**
reference genome — variant-bearing, edited, synthetic, or from a non-Ensembl
assembly. Acquisition only returns reference sequence for the requested
coordinates.

## Limits

Reference fetch is bounded by the task's own input cap (500,000 bp for every
task) and its floor (promoter 300, splice 100, enhancer 50, chromatin 200,
annotation 1,000, expression 9,198 bp). Fetch at least the model's
`context_window_bp` if you want the score to reflect real sequence rather than
padding — see `references/tasks.md`. Ensembl enforces its own per-request size
limits on `/sequence/region`; very large ranges may be rejected upstream —
fetch in pieces or narrow the region.
