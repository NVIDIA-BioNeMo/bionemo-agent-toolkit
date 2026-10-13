# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Install the same isolated CPU environment before either evaluation condition.

Usage: python3 /workspace/input/setup_eval_env.py
Arguments: none. Requires Python 3.10-3.13 with venv/ensurepip and index access.
Output: /workspace/pbd-eval-venv; diagnostics in /logs/artifacts/pbd-eval-setup.log.
Exit codes: 0 ready; 10 interpreter; 11 venv; 12 installation; 13 imports.
"""

from contextlib import ExitStack
from pathlib import Path
import shutil
import subprocess
import sys

ENVIRONMENT = Path("/workspace/pbd-eval-venv")
SETUP_LOG = Path("/logs/artifacts/pbd-eval-setup.log")
# Both wheels support the older Python interpreters in managed sandboxes.
DEPENDENCIES = ("numpy==2.2.6", "biotite==1.2.0")
# Harbor logs the exit code even when healthcheck stdout/stderr is unavailable.
EXIT_INTERPRETER = 10
EXIT_VENV = 11
EXIT_INSTALL = 12
EXIT_IMPORT = 13
IMPORT_CHECK = (
    "import numpy, biotite; "
    "assert numpy.__version__ == '2.2.6'; "
    "assert biotite.__version__ == '1.2.0'; "
    "print('Evaluation imports verified:', numpy.__version__, biotite.__version__)"
)


def select_python():
    """Use an installed compatible interpreter without downloading Python."""
    if (3, 10) <= sys.version_info[:2] < (3, 14):
        return sys.executable
    for name in ("python3.13", "python3.12", "python3.11", "python3.10"):
        executable = shutil.which(name)
        if executable:
            try:
                result = subprocess.run(
                    [executable, "-c", "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)"],
                    shell=False, check=False, timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0:
                return executable
    raise RuntimeError("An installed Python 3.10-3.13 is required for the pinned evaluation wheels")


def setup(environment=ENVIRONMENT, log=None):
    """Create a writable venv; never modify the sandbox's system site-packages."""
    def report(message, *, error=False):
        print(message, file=sys.stderr if error else sys.stdout, flush=True)
        if log is not None:
            try:
                print(message, file=log, flush=True)
            except OSError as exc:
                print(f"Could not write setup diagnostic: {exc}", file=sys.stderr, flush=True)

    phase = "interpreter selection"
    exit_code = EXIT_INTERPRETER
    try:
        report(f"Bootstrap interpreter: {sys.executable} (Python {sys.version.split()[0]})")
        executable = select_python()
        report(f"Evaluation base interpreter: {executable}")
        phase = "virtual environment creation (requires venv/ensurepip)"
        exit_code = EXIT_VENV
        report(f"Starting {phase}")
        subprocess.run(
            [executable, "-m", "venv", str(environment)], shell=False, check=True, timeout=30,
            stdout=log, stderr=subprocess.STDOUT if log is not None else None,
        )
        python = environment / "bin/python"
        phase = "dependency installation"
        exit_code = EXIT_INSTALL
        report(f"Starting {phase}")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "--only-binary=:all:", "--timeout", "15", "--retries", "1",
             *DEPENDENCIES],
            shell=False, check=True, timeout=70,
            stdout=log, stderr=subprocess.STDOUT if log is not None else None,
        )
        phase = "dependency import verification"
        exit_code = EXIT_IMPORT
        report(f"Starting {phase}")
        subprocess.run(
            [str(python), "-c", IMPORT_CHECK], shell=False, check=True, timeout=10,
            stdout=log, stderr=subprocess.STDOUT if log is not None else None,
        )
        report(f"Use {python} for Python commands in this evaluation.")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report(f"Evaluation setup failed during {phase}: {exc}", error=True)
        return exit_code
    return 0


def main():
    """Retain subprocess output even when Harbor omits healthcheck output."""
    with ExitStack() as stack:
        try:
            SETUP_LOG.parent.mkdir(parents=True, exist_ok=True)
            log = stack.enter_context(SETUP_LOG.open("w", encoding="utf-8"))
        except OSError as exc:
            print(f"Could not create setup log {SETUP_LOG}: {exc}", file=sys.stderr, flush=True)
            log = None
        return setup(log=log)


if __name__ == "__main__":
    sys.exit(main())
