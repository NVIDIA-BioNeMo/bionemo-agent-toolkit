# Setup evaluation environment

`preflight-then-smoke-monomer` measures a real model installation and one GPU
generation. It requires an approved RFD4-Proteina source revision in a writable
checkout, GPU access compatible with that revision, sufficient storage, and
access to its dependencies and released checkpoint downloads. It cannot be
completed in a generic CPU sandbox containing only the skill catalog.

Before a live run, configure the operator's GPU-enabled sandbox/template with
that source checkout. Give every with-skill and baseline trial its own writable
copy at the same absolute path and revision. Keep it outside evaluator-managed
input, skill, and repository projection roots; those roots are replaced during
staging. Pass its **sandbox path** as `RFPROTEINA_ROOT` into the SkillEvaluator
process. Passing a host path does not mount or copy that checkout.

SkillEvaluator 1.5.6 supports `harbor.sandbox.template` in `config.yml` for an
operator-provided template. No template name or repository URL is guessed here.
The checked-in config forwards `RFPROTEINA_ROOT` and checks source files and
GPU visibility before agent execution. Failed checks are environment errors;
they must not produce an apparent successful installation or a scored GPU test.
The agent still installs the runtime, obtains the weights, runs preflight, and
generates the CIF. Preserve identical initial state for the two evaluation arms;
do not give the baseline a checkout already modified by a with-skill trial.

The dataset's `setup` and `success_criteria` objects are descriptive metadata,
not provisioning or executable grading hooks. The actual contract remains the
nonempty assertions and expected output. A report of missing prerequisites is
useful diagnosis, but does not pass this full-installation task.

Offline regression tests use temporary checkouts and test doubles to verify
runtime selection, data-path resolution, failure propagation, and file preservation.
They are not evidence of a successful model installation or GPU inference.
