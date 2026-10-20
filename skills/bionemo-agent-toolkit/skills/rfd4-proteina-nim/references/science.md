# Scientific scope

RFD4-Proteina co-generates protein structure and sequence using a latent
flow-matching pipeline, with backbone and sequence-latent schedules. The NIM
handles input conditioning, sampling/search, decoding, mmCIF export, and
optional metrics. Its BioIR and OSS backends are deployment choices; a client
does not select a backend by adding an unsupported request field.

This differs from the public RFDiffusion backbone NIM. Do not require a
ProteinMPNN handoff merely because the request designs a backbone: RFD4
already returns sequences. Sequence redesign or independent refolding can
still be appropriate when explicitly part of the user's workflow.

Conditions compose. A task is a sampler preset, not a list of all scientific
problems the model can express. Protein binders use standard generation with
target coordinates/identities and a designable region; hotspots indicate the
desired interface. Motif scaffolding and enzyme design preserve indexed or
unindexed features respectively. Antibody and nanobody examples use framework
and target constraints, not a dedicated antibody sampler.

Schema acceptance proves only that a request is admissible. It does not show
that an antibody, VHH, binder, or enzyme is scientifically qualified. Evaluate
framework and motif preservation, conditioning adherence, geometry, sequence
composition, and the relevant interface. Keep antibody and VHH benchmarks
separate rather than generalizing from one demonstration.

The stock image's `/opt/nim/reward.py` declares no refolding oracles. The
operator can configure a compatible oracle plugin and enable its loading;
the source documents the contract under `nim/api/oracles/` and
`docs/oracles.md`. Sending oracle metric tags cannot install or enable an
oracle. `model.oracle` identifies the actual predictor(s), and per-design
results must exist before quoting confidence or refolding success.

Search selects trajectories using weighted metric outputs. Stronger reward
does not establish binding affinity, expression, catalytic activity, or
experimental success. For independent validation, preserve binder/target
chain mapping and use the requested structure predictor and interface checks.
Report what was actually measured, with calibrated task-specific thresholds
only when supplied or supported by an appropriate benchmark.
