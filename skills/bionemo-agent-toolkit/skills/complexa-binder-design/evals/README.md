# Tier 3 coverage

The active suite evaluates **campaign planning when the model runtime is
unavailable**, plus one negative routing case. The planner and artifact grader use
only standard Python in the existing sandbox image, with the same inputs in both
conditions. No custom Dockerfile, package installation, GPU or model credentials
are required. It does not test structure preparation, generation or independent
refolding. The four CPU execution cases are preserved in
`deferred/cpu-artifacts.json` and remain covered by local regression tests. Their
fixture coordinates and scores are synthetic. The original four live campaign
cases are preserved byte-for-byte in `deferred/live-campaigns.json`,
with their original configuration in `deferred/config.yml`; they are not active
coverage. Planning success is distinct from completion of a scientific campaign.

The October 9, 2026 report completed evaluation with neutral quality (0.5902,
lift -0.0187). Its three positive tasks required a GPU, Complexa installation,
weights, structure downloads and a working refolder, none of which the report
established as provisioned. All three scientific goals scored zero. The outer
“All Passed” label did not mean those goals succeeded. Claude's GROMACS timeout
excluded that agent from scored coverage; it was not a measured quality zero.

| Active case | Required deliverable |
| --- | --- |
| `planning-pdl1-blocked` | Preserve 5JDR/A, beam-search and exactly eight generated candidates in a blocked, bounded plan; request epitope evidence. |
| `planning-barnase-interface` | Plan sequence/structure co-design for 1BRS/A and independent validation; require verification of the barstar partner chain. |
| `planning-lysozyme-patch` | Preserve the desired five passing binders for 1LYZ/A, request the missing patch, and cap attempts without guaranteeing passers. |
| `routing-gromacs-guidance` | Provide bounded MD guidance with no binder workflow, installations or simulation. |

The planning profile has its own dataset digest and coverage scope. Do not
compare its aggregate as a like-for-like improvement over the old live campaign
score or the preceding eight-case CPU profile. Compare per-agent results and
report planning coverage explicitly.

The preceding eight-case profile added a custom Dockerfile for scientific CPU
dependencies. That triggered Astra's managed image builder, and the October 12 CI
attempt stopped at builder authentication before any agent tests ran. The active
planning profile uses the default sandbox and does not invoke that image builder;
normal sandbox and agent API access are still required. No `nvcarps-ci` changes
are needed for this profile.

The active config forwards no model keys. All paths in `files` are staged under
`/workspace/input/`; outputs go under `/workspace/output/`.
The three planning requests explicitly supply the unavailable-runtime facts so
agents need no repeated readiness probes. Each plan must preserve the user's
intent, explain missing inputs/runtime, order future
stages, retain independent holo/apo gates and record finite budgets/stops. The
scientific decision stays NOT_EVALUATED, with no generated candidates or metrics.
No task depends on another trial's artifacts. The negative case requests guidance
explicitly, so running a long simulation is outside its scope.

`grading.mode: aces_plus_custom` retains the ACES trajectory judges and adds
`grader.py`, which imports no skill code and verifies saved artifacts against
pinned fixture bytes and independently calculated results. It checks the actual
plan semantics, unchanged future validation gates, finite budgets and coverage
labels. It also supports the deferred CPU artifact cases. Mutation tests ensure
fabricated execution, changed targets, missing blockers and unbounded plans do not
pass. The guidance case has no artifact metric and is judged by the trajectory
rubric.

SkillEvaluator 1.5.6 does not use this custom artifact metric as its headline
gate. Inspect `artifact_correctness` in each positive trial's custom reward;
an ACES pass with incorrect artifacts does not establish workflow completion.
Local regression tests do not establish live-agent scores or lift:

```bash
python3 -B -S -m unittest discover -s tests -p test_campaign_planning.py -v
```

## Optional CPU execution coverage

`deferred/cpu-artifacts.json` retains these cases unchanged. They are outside the
default Tier 3 dataset and need a CPU environment with NumPy 2.5.1, Biotite 1.7.1
and PyYAML 6.0.3 provisioned before running the tests. Keep these dependencies and
fixtures identical in both conditions if reactivating this separate agent profile.
Paths in its `files` entries remain relative to the skill root; use the shared
`grader.py` and `aces_plus_custom` grading. Do not mix its results into the
planning-only score.

| Deferred case | Required deliverable |
| --- | --- |
| `offline-interface-preflight` | Derive one interface and save exact target/hotspot geometry. |
| `offline-missing-epitope` | Detect an absent explicit patch and save a failed preflight without substitutes. |
| `offline-independent-ranking` | Apply all unchanged gates; preserve missing/failing evidence; rank and report a quota shortfall. |
| `offline-interrupted-validation` | Reject stale responses, retain current failures/missing results, preserve raw evidence and replace stale rankings. |

With those dependencies already installed, the existing execution and mutation
tests run locally without model inference or network access:

```bash
python3 -m unittest discover -s tests -p test_tier3_offline.py -v
```

## Restoring live campaign evaluation

Keep live campaigns separate from this CPU profile. Before enabling the archived
cases, provision the same GPU runtime, trusted Complexa CLI/config/checkpoints,
AF2 reward parameters, independent refolder and verified ipSAE dependency in both
conditions. Check model/endpoint health before starting either agent. Forward
only the required credential. Stage verified local structures and their source
hashes, target chains and reviewed hotspots; a name or remote URL is not a fixture.

Resolve these archived task defects before a new live-profile run:

- PD-L1 needs a reviewed accessible epitope or explicitly selected protein partner.
- Barnase needs an explicit barstar chain. `hotspot_strategy.py` is a helper;
  preflight derives PDB contacts internally, so grade its coordinate-based results
  rather than a nonexistent helper CLI invocation.
- Lysozyme's prompt supplies no actual “defined surface patch”. Stage the reviewed
  residues. Preserve the request for five passing binders, but report workflow
  completion and scientific quota attainment separately. Bound generation to two
  rounds and stop on a zero-passer round; do not guarantee passers or lower gates.
- Use the bounded guidance prompt for negative routing. A 100 ns production run
  does not belong in a missing-input routing test.

Successful GPU integration requires saved real generation and independent holo/apo
responses, measured metrics, provenance and a ranked report. A blocked readiness
check, a shell scaffold or synthetic scores cannot substitute for those results.

## Security evidence

The reported curl downloads use lowercase `-f` (HTTP failure handling), not
uppercase `-F` (form upload). SkillEvaluator 1.5.6 lowercases the command and
matches `-f` as possible exfiltration. It also matches deletion text inside a
shell patch payload as an executed command. Correct these classifications in the
evaluator, with upload/actual-deletion regression cases; do not hide commands in
another language to avoid scanning. Truncated evidence is insufficient to excuse
other cleanup actions. TLS bypasses and real unsafe operations remain findings.
