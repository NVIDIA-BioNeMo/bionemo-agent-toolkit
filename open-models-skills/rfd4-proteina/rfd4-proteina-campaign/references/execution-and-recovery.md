# Execution and recovery

## Before submission

Read the chosen launcher and `.user_info_<cluster>`. Register the resolved config
and planned run, then state cluster, partition, account, GPU allocation, time,
memory, CPUs, QoS/priority-like options, and `SLURM_EXTRA_OPTIONS`.

Use the user's values exactly. Resource-efficiency advice is a recommendation to
discuss, not authority to override scheduler intent.

Pilot one job through generation, oracle evaluation, metrics, event ingestion, and
reconciliation before scaling. Validation and skill tests never submit jobs.

## During execution

Write events and outputs incrementally in the run directory. Use stable design,
evaluation, and prediction IDs in event payloads. Emit an explicit failed status
with the available log/error when a stage fails.

Only the coordinator imports events into SQLite. This avoids concurrent SQLite
writes from cluster workers and keeps recovery deterministic on shared filesystems.

## Recovery

After interruption, import the existing event stream and run reconciliation before
deciding what to retry. Search checkpoints and completed oracle predictions are
valid work even when the parent job did not finish.

Never delete or overwrite failed attempts. Create a new run for a retry and link
it to the earlier run. Report incomplete records and missing artifacts plainly.

## Stop conditions

Stop when the user-defined budget or scientific stopping rule is met, or when the
next action needs new authority. Do not continue spending compute merely because
the campaign has remaining possible branches.
