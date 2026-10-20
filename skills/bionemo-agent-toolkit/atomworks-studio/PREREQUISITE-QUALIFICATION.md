# Qualified prerequisite profile

The pinned `ubuntu22.04-cuda13.2-minimal-candidate-v7` profile was qualified on a dedicated Ubuntu 22.04.5 amd64 machine with an NVIDIA A100 80GB. Qualification applies only to its exact package versions, hashes, package configuration and review guards. It does not qualify other distributions, repositories or CUDA profiles.

The privileged coordinator installed the reviewed 57-package delta. Subsequent verification found a clean package database, unchanged kernel/GPU driver, released execution ownership and no remaining installation scope or persistent service change. The native runtime then installed the locked dependencies and built tmol 0.1.59, verified both pinned checkpoints, passed all nine runtime checks before and after a representative inference, and produced a 672-atom CIF. The original setup operation completed successfully and was reconciled without another dispatch.

An independent auditor reviewed this evidence before the controller gate was enabled. The controller still rejects an unqualified profile, changed helper/profile bytes, changed package proposals, incompatible activity and stale authorization. Archive preparation alone never establishes runtime readiness.

This qualifies the prerequisite mechanism and exact profile, not the complete first-time Brev workflow or installed host release. Those acceptance gates remain open.

Evidence was captured under `managed-compute-evidence` in the development workspace. The evidence file digests below make the underlying observations identifiable without including private host configuration in the plugin.

- `fresh-prerequisite-v2-verification.json`: `24199bb5a29d793cf6cbe3044ee0b1f0dda68d30304bf49d37da28dcbff3d107`
- `fresh-prerequisite-cleanup.json`: `0be3998a9568ea2b06ceacb881fa67cce49757898cdfcafcc57e8573af227a81`
- `prerequisite-qualification-audit.md`: `f391d96d62859e99384747619608ead463bfafd00e607066cd8de78a95ebb51f`
- `live-runtime-progress-7.json`: `e6d71ca331e78fc992c4b49d1c1f4ce84ff0d6b8739492728251036e13350079`
- `live-runtime-phase-reconciliation-4.json`: `23b8ffeca1dff0de0e17d96bd2474477d7dfd3d51caffc1b9138770049accb68`
- `live-brev-scp-fallback-results.json`: `19a25522a1a81161fa7f7b69e0b053fba8d21b4321c02dd14280ce973566e3cd`
