# Environment reference

Model execution uses a Python environment from a separate RFD4-Proteina model
checkout. Set `RFPROTEINA_ROOT` to its absolute path. Read `docs/installation.rst`
inside that checkout for the revision-specific environment and scheduler contract;
this skill catalog does not contain the model source. Check that the checkout
contains `.project-root`, `pyproject.toml`, and `configs/inference.yaml` before setup.
An absent runtime dispatcher does not invalidate these source files. Keep the
absolute installed skill directory separate so its helpers remain reachable
after changing to the model directory.

If no checkout is available, obtain the actual repository URL and revision from
the user or established project configuration. Clone into an unused directory;
preserve existing catalogs, Git metadata, data, and partial checkouts when a
clone fails. Do not substitute another Proteina implementation or disable TLS
verification to work around unavailable source.

From the verified model root, following that revision's installation manual:

```bash
bash setup.sh --native --skip-search-envs  # CUDA 13, Python 3.12, Linux x86_64
source .venv/bin/activate
```

Setup installs AtomWorks through pip at the version pinned in
`pyproject.toml`. It creates `.venv` with the native dependencies and copies
`.env.local.example` only when neither `.env.local` nor `.env` exists. Existing
settings are preserved and shell startup files are not edited. Public setup downloads
the configured Hugging Face bundle at its pinned revision into the Hub cache
(`HF_HOME` can select the cache). It sets `DATA_PATH` for ancillary data, recording
the default in the active environment file if no path is configured. Existing
downloads are reused. Use `bash setup.sh --skip-weights --skip-search-envs` to install only the environment.

Studio uses a separate locked profile. Follow the skill's **Studio runtime** path;
ordinary upstream setup is insufficient for Studio's exact readiness checks.

Edit `.env.local` for data paths and optional tool settings. The loader falls
back to `.env` if `.env.local` is absent; the files are not merged. If setup
preserves an existing `.env`, edit that file or rename it to `.env.local`.
Exported shell values take precedence. Treat configuration files as data: do not
source them as shell programs, print their contents, or copy credentials into reports.
The skill's preflight accepts exported `DATA_PATH` or an explicit `--data-path`;
it does not load these files. For the public bundle, it defaults ancillary data
to `data_path` when unset and checks the already downloaded Hub cache offline.
For legacy weights, supply the actual data directory selected during setup.
Relative paths resolve against the model root, independently of
the directory containing the skill.

Installed commands such as `rfd4-generate` use the Python environment where
they were installed. Activate it first, or use `.venv/bin/rfd4-generate` directly.
SLURM launchers prefer the active environment and can find the checkout `.venv`
automatically. They need no cluster argument; `scripts/.user_info_local` is optional.
`bash setup.sh --venv` adds development and notebook tools.

Run the installed helper with `--repo-root "$RFPROTEINA_ROOT"` from any working
directory. It selects `RFPROTEINA_PYTHON` first when explicitly configured,
then an executable `scripts/rfproteina_exec.sh`, then `.venv/bin/python`.
Set `RFPROTEINA_PYTHON` to the intended interpreter for another environment;
there is no silent fallback to an unrelated system Python. The model installer
supplies PyYAML along with the model's CUDA, PyTorch, and AtomWorks stack.

For rdkit/PoseBusters segmentation faults, check the selected Python build and
C++ runtime against that revision's installation manual and Makefile. Use its
maintained launcher when an ABI workaround is required; keep any library-loading
setting scoped to that command and to libraries supplied by the trusted runtime.
Do not turn a diagnostic workaround into a persistent shell startup setting.
