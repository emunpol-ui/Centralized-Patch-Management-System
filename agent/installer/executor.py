"""
Silent installer execution (client-side; DEPLOY-003, FR-011 Silent
Software Installation).

Executes an approved installer using its administrator-defined silent
installation command "as a direct process execution rather than through a
system shell, to prevent shell metacharacter injection" (PRS FR-011
Functional Behavior, step 3). ``subprocess.run`` is always invoked with
``shell=False`` (the default) and a pre-tokenized argument list - never a
single shell command string - so no shell (``cmd.exe``, ``powershell.exe
-Command``, etc.) is ever spawned to interpret the command.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# The token a repository package's ``silent_command`` uses to reference
# the installer file that was actually downloaded for this deployment
# (FR-006 Repository Metadata / FR-011 Functional Behavior step 3). Must
# match the placeholder REP-001's upload-time validation
# (``backend.schemas.repository.RepositoryPackageUploadMetadata``) already
# enforces server-side.
INSTALLER_PATH_PLACEHOLDER = "{installer_path}"

# Default ceiling on how long a single silent installation may run before
# it is forcibly terminated and reported as failed (FR-011 Error
# Conditions: "Installation times out").
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 600.0


class InstallerCommandError(ValueError):
    """
    Raised when a repository package's ``silent_command`` cannot be turned
    into a safe, direct-process argument list (e.g. it cannot be tokenized
    at all, or does not reference the ``{installer_path}`` placeholder
    anywhere).

    This should be rare in practice - REP-001's upload-time validation
    already rejects a ``silent_command`` missing the placeholder before it
    is ever persisted - but the Client Agent must not assume every record
    it will ever encounter passed that validation (e.g. a package
    persisted before that validation existed), and must fail safely rather
    than executing something unexpected.
    """


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of running a silent installer as a direct process."""

    command: List[str]
    exit_code: Optional[int]
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        """``True`` only when the process ran to completion with exit code 0."""
        return not self.timed_out and self.exit_code == 0


def build_command(silent_command_template: str, installer_path: Path) -> List[str]:
    """
    Turn a repository package's ``silent_command`` template into a safe,
    tokenized argument list ready for direct process execution
    (``subprocess.run(..., shell=False)``).

    The template is tokenized with ``shlex.split`` (for its
    quoted-argument handling, e.g. ``msiexec /i {installer_path} /quiet``)
    *before* the actual installer path is substituted in place of the
    literal ``{installer_path}`` token. This ordering matters:
    ``installer_path`` is an absolute Windows path containing backslashes,
    and tokenizing a string that already contains backslashes would treat
    them as shell-style escape characters and corrupt the path. Splitting
    the template first (which contains no backslashes) and substituting
    afterwards avoids that problem entirely.

    Raises ``InstallerCommandError`` if the template cannot be tokenized,
    or does not reference ``{installer_path}`` anywhere - a silent command
    that never mentions the downloaded installer cannot plausibly install
    it, and must not be executed as-is.
    """
    try:
        tokens = shlex.split(silent_command_template)
    except ValueError as exc:
        raise InstallerCommandError(f"Silent installation command could not be parsed: {exc}") from exc

    if not tokens or not any(INSTALLER_PATH_PLACEHOLDER in token for token in tokens):
        raise InstallerCommandError(
            f"Silent installation command does not reference the "
            f"'{INSTALLER_PATH_PLACEHOLDER}' placeholder."
        )

    resolved_path = str(installer_path)
    return [token.replace(INSTALLER_PATH_PLACEHOLDER, resolved_path) for token in tokens]


def execute_installer(
    command: List[str],
    *,
    timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """
    Run ``command`` as a direct process (``shell=False``) and capture its
    exit code, stdout, and stderr (FR-011 functional behavior: "The
    installation process is monitored" / "The installer exit code is
    captured").

    If the process does not complete within ``timeout_seconds``, it is
    forcibly killed (``subprocess`` does this automatically on
    ``TimeoutExpired``) and the result is reported with
    ``timed_out=True`` and ``exit_code=None`` (FR-011 Error Conditions:
    "Installation times out") - the caller must treat this as a
    definitive failure, not something to silently retry.

    Never raises for an installer that runs and simply exits with a
    non-zero code (FR-011 explicitly expects this - "the installer
    returns an error code" is a normal, capturable outcome, not an
    exception); only a failure to even *launch* the process (e.g. the
    executable cannot be found) is caught and reported as a failed
    ``ExecutionResult`` rather than propagating as an uncaught
    ``OSError``.
    """
    logger.info("Executing installer command: %s", command)
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            timeout=timeout_seconds,
            text=True,
        )
        duration = time.monotonic() - start
        logger.info(
            "Installer command finished in %.1fs with exit code %s.", duration, completed.returncode
        )
        return ExecutionResult(
            command=command,
            exit_code=completed.returncode,
            timed_out=False,
            duration_seconds=duration,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        logger.error("Installer command timed out after %.1fs: %s", duration, command)
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ExecutionResult(
            command=command,
            exit_code=None,
            timed_out=True,
            duration_seconds=duration,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError as exc:
        duration = time.monotonic() - start
        logger.error("Failed to launch installer command %s: %s", command, exc)
        return ExecutionResult(
            command=command,
            exit_code=None,
            timed_out=False,
            duration_seconds=duration,
            stdout="",
            stderr=str(exc),
        )


__all__ = [
    "INSTALLER_PATH_PLACEHOLDER",
    "DEFAULT_EXECUTION_TIMEOUT_SECONDS",
    "InstallerCommandError",
    "ExecutionResult",
    "build_command",
    "execute_installer",
]
