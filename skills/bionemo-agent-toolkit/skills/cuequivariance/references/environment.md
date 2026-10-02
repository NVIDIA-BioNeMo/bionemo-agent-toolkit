# Isolated example execution

Use this reference only when an actual run needs dependencies absent from the
selected interpreter. A request to explain an API or show code does not require
environment setup. Preserve any explicit no-install or no-upgrade constraint.

For work inside an existing project, use its environment and declared package
versions. The commands below validate a standalone example against 0.12.0; they
do not verify integration with a project that uses a different version.

## When uv is already available

Save the relevant Python example as `example.py` in the working directory, then:

```bash
uv run --no-project --isolated --with "cuequivariance==0.12.0" python example.py
```

This downloads dependencies if needed and runs in an isolated environment.
`--no-project` prevents syncing the surrounding project's dependencies, and
`--isolated` avoids reusing its virtual environment. Use the same invocation for
subsequent checks; there is no need to activate, delete, or recreate a project
environment. See [uv's script execution documentation](https://docs.astral.sh/uv/guides/scripts/).

## Without uv

If the selected Python has working `venv` and `ensurepip` support, create a new,
uniquely named environment. This POSIX-shell example uses `python3`; substitute
the chosen interpreter if the project uses another one:

```bash
cueq_env="$(mktemp -d "${TMPDIR:-/tmp}/cuequivariance.XXXXXX")" &&
python3 -m venv "$cueq_env" &&
"$cueq_env/bin/python" -m pip install "cuequivariance==0.12.0" &&
"$cueq_env/bin/python" example.py
```

Keep the environment path for any follow-up run. If setup fails, leave existing
environments intact and retain the error. A missing `ensurepip` can be avoided
with the uv route when uv is already available. If neither route is available,
report that execution needs a working isolated Python environment; provide the
code and its assertions without claiming they ran. Do not switch to system or
user-site installs, remove an existing virtual environment, or override an
externally managed Python installation just to run the example.
