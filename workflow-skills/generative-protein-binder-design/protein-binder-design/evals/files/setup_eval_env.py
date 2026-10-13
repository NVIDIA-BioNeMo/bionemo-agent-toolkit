# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Install the same isolated CPU environment before either evaluation condition.

Usage: python3 /workspace/input/setup_eval_env.py
Arguments: none. Requires an installed Python 3.12+ with venv/ensurepip and index access.
Output: /workspace/pbd-eval-venv; setup diagnostics on stdout/stderr.
Exit codes: 0 for verified imports; 1 for failed setup.
"""

from pathlib import Path
import shutil
import subprocess
import sys

ENVIRONMENT = Path("/workspace/pbd-eval-venv")
DEPENDENCIES = ("numpy==2.5.1", "biotite==1.7.1")
IMPORT_CHECK = (
    "import numpy, biotite; "
    "assert numpy.__version__ == '2.5.1'; "
    "assert biotite.__version__ == '1.7.1'; "
    "print('Evaluation imports verified:', numpy.__version__, biotite.__version__)"
)


def select_python():
    """Use an installed compatible interpreter without downloading Python."""
    if sys.version_info >= (3, 12):
        return sys.executable
    for name in ("python3.12", "python3.13", "python3.14"):
        executable = shutil.which(name)
        if executable:
            result = subprocess.run(
                [executable, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"],
                shell=False, check=False, timeout=5,
            )
            if result.returncode == 0:
                return executable
    raise RuntimeError("An installed Python 3.12+ is required for the pinned evaluation wheels")


def setup(environment=ENVIRONMENT):
    """Create a writable venv; never modify the sandbox's system site-packages."""
    phase = "interpreter selection"
    try:
        executable = select_python()
        print(f"Evaluation base interpreter: {executable}", flush=True)
        phase = "virtual environment creation (requires venv/ensurepip)"
        subprocess.run([executable, "-m", "venv", str(environment)], shell=False, check=True, timeout=30)
        python = environment / "bin/python"
        phase = "dependency installation"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "--only-binary=:all:", "--timeout", "15", "--retries", "1",
             *DEPENDENCIES],
            shell=False, check=True, timeout=70,
        )
        phase = "dependency import verification"
        subprocess.run([str(python), "-c", IMPORT_CHECK], shell=False, check=True, timeout=10)
        print(f"Use {python} for Python commands in this evaluation.", flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Evaluation setup failed during {phase}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(setup())
