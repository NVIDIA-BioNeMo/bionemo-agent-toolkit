# UniProt database helper

Adapted from google-deepmind/science-skills (Apache-2.0). See the adjacent
`../LICENSE` and `../VENDOR.md` for attribution and local modifications.
This is a vendored library for target resolution, not an independently activated
skill. Run it with Python 3; it uses only the standard library.

## Data terms and local notice

Before first use of UniProt data, notify the user of the
[UniProt license](https://www.uniprot.org/help/license) and
[API usage terms](https://www.uniprot.org/help/api_queries).
Record that notification and its timestamp in `LICENSE_NOTIFICATION.txt` in the
campaign output directory. This creates a persistent local notice; reuse an
existing notice for that campaign. The helper itself does not write this file.

## Usage

From the parent Complexa skill directory:

```bash
python3 vendor/science-skills/uniprot_database/scripts/uniprot_tools.py get P04637
python3 vendor/science-skills/uniprot_database/scripts/uniprot_tools.py search 'gene:TP53 AND reviewed:true' --limit 5
python3 vendor/science-skills/uniprot_database/scripts/uniprot_tools.py count 'taxonomy_id:9606 AND reviewed:true'
python3 vendor/science-skills/uniprot_database/scripts/uniprot_tools.py stream 'gene:TP53 AND reviewed:true' --format tsv --fields accession,gene_names --limit 100
```

`get` returns one entry with its functional features. `search` yields pages in
JSON, TSV, or FASTA. `stream` yields lines from the same bounded search pages,
with `--limit` counting entries rather than FASTA lines. It does not call the
bulk stream endpoint. `count` reports the total before retrieval. `map` maps an
explicit set of IDs, and `sparql` runs a query; include a narrow LIMIT in SPARQL.

## Resource bounds

- Search and stream default to 100 records; `--limit` accepts 1..10000.
- Pages contain at most 500 requested entries. Pagination stops at the record
  budget and rejects responses exceeding the page budget, including cycles.
- Responses and gzip-expanded pages are capped at 16 MiB, with a 120-second
  per-request timeout and at most one request per second per client.
- ID mapping accepts at most 10000 IDs and polls at most 150 times, waiting two
  seconds between pending results. Individual requests retain their timeout.
- Results go to stdout; progress goes to stderr. Oversized responses, invalid
  budgets, API failures, and exhausted polling stop the command with an error.

Narrow the query when a bound is reached. For a larger dataset, use a separately
budgeted bulk-data workflow rather than raising this helper's limits. Preserve
accessions, source metadata and feature numbering; never infer missing functional
annotations from the protein name.
