# Environment reference

Model execution uses a Python environment. See
[installation](../../../docs/installation.rst) for the source of truth.

From the repository root:

```bash
make setup          # native CUDA 13, Python 3.12, Linux x86_64
source .venv/bin/activate
rfd4-generate inputs=data/benchmarks/monomer out_dir=./runs/smoke
```

Setup installs AtomWorks through pip from the Git revision pinned in
`pyproject.toml`. It creates `.venv` with the native dependencies and copies
`.env.local.example` only when neither `.env.local` nor `.env` exists. Existing
settings are preserved and shell startup files are not edited. Setup also downloads
the released checkpoint pair into `DATA_PATH` (default `./data_path`), recording
the default in the active environment file if no path is configured. Existing
checkpoints are reused. Use `bash setup.sh --skip-weights` to install only the environment.

Edit `.env.local` for data paths and optional tool settings. The loader falls
back to `.env` if `.env.local` is absent; the files are not merged. If setup
preserves an existing `.env`, edit that file or rename it to `.env.local`.
Exported shell values take precedence.

Installed commands such as `rfd4-generate` use the Python environment where
they were installed. Activate it first, or use `.venv/bin/rfd4-generate` directly.
SLURM launchers prefer the active environment and can find the checkout `.venv`
automatically. They need no cluster argument; `scripts/.user_info_local` is optional.
`bash setup.sh --venv` adds development and notebook tools.

uv's Python may segfault in rdkit/posebusters unless `LD_PRELOAD` points at the
bundled `libstdc++.so.6`. The `Makefile` sets this automatically for `make test`;
mirror it if you hit a segfault outside `make`.
