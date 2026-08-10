"""
Deployment polling and installer download client (client-side; DEPLOY-003).

Talks to the CPMS Server's ``GET /api/agent/deployments/poll`` (FR-009,
server-side implemented by DEPLOY-002) and
``GET /api/agent/deployments/{target_id}/download`` (FR-010, server-side
implemented by this ticket) endpoints, authenticated the same way as
``agent.communication.inventory_client`` - an ``Authorization: Bearer
<api_key>`` header, matching the server's ``require_client_api_key``
dependency. No new server-side authentication mechanism is introduced by
this module.

Kept separate from ``agent.installer`` (which owns checksum verification
and silent-installer execution) and ``agent.deployment`` (which
orchestrates the full poll -> download -> verify -> execute cycle) per the
SAD Section 7.5 directory layout: this module is purely a "Communication
Module" concern (HTTP requests/responses), with no filesystem-hashing or
process-execution logic of its own beyond writing the downloaded bytes to
the destination path it is given.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEPLOYMENT_POLL_PATH = "/api/agent/deployments/poll"

# Chunk size used when streaming a downloaded installer to disk, matching
# the server's own streaming chunk size in
# ``backend.utils.file_storage.save_and_hash`` - large installer files
# never need to be fully buffered in memory on either side of the
# connection.
_DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB


class DeploymentCommunicationError(Exception):
    """
    Raised when polling or downloading fails outright (the request cannot
    be sent, the response is not valid JSON where JSON is expected, or the
    server rejects the request with a non-success status code).

    Deliberately a single exception type for both polling and downloading
    failures - callers (``agent.deployment.manager``) are expected to
    treat any communication failure the same way: log it and stop this
    deployment cycle without executing anything, never as a reason to
    fabricate a "successful" result.
    """


def poll_deployment(
    *,
    server_url: str,
    api_key: str,
    timeout_seconds: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """
    Poll the CPMS Server for the authenticated client's own pending
    deployment (FR-009).

    Returns the ``data.deployment`` payload - a dict shaped like
    ``backend.schemas.deployment.DeploymentPollTargetResponse`` (i.e. with
    ``target_id``, ``deployment_id``, ``status``, ``created_at``, and a
    nested ``package`` dict carrying ``checksum``, ``silent_command``,
    ``installer_filename``, etc.) - if one is pending, or ``None`` if
    ``has_deployment`` is ``False``.

    Raises ``DeploymentCommunicationError`` if the request cannot be sent,
    the response is not valid JSON, or the server rejects the request.
    """
    url = server_url.rstrip("/") + DEPLOYMENT_POLL_PATH
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        logger.error("Deployment poll to %s failed: %s", url, exc)
        raise DeploymentCommunicationError(f"Unable to reach CPMS Server at {url}: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        logger.error(
            "Deployment poll to %s returned a non-JSON response (status=%d).", url, response.status_code
        )
        raise DeploymentCommunicationError(
            f"CPMS Server returned an unreadable response (status={response.status_code})."
        ) from exc

    if not response.ok:
        message = body.get("message") if isinstance(body, dict) else None
        logger.error("Deployment poll to %s rejected (status=%d): %s", url, response.status_code, message)
        raise DeploymentCommunicationError(
            message or f"Deployment poll rejected (status={response.status_code})."
        )

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("has_deployment"):
        logger.debug("Deployment poll to %s: no pending deployment.", url)
        return None

    deployment = data.get("deployment")
    if not isinstance(deployment, dict):
        raise DeploymentCommunicationError(
            "Server response indicated a pending deployment but omitted its details."
        )

    logger.info(
        "Deployment poll to %s: pending deployment target %s found.", url, deployment.get("target_id")
    )
    return deployment


def download_installer(
    target_id: str,
    destination_path: Path,
    *,
    server_url: str,
    api_key: str,
    timeout_seconds: float = 120.0,
) -> None:
    """
    Download the installer for deployment target ``target_id`` (FR-010)
    and stream it to ``destination_path``.

    Streams the response body directly to disk in fixed-size chunks
    rather than buffering the entire installer in memory, mirroring the
    server's own upload-time streaming approach
    (``backend.utils.file_storage.save_and_hash``).

    ``destination_path``'s parent directory is created if it does not
    already exist. If the write fails partway through, the partially
    written file is removed - a partial installer must never be left
    behind for ``agent.installer.checksum.verify_checksum`` or
    ``agent.installer.executor.execute_installer`` to act on.

    Raises ``DeploymentCommunicationError`` if the request cannot be sent,
    the server rejects it (e.g. the target does not belong to this
    client, is not currently downloadable, or its installer file is
    missing server-side), or the response cannot be written to disk.
    """
    url = f"{server_url.rstrip('/')}/api/agent/deployments/{target_id}/download"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds, stream=True)
    except requests.RequestException as exc:
        logger.error("Installer download from %s failed: %s", url, exc)
        raise DeploymentCommunicationError(f"Unable to reach CPMS Server at {url}: {exc}") from exc

    if not response.ok:
        message = None
        try:
            body = response.json()
            if isinstance(body, dict):
                message = body.get("message")
        except ValueError:
            pass
        logger.error(
            "Installer download from %s rejected (status=%d): %s", url, response.status_code, message
        )
        raise DeploymentCommunicationError(
            message or f"Installer download rejected (status={response.status_code})."
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination_path.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE_BYTES):
                if chunk:
                    output_file.write(chunk)
    except OSError as exc:
        destination_path.unlink(missing_ok=True)
        logger.error("Failed to write downloaded installer to %s: %s", destination_path, exc)
        raise DeploymentCommunicationError(f"Failed to save downloaded installer: {exc}") from exc
    finally:
        response.close()

    logger.info("Installer for target %s downloaded to %s.", target_id, destination_path)


__all__ = [
    "DeploymentCommunicationError",
    "poll_deployment",
    "download_installer",
]