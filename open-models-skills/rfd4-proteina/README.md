# Public RFD4-Proteina skills

These three skills are copied without modification from
[RosettaCommons/RFD4-Proteina](https://github.com/RosettaCommons/RFD4-Proteina/tree/c7c6cacbc617ab074b4e234448bed6581840949f/skills)
at commit `c7c6cacbc617ab074b4e234448bed6581840949f`. `source-manifest.json`
records every upstream file checksum. Each skill includes the upstream
BSD-3-Clause license as `LICENSE.upstream`.

The scope is setup, annotated CIF preparation, and single-shot generation.
Campaigns, search, commitment curves, and refolding are not added to this plugin.
Upstream skills expect a model checkout containing `.project-root`; their shell
commands and relative model paths run from that checkout, not the BAT root.

For the embedded Studio managed-compute flow, use its MCP tools to review and
execute setup, readiness checks, and jobs. These upstream references do not
replace the managed controller's reviewed setup, ownership, and recovery rules.
Optional refolding instructions in upstream references are not part of the
managed default runtime.
