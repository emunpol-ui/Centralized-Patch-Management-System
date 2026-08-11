"""
Deployment execution workflow orchestration (client-side; DEPLOY-003).

Ties together deployment polling (FR-009, DEPLOY-002's server-side
endpoint), installer download (FR-010), SHA-256 checksum verification, and
silent installation (FR-011) into a single runnable cycle, run from the
project root:

    python -m agent.deployment.manager

``run_deployment_cycle`` now also *reports* the execution's progress and
final result back to the server (DEPLOY-004, FR-012 Deployment Status
Reporting), via ``agent.communication.deployment_client.report_status``:
a ``"Downloading"`` report immediately before the installer download
begins, an ``"Installing"`` report immediately before the silent
installation command is executed, and a final ``"Completed"``/``"Failed"``
report once execution finishes. ``run_deployment_cycle`` still returns the
same ``DeploymentExecutionResult`` it always has, so any existing caller
of this module is unaffected by this addition.

--------------------------------------------------------------------------
Retry policy (FR-010 Error Conditions: "The Client Agent shall retry the
download according to the configured retry policy")

Only the *download* step is retried, and only for network/communication
failures (``DeploymentCommunicationError`` - e.g. a timeout, connection
error, or a transient server error). A checksum mismatch (FR-011) is a
definitive integrity/security failure, not a transient condition - per
this project's explicit instruction, it is NEVER retried; the deployment
is immediately reported as failed. Likewise, a poll failure or an
installer execution failure is not retried within a single cycle - the
next scheduled invocation of this module (once a Scheduler Module exists -
SAD Section 12.11, not yet implemented per INV-001's own documented scope)
is expected to try again from scratch.
--------------------------------------------------------------------------

--------------------------------------------------------------------------
DEPLOY-004 ADDITION - status reporting and its own retry policy

Each status report (``"Downloading"``, ``"Installing"``, and the final
``"Completed"``/``"Failed"``) is sent via
``agent.communication.deployment_client.report_status`` and retried, on
communication failure only, using the same bounded-retry shape already
established for installer downloads (see ``_download_with_retries``
above) - configured separately via
``AgentSettings.status_report_max_retries``/
``status_report_retry_delay_seconds`` (PRS NFR-004 / FR-012 Error
Conditions: "If reporting fails, the Client Agent shall retain the report
and retry transmission during the next communication cycle").

If a status report still fails after every retry, the report is persisted
to the Client Agent's local JSON status-report queue and retried at the
start of the next communication cycle. This satisfies FR-012 without
introducing a second database, message broker, or scheduler. The local
deployment outcome remains independent of reporting success/failure.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from agent.communication.deployment_client import (
    DeploymentCommunicationError,
    download_installer,
    poll_deployment,
    report_status,
)
from agent.config.settings import AgentSettings, get_agent_settings
from agent.installer.checksum import verify_checksum
from agent.installer.executor import (
    InstallerCommandError,
    build_command,
    execute_installer,
)
from agent.deployment.status_report_store import (
    PendingStatusReport,
    StatusReportStore,
    StatusReportStoreError,
)

logger = logging.getLogger(__name__)

# Runtime-only local queue required by FR-012 when a status report cannot
# be delivered during the current communication cycle. The file is ignored
# by Git and is created only when a report actually needs to be retained.
_STATUS_REPORT_QUEUE_PATH = Path(__file__).resolve().with_name("pending_status_reports.json")

# Status string vocabulary matches the server's
# ``backend.models.enums.DeploymentStatus`` values exactly, so a future
# DEPLOY-004 reporting client can pass ``DeploymentExecutionResult.status``
# straight through to the status-reporting endpoint's request body without
# any translation step.
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"

# DEPLOY-004 additions (FR-012): the two intermediate progress statuses a
# Client Agent reports as it moves through a deployment. Same string
# vocabulary as ``backend.models.enums.DeploymentStatus``/
# ``backend.schemas.deployment.DeploymentStatusReportRequest`` - no
# translation step is needed between this module and the server.
STATUS_DOWNLOADING = "Downloading"
STATUS_INSTALLING = "Installing"


class ChecksumMismatchError(Exception):
    """
    Raised internally when a downloaded installer's SHA-256 checksum does
    not match the value the server provided.

    A checksum mismatch is a definitive integrity/security failure
    (FR-011: "If the checksums do not match, the installer shall not be
    executed and the deployment shall be reported as Failed") - it must
    never be retried as though it were a transient network error, and the
    installer must never be executed once this is raised.
    """


@dataclass(frozen=True)
class DeploymentExecutionResult:
    """
    The outcome of one attempted deployment execution cycle, prepared for
    the later DEPLOY-004 status-reporting workflow (FR-012).

    ``status`` uses the same string vocabulary as the server's
    ``backend.models.enums.DeploymentStatus`` (``"Completed"`` /
    ``"Failed"``) - see the module-level ``STATUS_COMPLETED`` /
    ``STATUS_FAILED`` constants - so a future reporting client can pass it
    through unchanged. ``target_id``/``deployment_id`` are kept as strings
    (rather than ``uuid.UUID``) since that is the exact shape returned by
    the server's JSON poll response and required by its JSON download URL
    path - no round-trip UUID parsing is needed anywhere in this module.
    """

    target_id: str
    deployment_id: str
    status: str
    exit_code: Optional[int]
    error_message: Optional[str]


def _download_with_retries(
    target_id: str,
    installer_path: Path,
    *,
    server_url: str,
    api_key: str,
    timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
) -> None:
    """
    Attempt ``download_installer`` up to ``max_retries`` times, retrying
    only on ``DeploymentCommunicationError`` (FR-010 Error Conditions:
    "The Client Agent shall retry the download according to the
    configured retry policy").

    Re-raises the final attempt's ``DeploymentCommunicationError`` if
    every attempt fails. ``max_retries`` is treated as the total number of
    attempts (i.e. ``max_retries=1`` means no retries), so a
    misconfigured value of ``0`` or less still results in exactly one
    attempt rather than silently skipping the download altogether.
    """
    attempts = max(1, max_retries)
    last_error: Optional[DeploymentCommunicationError] = None

    for attempt in range(1, attempts + 1):
        try:
            download_installer(
                target_id,
                installer_path,
                server_url=server_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            return
        except DeploymentCommunicationError as exc:
            last_error = exc
            logger.warning(
                "Installer download attempt %d/%d failed for target %s: %s",
                attempt,
                attempts,
                target_id,
                exc,
            )
            if attempt < attempts:
                time.sleep(retry_delay_seconds)

    assert last_error is not None  # pragma: no cover - loop always sets this on failure
    raise last_error


def _send_status_report_with_retries(
    target_id: str,
    status: str,
    *,
    settings: AgentSettings,
    exit_code: Optional[int] = None,
    error_message: Optional[str] = None,
) -> bool:
    """
    Attempt one status report with the configured bounded retry policy.

    Returns ``True`` when the server accepts the report and ``False`` after
    every configured attempt fails. This low-level helper deliberately does
    not persist anything so queued reports can be acknowledged or retained
    by the caller without creating duplicate queue entries.
    """
    attempts = max(1, settings.status_report_max_retries)
    last_error: Optional[DeploymentCommunicationError] = None

    for attempt in range(1, attempts + 1):
        try:
            report_status(
                target_id,
                status,
                server_url=settings.server_url,
                api_key=settings.api_key,
                exit_code=exit_code,
                error_message=error_message,
                timeout_seconds=settings.request_timeout_seconds,
            )
            return True
        except DeploymentCommunicationError as exc:
            last_error = exc
            logger.warning(
                "Status report attempt %d/%d ('%s') failed for target %s: %s",
                attempt,
                attempts,
                status,
                target_id,
                exc,
            )
            if attempt < attempts:
                time.sleep(settings.status_report_retry_delay_seconds)

    logger.error(
        "Unable to report status '%s' for target %s after %d attempt(s).",
        status,
        target_id,
        attempts,
    )
    return False


def _report_status_with_retries(
    target_id: str,
    status: str,
    *,
    settings: AgentSettings,
    exit_code: Optional[int] = None,
    error_message: Optional[str] = None,
) -> bool:
    """
    Send a new status report and retain it locally if delivery fails.

    FR-012 requires a failed report to survive the current communication
    cycle and be retried during a later cycle. Immediate bounded retries
    happen first; only after those attempts are exhausted is the report
    written to the persistent local queue.

    A persistence failure is logged and does not alter the locally
    determined deployment result.
    """
    if _send_status_report_with_retries(
        target_id,
        status,
        settings=settings,
        exit_code=exit_code,
        error_message=error_message,
    ):
        return True

    try:
        store = StatusReportStore(_STATUS_REPORT_QUEUE_PATH)
        store.enqueue(
            target_id=target_id,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
        )
        logger.warning(
            "Retained undelivered status report '%s' for target %s for the next communication cycle.",
            status,
            target_id,
        )
    except StatusReportStoreError as exc:
        logger.error(
            "Status report '%s' for target %s could not be persisted for later retry: %s",
            status,
            target_id,
            exc,
        )
    return False


def _flush_pending_status_reports(settings: AgentSettings) -> None:
    """
    Retry persisted status reports before polling for a new deployment.

    Reports are processed in queue order. If a report still cannot be sent,
    later reports for that same target are not attempted in this cycle,
    because the server may still require the earlier transition first.
    Reports for other targets remain in the queue for a future cycle.

    A successful later report also acknowledges and removes older queued
    reports for that target because the server has already accepted a later
    state. This covers lost HTTP responses without replaying stale
    transitions forever.
    """
    try:
        store = StatusReportStore(_STATUS_REPORT_QUEUE_PATH)
        reports = store.load()
    except StatusReportStoreError as exc:
        logger.error("Unable to load persisted deployment status reports: %s", exc)
        return

    if not reports:
        return

    blocked_targets: set[str] = set()
    logger.info("Retrying %d persisted deployment status report(s).", len(reports))

    for report in reports:
        if report.target_id in blocked_targets:
            continue

        if _send_status_report_with_retries(
            report.target_id,
            report.status,
            settings=settings,
            exit_code=report.exit_code,
            error_message=report.error_message,
        ):
            try:
                store.acknowledge(report)
            except StatusReportStoreError as exc:
                logger.error(
                    "Status report '%s' for target %s was accepted but could not be removed "
                    "from the local queue: %s",
                    report.status,
                    report.target_id,
                    exc,
                )
        else:
            blocked_targets.add(report.target_id)
            logger.warning(
                "Keeping persisted status report '%s' for target %s; "
                "later reports for that target will wait for the next cycle.",
                report.status,
                report.target_id,
            )

def _report_final_status(
    target_id: str,
    result: DeploymentExecutionResult,
    *,
    settings: AgentSettings,
) -> None:
    """
    Report the terminal outcome (``Completed``/``Failed``) of a deployment
    execution attempt (DEPLOY-004, FR-012), via
    ``_report_status_with_retries``.

    Never raises and never influences ``result`` - the actual deployment
    outcome (already fully determined by ``_execute_pending_deployment``
    before this is ever called) and the outcome of *reporting* that
    result are kept strictly independent, per this ticket's explicit
    rule: a failed status report must never cause a successful
    installation to be recorded as failed (or vice versa). Every caller
    ignores this function's return value and always returns its own
    already-built ``result`` unchanged.
    """
    _report_status_with_retries(
        target_id,
        result.status,
        settings=settings,
        exit_code=result.exit_code,
        error_message=result.error_message,
    )


def _execute_pending_deployment(
    pending: Dict[str, Any],
    *,
    settings: AgentSettings,
) -> DeploymentExecutionResult:
    """
    Download, verify, and silently execute the installer for one pending
    deployment target (FR-010, FR-011).

    ``pending`` is the ``deployment`` dict returned by
    ``agent.communication.deployment_client.poll_deployment`` - i.e.
    already known to have ``target_id``, ``deployment_id``, and a nested
    ``package`` dict with ``checksum``, ``installer_filename``, and
    ``silent_command``.

    DEPLOY-004 addition: reports ``"Downloading"`` immediately before the
    installer download actually begins, ``"Installing"`` immediately
    before the silent installation command is actually executed (never
    merely because polling or downloading happened), and the terminal
    ``"Completed"``/``"Failed"`` outcome at every return point below, via
    ``_report_status_with_retries``/``_report_final_status``. A failed
    status report is logged but never changes the ``DeploymentExecutionResult``
    this function returns - see those helpers' docstrings.

    The downloaded installer is stored under a fresh, per-attempt
    temporary directory (``tempfile.TemporaryDirectory``) so that only
    files this workflow itself created are ever removed during cleanup -
    the directory (and everything in it) is deleted automatically when
    the ``with`` block exits, regardless of success or failure, without
    this function needing to enumerate or guess at what to delete.
    """
    target_id = str(pending["target_id"])
    deployment_id = str(pending["deployment_id"])
    package = pending["package"]
    expected_checksum = package["checksum"]
    installer_filename = package["installer_filename"]
    silent_command_template = package["silent_command"]

    with tempfile.TemporaryDirectory(prefix="cpms_deploy_") as tmp_dir_name:
        installer_path = Path(tmp_dir_name) / installer_filename

        # DEPLOY-004: report the download stage beginning - only now, not
        # merely because this target was returned by polling (FR-009's
        # poll is read-only and reports nothing on its own; see
        # ``poll_pending_deployment``'s server-side design note).
        _report_status_with_retries(target_id, STATUS_DOWNLOADING, settings=settings)

        try:
            _download_with_retries(
                target_id,
                installer_path,
                server_url=settings.server_url,
                api_key=settings.api_key,
                timeout_seconds=settings.download_timeout_seconds,
                max_retries=settings.download_max_retries,
                retry_delay_seconds=settings.download_retry_delay_seconds,
            )

            if not verify_checksum(installer_path, expected_checksum):
                raise ChecksumMismatchError(
                    f"Downloaded installer checksum did not match the expected value for "
                    f"deployment target {target_id}."
                )

            # DEPLOY-004: report the install stage beginning - only now
            # that the installer has been downloaded and its checksum
            # verified, and only immediately before actually invoking the
            # silent installation command (never merely because the
            # download finished).
            _report_status_with_retries(target_id, STATUS_INSTALLING, settings=settings)

            command = build_command(silent_command_template, installer_path)
            exec_result = execute_installer(
                command, timeout_seconds=settings.installer_execution_timeout_seconds
            )

        except DeploymentCommunicationError as exc:
            logger.error("Installer download failed for target %s: %s", target_id, exc)
            result = DeploymentExecutionResult(
                target_id=target_id,
                deployment_id=deployment_id,
                status=STATUS_FAILED,
                exit_code=None,
                error_message=f"Installer download failed: {exc}",
            )
            _report_final_status(target_id, result, settings=settings)
            return result
        except ChecksumMismatchError as exc:
            logger.error("%s", exc)
            result = DeploymentExecutionResult(
                target_id=target_id,
                deployment_id=deployment_id,
                status=STATUS_FAILED,
                exit_code=None,
                error_message=str(exc),
            )
            _report_final_status(target_id, result, settings=settings)
            return result
        except InstallerCommandError as exc:
            logger.error("Invalid silent installation command for target %s: %s", target_id, exc)
            result = DeploymentExecutionResult(
                target_id=target_id,
                deployment_id=deployment_id,
                status=STATUS_FAILED,
                exit_code=None,
                error_message=str(exc),
            )
            _report_final_status(target_id, result, settings=settings)
            return result

        if exec_result.timed_out:
            logger.error("Silent installation timed out for target %s.", target_id)
            result = DeploymentExecutionResult(
                target_id=target_id,
                deployment_id=deployment_id,
                status=STATUS_FAILED,
                exit_code=None,
                error_message="Silent installation timed out.",
            )
            _report_final_status(target_id, result, settings=settings)
            return result

        if exec_result.succeeded:
            logger.info("Deployment target %s installed successfully.", target_id)
            result = DeploymentExecutionResult(
                target_id=target_id,
                deployment_id=deployment_id,
                status=STATUS_COMPLETED,
                exit_code=exec_result.exit_code,
                error_message=None,
            )
            _report_final_status(target_id, result, settings=settings)
            return result

        logger.error(
            "Installer for target %s exited with non-zero code %s.", target_id, exec_result.exit_code
        )
        result = DeploymentExecutionResult(
            target_id=target_id,
            deployment_id=deployment_id,
            status=STATUS_FAILED,
            exit_code=exec_result.exit_code,
            error_message=f"Installer exited with non-zero code {exec_result.exit_code}.",
        )
        _report_final_status(target_id, result, settings=settings)
        return result


def run_deployment_cycle() -> Optional[DeploymentExecutionResult]:
    """
    Poll the CPMS Server for a pending deployment and, if one exists,
    download, verify, and silently install it (FR-009/FR-010/FR-011).

    Returns ``None`` if the agent is not configured (missing
    ``AGENT_API_KEY``), the poll itself fails (communication error), or no
    deployment is currently pending for this client - in every one of
    those cases there is nothing further for this cycle to do. Otherwise
    returns the ``DeploymentExecutionResult`` describing the download and
    installation outcome.

    Reports progress/result back to the server at each stage (DEPLOY-004,
    FR-012) via ``_execute_pending_deployment``'s internal
    ``_report_status_with_retries``/``_report_final_status`` calls - see
    the module docstring for the full status-reporting and retry
    behavior. A status-reporting failure never changes the value this
    function returns.
    """
    settings = get_agent_settings()
    if not settings.api_key:
        logger.error(
            "AGENT_API_KEY is not configured. Set it to a Client API key issued via "
            "POST /api/admin/keys and claimed via POST /api/register before running the agent."
        )
        return None

    # FR-012: reports that could not be delivered during an earlier cycle
    # must be retried before polling for another deployment.
    _flush_pending_status_reports(settings)

    try:
        pending = poll_deployment(
            server_url=settings.server_url,
            api_key=settings.api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
    except DeploymentCommunicationError as exc:
        logger.error("Deployment poll failed: %s", exc)
        return None

    if pending is None:
        logger.info("No pending deployment for this client.")
        return None

    logger.info(
        "Pending deployment target %s found (deployment=%s); beginning download and installation.",
        pending.get("target_id"),
        pending.get("deployment_id"),
    )
    result = _execute_pending_deployment(pending, settings=settings)
    logger.info("Deployment execution result: %s", result)
    return result


def _configure_logging() -> None:
    """
    Configure Client Agent logging for a standalone ``python -m
    agent.deployment.manager`` invocation.

    Mirrors ``agent.main._configure_logging``'s console-plus-file
    approach (SAD Section 7.5 / 12.13 client-side log location), kept
    local to this entry point for the same reason INV-001 kept its own
    logging setup local: no other component in this package needs
    logging configuration of its own - each module simply calls
    ``logging.getLogger(__name__)`` and relies on this root configuration
    when run directly.
    """
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "agent.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    """
    Run one poll-download-execute cycle. Returns a process exit code
    (``0`` for "nothing to do" or a completed installation, ``1`` for a
    failed installation) suitable for use by a future Windows Scheduled
    Task (PRS Section 8) invoking this module directly.
    """
    _configure_logging()
    result = run_deployment_cycle()
    if result is None:
        return 0
    return 0 if result.status == STATUS_COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_DOWNLOADING",
    "STATUS_INSTALLING",
    "ChecksumMismatchError",
    "DeploymentExecutionResult",
    "run_deployment_cycle",
    "main",
]