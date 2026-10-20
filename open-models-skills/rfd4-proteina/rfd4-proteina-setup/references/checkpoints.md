# Checkpoints reference

RFD4-Proteína needs **two** checkpoints, both read from `$DATA_PATH` by default:

| Role | Default path (relative to `$DATA_PATH`) |
| --- | --- |
| Denoiser (latent diffusion, LDM) | `flow_checkpoints/<denoiser>.ckpt` |
| Autoencoder (frozen local latents) | `ae_checkpoints/<autoencoder>.ckpt` |

Each release file has a `.sha256` sidecar.

Read the active filenames from `configs/inference.yaml`:

```yaml
ckpt_name: <current release denoiser>
ckpt_path: ${oc.env:DATA_PATH}/flow_checkpoints
autoencoder_ckpt_path: ${oc.env:DATA_PATH}/ae_checkpoints/<current release autoencoder>
```

`configs/inference.yaml` is the **runtime source of truth** for "the SOTA model":
`generate.py` loads `ckpt_name` from it by default, and the GPU regression tests
read it too.

`download_example_data.sh` fetches exactly these two names, so a default
`generate.py` run resolves with no CLI override. To use a different checkpoint,
point at it with `ckpt_path=<dir> ckpt_name=<file.ckpt>`.

## Sizes / download

- Public HTTPS, no credentials.
- **Public bucket: `rfd4-proteina-public-e04a`** — everything published for
  external use (both checkpoints, the `test_dataset` tarball, the CCD mirror)
  lives there and is served anonymously at
  `https://rfd4-proteina-public-e04a.cwobject.com`.
- Host override: `RFPROTEINA_DATA_URL` (default
  `https://rfd4-proteina-public-e04a.cwobject.com`).
- Add `--with-test-dataset` to also fetch a tiny training set:
  `./scripts/download_example_data.sh "$DATA_PATH" --with-test-dataset`.
