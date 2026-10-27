# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Install the same isolated CPU environment before either evaluation condition.

Usage: python3 /workspace/input/setup_eval_env.py
Arguments: none. Requires Python 3.10-3.13, uv or venv, and package-download access.
Output: /workspace/pbd-eval-venv; diagnostics in /logs/artifacts/pbd-eval-setup.log.
Exit codes: 0 ready; 10 interpreter; 11 venv; 12 installation; 13 imports.
"""

from contextlib import ExitStack
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ENVIRONMENT = Path("/workspace/pbd-eval-venv")
SETUP_LOG = Path("/logs/artifacts/pbd-eval-setup.log")
# Both wheels support the older Python interpreters in managed sandboxes.
DEPENDENCIES = ("numpy==2.2.6", "biotite==1.2.0")
# A universal wheel supplies pip when the sandbox omits pip/ensurepip. Verify
# the published PyPI digest before executing it with the isolated interpreter.
# https://pypi.org/project/pip/25.3/#files
PIP_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/44/3c/"
    "d717024885424591d5376220b5e836c2d5293ce2011523c9de23ff7bf068/"
    "pip-25.3-py3-none-any.whl"
)
PIP_WHEEL_SHA256 = "9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd"
PIP_WHEEL_MAX_BYTES = 2_000_000
# Harbor logs the exit code even when healthcheck stdout/stderr is unavailable.
EXIT_INTERPRETER = 10
EXIT_VENV = 11
EXIT_INSTALL = 12
EXIT_IMPORT = 13
IMPORT_CHECK = (
    "import sys, numpy, biotite; "
    "assert sys.prefix != sys.base_prefix, 'Evaluation Python is not isolated'; "
    "assert numpy.__version__ == '2.2.6'; "
    "assert biotite.__version__ == '1.2.0'; "
    "print('Evaluation imports verified:', numpy.__version__, biotite.__version__)"
)


def installer_environment():
    """Forward installation settings, not agent or model-service credentials."""
    names = (
        "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LD_LIBRARY_PATH",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
        "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_CERT", "PIP_CLIENT_CERT",
        "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "UV_NATIVE_TLS",
    )
    environment = {}
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    environment.update(UV_HTTP_TIMEOUT="15", UV_HTTP_RETRIES="1", UV_NO_PROGRESS="1")
    return environment


def download_pip_wheel(directory):
    """Fetch one pinned wheel over verified HTTPS; reject unexpected bytes."""
    with urllib.request.urlopen(PIP_WHEEL_URL, timeout=10) as response:
        contents = response.read(PIP_WHEEL_MAX_BYTES + 1)
    if len(contents) > PIP_WHEEL_MAX_BYTES:
        raise RuntimeError("Pinned pip wheel exceeded the download size limit")
    if hashlib.sha256(contents).hexdigest() != PIP_WHEEL_SHA256:
        raise RuntimeError("Pinned pip wheel SHA-256 mismatch; refusing to execute it")
    wheel = Path(directory) / "pip-25.3-py3-none-any.whl"
    wheel.write_bytes(contents)
    return wheel


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
        python = environment / "bin/python"
        uv = shutil.which("uv")
        process_env = installer_environment()
        if uv:
            report(f"Environment installer: {uv} (does not require venv/ensurepip)")
            create = [uv, "venv", "--python", executable, "--no-python-downloads",
                      "--no-config", "--no-cache", "--allow-existing", str(environment)]
            install = [uv, "pip", "install", "--python", str(python),
                       "--no-python-downloads", "--no-config", "--no-cache",
                       "--only-binary=:all:", *DEPENDENCIES]
        else:
            report("Environment installer: Python venv and verified pip wheel (uv not installed)")
            # Minimal sandbox distributions can include venv but omit ensurepip.
            # Creating the environment must not depend on pip already existing.
            create = [executable, "-m", "venv", "--without-pip", str(environment)]
        phase = "virtual environment creation"
        exit_code = EXIT_VENV
        report(f"Starting {phase}")
        subprocess.run(
            create, shell=False, check=True, timeout=20, env=process_env,
            stdout=log, stderr=subprocess.STDOUT if log is not None else None,
        )
        phase = "dependency installation"
        exit_code = EXIT_INSTALL
        with ExitStack() as installers:
            if not uv:
                phase = "installer download and verification"
                report(f"Starting {phase}")
                installer_dir = installers.enter_context(
                    tempfile.TemporaryDirectory(prefix="pbd-eval-installer-"),
                )
                wheel = download_pip_wheel(installer_dir)
                install = [str(python), str(wheel / "pip"), "install",
                           "--disable-pip-version-check", "--no-input", "--no-cache-dir",
                           "--only-binary=:all:", "--timeout", "15", "--retries", "1",
                           *DEPENDENCIES]
            phase = "dependency installation"
            exit_code = EXIT_INSTALL
            report(f"Starting {phase}")
            subprocess.run(
                install, shell=False, check=True, timeout=60, env=process_env,
                stdout=log, stderr=subprocess.STDOUT if log is not None else None,
            )
        phase = "dependency import verification"
        exit_code = EXIT_IMPORT
        report(f"Starting {phase}")
        subprocess.run(
            [str(python), "-c", IMPORT_CHECK], shell=False, check=True, timeout=10,
            env=process_env,
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
