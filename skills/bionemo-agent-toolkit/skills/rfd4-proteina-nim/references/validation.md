# Validate and interpret a run

## Completion and artifacts

Read `transport.json` first. `prepared_not_submitted`, `pending`, and `failed`
are not completed inference. `source=saved_response` means extraction only.
For a live run, retain the actual endpoint, timestamps, request/response hashes,
HTTP status, and returned request IDs. Do not replace error bodies with example
output or report a previous directory's artifacts as a new run.

`summary.json` must have no `validation_errors`. The client checks nonempty
designs, task consistency, plain-sampling count, origins, model/runtime/schedule
objects, expected output presence, a basic mmCIF header, sequence text, and
`diagnostics.all_coordinates_finite is true`. It does not parse the complete
CIF or independently prove physical validity. Failed output remains available
for diagnosis with `status=failed_validation`.

Verify each saved file exists and opens with a mmCIF-aware parser. Check that
`_atom_site.Cartn_x/y/z` values are finite and atom/residue counts are plausible.
Preserve annotated mmCIF for motif mapping; conversion to PDB can discard
provenance, molecular context, and condition annotations.

## Biological conditions

- Confirm target/framework coordinates and fixed identities were retained.
  Check the conditions actually present in the request, not just its task name.
- Designed chains can be renumbered. Follow annotations such as
  `annotation_src-component_1_atom`, `mapped_to_coordinate_conditioned_region`,
  and `is_unindexed_insertion` to find held motifs and insertions.
- For binders, identify binder/target chains in the structure before reading
  contact metrics or extracting sequences. `chain_of_interest` qualifies
  `*_coi` results; an incompletely held target can influence them.
- For antibodies, verify framework retention and loop changes. A missing
  sidechain cannot be held at finite coordinates merely because the residue
  exists; the upstream HER2 example leaves an unresolved sidechain free while
  preserving its sequence.
- For partial diffusion and inverse folding, inspect reported
  `input_ca_rmsd_angstrom` and `sequence_recovery` when available. Their null
  values are not zero RMSD or zero recovery. The input backbone's quality
  limits what inverse folding can produce.

## Metrics and quality

Report returned geometry and condition-adherence metrics without inventing
universal thresholds. In particular inspect clashes, unreasonable bond-length
fractions, motif RMSD, sequence violations, and hotspot/contact adherence when
those families apply. An all-finite structure can still have serious clashes,
poor geometry, unsuitable sequence composition, or unmet design conditions.

An empty metrics dictionary despite requested tags deserves a warning, even
when the service supplied none. A dictionary of null values is also not a
successful measurement. Upstream metrics can fail independently of generation;
some tags have historically emptied the full dictionary, while others returned
nulls. Inspect actual responses rather than assuming all historical failures
remain present in the deployed version.

`aggregated_metrics[].n` counts contributing values. Missing/indeterminate
values are excluded; when all values are unavailable, the aggregate row can
be absent entirely. A `.pass` mean with `n=2` from ten designs describes those
two, not a ten-design success rate. Include both denominator and total count.

Compare search rewards only within a compatible reward configuration. Keep
`search_final` and `search_intermediate` separate. Search selection against a
metric is not independent validation of that metric or of experimental binding.

Independent refolding, interface analysis, and experiments are separate evidence.
Do not infer pLDDT from a search reward, generic score, or the B-factor column.
No stock refolding oracle means no built-in refolding result.

## Reproduce and report

Report request identity, actual design count, structure/FASTA/summary paths,
returned schedule and backend, warnings, failed replicates, relevant metric
values and denominators, and whether independent validation was actually run.
Keep full sequences in FASTA; label any displayed truncation as a preview.

For reruns preserve the input bytes, weights, runtime, batch size, and seed.
Search requires replaying the whole search. Save an edited request as a new
artifact rather than silently changing the original.

## Observed BioIR metadata caveat

Sample 09 requested `partial.trajectory_fraction_steps=0.4` with the 60-step
named schedule. Its response reported `kind=partial`, `num_steps=60`,
`trunk_passes=185`, and `start_times=null`. The nominal fraction corresponds
to 24 steps under the request contract. The inspected
`nim/api/pipeline/bioir.py` response builder reports the full sampling bands
and hardcodes null start times. Thus these fields do not establish actual
partial-trajectory work. Report both request and returned metadata, identify
the discrepancy, and avoid claiming either that all 60 steps executed or
that partial conditioning was ignored. Independent mmCIF parsing and
finite-coordinate checks passed, which is a separate observation.
