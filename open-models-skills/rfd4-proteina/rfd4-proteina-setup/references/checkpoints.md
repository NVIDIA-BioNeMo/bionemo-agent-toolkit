# Checkpoints reference

Read `hf_ckpt_path` and `hf_ckpt_revision` from the selected checkout's
`configs/inference.yaml`. The current public release defaults to the
`nvidia/RFD4-Proteina` Hugging Face bundle at an immutable revision. The bundle
contains `config.json` and `model.safetensors`, including autoencoder weights.
It takes precedence over the legacy `ckpt_path`, `ckpt_name`, and
`autoencoder_ckpt_path` settings.

The public `scripts/download_assets.sh` downloads those two files using `hf
download ... --revision ...` into the Hub cache. It does not place them in
`DATA_PATH/flow_checkpoints` or `DATA_PATH/ae_checkpoints`. Set `HF_HOME` before
setup and generation to choose a shared cache location. A local bundle directory
can also be selected with `hf_ckpt_path=/absolute/bundle-directory`.

The standalone preflight checks the configured local directory or resolves the
configured revision from the cache with `local_files_only=True`. It checks
nonempty files and the bundle type/configuration, without downloading or loading
weights into memory. Missing bundles are download/configuration failures; rerun
the selected revision's downloader in the same cache environment. It does not
fall back to native checkpoints while a bundle is selected.

Studio has a stricter contract: its setup command downloads the pinned bundle
into `runtime-root/model-bundle`, verifies sizes and SHA-256 hashes, and writes
`.rfd4-public-bundle.json`. Its readiness probe verifies this directory and
receipt. A standalone Hub-cache preflight pass is insufficient for Studio.

## Legacy native checkpoints

When `hf_ckpt_path` is absent or null, the canonical preflight retains the legacy
checkpoint-pair checks under the selected `DATA_PATH`:

| Role | Path relative to `DATA_PATH` |
| --- | --- |
| Denoiser | `flow_checkpoints/<ckpt_name>` |
| Autoencoder | `ae_checkpoints/<basename of autoencoder_ckpt_path>` |

Use the installation and download instructions for that checkout's revision.
Do not request these obsolete files to repair a current public bundle setup.
