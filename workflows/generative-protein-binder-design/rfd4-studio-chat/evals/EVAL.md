# Studio recovery procedure evaluation

`recover-uncertain-submission` is a bounded explanation-only task for this chat
workflow. The agent must recover the recorded request/job identities and give
the correct monitoring, collection and shutdown procedure after an uncertain
submission. The user explicitly asks for a procedure, so this case requires no
SSH host, model installation, GPU, credentials or running MCP service.

The assertions grade the procedure and the absence of unauthorized actions.
They do not establish that SSH execution, GPU inference or result collection
worked. Transport, immutable request and collection regressions remain covered
by the repository's adapter tests; full generation still requires a real host
that passes Studio readiness and produces a verified result.

Use the same prompt and starting state for the with-skill and baseline arms.
Do not inject the target skill or its instructions into the baseline. A clear
plan is the requested output; fabricated tool results or collected files fail.
