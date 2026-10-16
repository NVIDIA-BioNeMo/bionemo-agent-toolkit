# Offline target preparation contract
This is a synthetic software fixture. No API calls, inference, or biological validation.
Use model 1 and the chain in request.json. Keep author numbers and insertion codes distinct;
choose one CA per residue using the supplied alternate-location policy and preserve file order.
Write target.pdb (only the chosen chain/model, original author numbering) and preparation.json:
`chain`, `sequence`, `author_to_sequence` (string author ID to 1-based integer), and `requests`
(keyed by request ID). Each request has `status`: `ready` or `blocked`. A ready request has
`hotspot_res` (chain+author strings) and `sequence_indices`. A missing hotspot blocks that
request and records `missing_author_residues`; do not choose a nearby residue or emit its
partial handoff. Other requests can succeed independently. Add `simulated: true` and
`live_inference: false`. Do not renumber the PDB or combine alternate locations/models.
