"""
Client Agent router.

Establishes the protected namespace future Client Agent-facing endpoints
(FR-001 registration, FR-003 heartbeat, FR-005 inventory upload, FR-009
deployment polling, FR-010 installer download, FR-012 status reporting -
CLIENT-*, INV-*, DEPLOY-* tickets) will be added to.

The ``dependencies=[Depends(require_client_api_key)]`` argument below
applies API-key authentication to *every* route registered on this
router, present or future, centrally and automatically - this is how
AUTH-002's "Client authentication middleware" deliverable is realized:
a single, reusable enforcement point covering all agent endpoints (this
ticket's acceptance criterion), implemented via this project's
established Dependency Injection architecture (SAD Section 5.6) rather
than a second, parallel ASGI-middleware mechanism alongside it. See the
docstring on ``require_client_api_key`` (backend/api/dependencies.py) for
the full reasoning.

``GET /ping`` is this ticket's own demonstration/verification endpoint -
analogous to CPM-001's ``/api/health`` and AUTH-001's ``/api/admin/me`` -
proving the mechanism works end-to-end ("valid clients accepted, invalid
clients rejected") ahead of any real agent functionality existing. It is
not a PRS-documented endpoint.

--------------------------------------------------------------------------
CLIENT-002 ADDITION - ``POST /heartbeat``

Implements FR-003 Client Heartbeat (PRS Appendix B: ``/api/heartbeat``).
Added directly to this existing router - per this router's own docstring
above, every route declared here automatically inherits API-key
authentication via the router-wide ``dependencies=[Depends(require_client_
api_key)]`` - rather than a new router, since a heartbeat is a routine
authenticated request from an *already-registered* client (unlike
``POST /api/register``, which cannot use this router - see
``backend/api/routers/registration.py``). Business logic lives in
``backend.services.heartbeat_service.HeartbeatService``, per the Service
Layer Pattern; this handler stays thin (parse request, call service,
shape response), consistent with every other router in this codebase.
--------------------------------------------------------------------------

--------------------------------------------------------------------------
INV-001 ADDITION - ``POST /inventory/upload``

Implements FR-005 Software Inventory Upload. PRS Appendix B documents this
endpoint's path as ``/api/inventory/upload``; consistent with the path
convention CLIENT-002 already established for ``/api/heartbeat`` above
(centralizing every authenticated, already-registered-client endpoint
under this router's ``/api/agent`` prefix so it automatically inherits
router-wide API-key authentication), it is added here as
``/api/agent/inventory/upload`` rather than as a literal, separate
``/api/inventory/upload`` route. Business logic lives in
``backend.services.inventory_service.InventoryService``, per the Service
Layer Pattern; this handler stays thin, consistent with every other route
on this router.
--------------------------------------------------------------------------

--------------------------------------------------------------------------
DEPLOY-002 ADDITION - ``GET /deployments/poll``

Implements FR-009 Deployment Job Retrieval (Client Polling). PRS Appendix
B documents this endpoint's path as ``/api/deployments/poll``; consistent
with the path convention this router already established for
``/api/agent/heartbeat`` (CLIENT-002) and ``/api/agent/inventory/upload``
(INV-001) - centralizing every authenticated, already-registered-client
endpoint under this router's ``/api/agent`` prefix so it automatically
inherits router-wide API-key authentication - it is added here as
``/api/agent/deployments/poll`` rather than as a literal, separate
``/api/deployments/poll`` route.

The authenticated ``current_client`` (never a client id read from the
request) is the sole source of the polling identity, per this ticket's
"Client Isolation" requirement - see ``backend.services.deployment_service
.DeploymentService.poll_pending_deployment`` and
``backend.repositories.deployment_repository.DeploymentRepository.
get_pending_target_for_client`` for where that scoping is actually
enforced. Business logic (including the documented decision not to
transition ``DeploymentTarget.status`` on poll) lives entirely in
``DeploymentService``; this handler only authenticates, delegates, and
shapes the response, consistent with every other route on this router.

Reuses the existing ``Deployment``/``DeploymentTarget`` models,
``DeploymentRepository``, and ``DeploymentService`` introduced by
DEPLOY-001 - no new models or a second deployment repository/service were
created. Installer download, checksum verification, silent installation,
and status reporting remain out of scope (DEPLOY-003/DEPLOY-004).
--------------------------------------------------------------------------

--------------------------------------------------------------------------
DEPLOY-003 ADDITION - ``GET /deployments/{target_id}/download``

Implements FR-010 Installer Download. PRS Appendix B documents this
endpoint's path as ``/api/download/{deploymentId}``; consistent with the
path convention this router already established for
``/api/agent/deployments/poll`` (DEPLOY-002) - centralizing every
authenticated, already-registered-client endpoint under this router's
``/api/agent`` prefix - it is added here as
``/api/agent/deployments/{target_id}/download`` rather than as a literal,
separate ``/api/download/{deploymentId}`` route. ``target_id`` is this
client's own ``DeploymentTarget.id`` (the PRS's per-client "Deployment
ID"), the same identifier already returned by DEPLOY-002's
``GET /deployments/poll`` response.

As with polling, the authenticated ``current_client`` (never a client id
read from the request) is the sole source of the authorization identity -
see ``backend.services.deployment_service.DeploymentService.
prepare_installer_download`` and ``backend.repositories.deployment_repository
.DeploymentRepository.get_target_for_client`` for where that scoping is
actually enforced. This handler only authenticates, delegates, and streams
the resulting file back to the caller - it performs no authorization or
filesystem logic itself.

Checksum verification (FR-011: "the Client Agent computes the SHA-256
checksum of the downloaded installer file and compares it to the checksum
provided by the server") and silent installation both happen entirely on
the Client Agent side, using the ``checksum`` and ``silent_command``
already returned by DEPLOY-002's polling response - this endpoint's only
job is to transmit the installer bytes. Deployment status reporting
(FR-012) remains out of scope (DEPLOY-004).
--------------------------------------------------------------------------

--------------------------------------------------------------------------
DEPLOY-004 ADDITION - ``POST /deployments/{target_id}/status``

Implements FR-012 Deployment Status Reporting. PRS Appendix B documents
this endpoint's path as ``/api/deployment/status`` (no path parameter);
consistent with the path convention this router already established for
``/api/agent/deployments/poll`` (DEPLOY-002) and
``/api/agent/deployments/{target_id}/download`` (DEPLOY-003) -
centralizing every authenticated, already-registered-client endpoint
under this router's ``/api/agent`` prefix, and identifying the target
deployment via the same ``target_id`` path parameter DEPLOY-003 already
introduced - it is added here as
``/api/agent/deployments/{target_id}/status`` rather than as a literal,
separate ``/api/deployment/status`` route.

As with polling and download, the authenticated ``current_client`` (never
a client id read from the request) is the sole source of the
authorization identity - see
``backend.services.deployment_service.DeploymentService.report_status``
and ``backend.repositories.deployment_repository.DeploymentRepository.
get_target_for_client`` for where that scoping is actually enforced.
This handler only authenticates, delegates, and shapes the response - all
status-transition validation, ``completion_time``/exit-code/error-message
persistence, and audit logging happen inside ``DeploymentService.
report_status``.

Deployment cancellation (FR-021) is an administrator-facing operation and
therefore lives on ``backend/api/routers/deployments.py``, not here - a
Client Agent has no ability to cancel its own deployment.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from backend.api.dependencies import (
    CurrentClient,
    DBSessionDependency,
    DeploymentServiceDependency,
    HeartbeatServiceDependency,
    InventoryServiceDependency,
    SettingsDependency,
    require_client_api_key,
)
from backend.schemas.deployment import (
    DeploymentPollPackageDetail,
    DeploymentPollResponse,
    DeploymentPollTargetResponse,
    DeploymentStatusReportRequest,
    DeploymentTargetStatusResponse,
)
from backend.schemas.heartbeat import HeartbeatRequest
from backend.schemas.inventory import InventoryUploadRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/agent",
    tags=["Client Agent"],
    dependencies=[Depends(require_client_api_key)],
)


@router.get(
    "/ping",
    status_code=status.HTTP_200_OK,
    summary="Client Agent authentication check",
    description=(
        "Verifies that the presented API key authenticates successfully. "
        "Demonstrates the 'protected route' mechanism required by AUTH-002."
    ),
)
async def ping(current_client: CurrentClient) -> Dict[str, Any]:
    """Return the identity of the authenticated Client Agent."""
    logger.debug("Agent ping from client %s (%s).", current_client.id, current_client.hostname)
    return {
        "success": True,
        "message": "Authenticated.",
        "data": {
            "client_id": str(current_client.id),
            "hostname": current_client.hostname,
            "status": current_client.status.value,
        },
    }


@router.post(
    "/heartbeat",
    status_code=status.HTTP_200_OK,
    summary="Client Agent heartbeat",
    description=(
        "Record that the authenticated Client Agent remains online (FR-003). Updates the client's "
        "last-heartbeat timestamp and marks its status as Online. Idempotent: repeated calls simply "
        "refresh the timestamp and keep the client marked Online."
    ),
)
async def heartbeat(
    current_client: CurrentClient,
    db: DBSessionDependency,
    heartbeat_service: HeartbeatServiceDependency,
    payload: HeartbeatRequest = HeartbeatRequest(),
) -> Dict[str, Any]:
    """
    Record a heartbeat for the authenticated Client Agent.

    ``current_client`` is resolved (and thus already validated as a
    registered, authenticated client - see ``require_client_api_key`` and
    ``HeartbeatService``'s module docstring) before this handler body
    runs. ``payload`` carries no fields (see ``backend.schemas.heartbeat``)
    but is still declared and defaulted so a malformed request body is
    rejected by Pydantic (422) rather than silently ignored.
    """
    del payload  # No fields to consume; presence-only validation (see schema docstring).
    updated = heartbeat_service.record_heartbeat(db, client=current_client)
    return {
        "success": True,
        "message": "Heartbeat recorded.",
        "data": {
            "client_id": str(updated.id),
            "hostname": updated.hostname,
            "status": updated.status.value,
            "last_heartbeat": updated.last_heartbeat.isoformat() if updated.last_heartbeat else None,
        },
    }


@router.post(
    "/inventory/upload",
    status_code=status.HTTP_200_OK,
    summary="Upload software inventory",
    description=(
        "Upload the authenticated Client Agent's current software inventory (FR-005). The uploaded "
        "list is treated as the client's complete, current inventory snapshot: software not already "
        "on record is added, software already on record is refreshed, and previously recorded "
        "software absent from this upload is removed (see InventoryService for the full rationale)."
    ),
)
async def upload_inventory(
    current_client: CurrentClient,
    db: DBSessionDependency,
    inventory_service: InventoryServiceDependency,
    payload: InventoryUploadRequest,
) -> Dict[str, Any]:
    """
    Persist a software inventory upload for the authenticated Client Agent.

    ``current_client`` is resolved (and thus already authenticated - see
    ``require_client_api_key``) before this handler body runs. ``payload``
    is validated by Pydantic (``InventoryUploadRequest`` - required field
    lengths/types, per FR-005's "the server validates the inventory
    format" step) before this handler is even invoked. All business logic
    - matching, inserting, updating, removing, and audit logging - lives
    in ``InventoryService.upload_inventory``.
    """
    result = inventory_service.upload_inventory(db, client=current_client, items=payload.items)
    return {
        "success": True,
        "message": "Inventory uploaded successfully.",
        "data": {
            "client_id": str(current_client.id),
            "record_count": result.total,
            "created": result.created,
            "updated": result.updated,
            "removed": result.removed,
        },
    }


@router.get(
    "/deployments/poll",
    status_code=status.HTTP_200_OK,
    summary="Poll for a pending deployment",
    description=(
        "Retrieve the authenticated Client Agent's own pending deployment job, if any (FR-009). "
        "Scoped strictly to the authenticated client - a client can never retrieve another client's "
        "deployment. Read-only: does not download the installer, verify its checksum, execute it, or "
        "change the deployment's status (see DEPLOY-003/DEPLOY-004 for those steps)."
    ),
)
async def poll_deployment(
    current_client: CurrentClient,
    db: DBSessionDependency,
    deployment_service: DeploymentServiceDependency,
) -> Dict[str, Any]:
    """
    Return the authenticated Client Agent's own pending deployment target,
    if one exists (FR-009 Deployment Job Retrieval).

    ``current_client`` - resolved and authenticated by
    ``require_client_api_key`` before this handler body runs - is the
    *only* source of the polling identity passed to
    ``DeploymentService.poll_pending_deployment``. No client id is ever
    accepted from request input for this purpose, which is what
    guarantees the "a client must never be able to retrieve another
    client's deployment" requirement holds.

    Returns ``has_deployment: false`` (still ``200 OK``) rather than a
    ``404`` when nothing is pending - "no work to do right now" is a
    routine, expected polling outcome for a Client Agent (FR-009
    Alternative Flow), not an error.
    """
    target = deployment_service.poll_pending_deployment(db, client=current_client)

    if target is None:
        response = DeploymentPollResponse(has_deployment=False, deployment=None)
        return {
            "success": True,
            "message": "No pending deployment.",
            "data": response.model_dump(mode="json"),
        }

    package = target.deployment.repository_package
    response = DeploymentPollResponse(
        has_deployment=True,
        deployment=DeploymentPollTargetResponse(
            target_id=target.id,
            deployment_id=target.deployment_id,
            status=target.status,
            created_at=target.created_at,
            package=DeploymentPollPackageDetail.model_validate(package),
        ),
    )
    return {
        "success": True,
        "message": "Pending deployment found.",
        "data": response.model_dump(mode="json"),
    }


@router.get(
    "/deployments/{target_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download an assigned installer",
    description=(
        "Download the installer package for one of the authenticated Client Agent's own deployment "
        "targets (FR-010). Scoped strictly to the authenticated client - a client can never download "
        "another client's installer, even by guessing/enumerating target ids. The Client Agent must "
        "verify the downloaded file's SHA-256 checksum against the value already provided by "
        "GET /deployments/poll (DEPLOY-002) before executing it (FR-011); this endpoint only "
        "transmits the installer bytes."
    ),
)
async def download_installer(
    target_id: UUID,
    current_client: CurrentClient,
    db: DBSessionDependency,
    deployment_service: DeploymentServiceDependency,
    settings: SettingsDependency,
) -> FileResponse:
    """
    Stream the installer file for ``target_id`` back to the authenticated
    Client Agent (FR-010 Installer Download).

    ``current_client`` - resolved and authenticated by
    ``require_client_api_key`` before this handler body runs - is the
    *only* source of the authorization identity passed to
    ``DeploymentService.prepare_installer_download``; ``target_id`` alone
    (a value the requesting client supplies) is never trusted as an
    authorization boundary by itself - see that method and
    ``DeploymentRepository.get_target_for_client`` for where client
    isolation is actually enforced (this ticket's "Client Isolation"
    requirement).

    All validation (target ownership, downloadable status, installer file
    presence on disk) and audit logging happen inside
    ``DeploymentService.prepare_installer_download``; if it raises, the
    application's global ``AppException`` handler (see
    ``backend.core.exceptions``) converts it into the standard JSON error
    envelope before any file response is ever constructed. On success,
    the installer is streamed directly from the repository directory -
    this handler never loads the file into memory itself.
    """
    _target, installer_path = deployment_service.prepare_installer_download(
        db,
        client=current_client,
        target_id=target_id,
        repository_dir=settings.repository_path,
    )
    return FileResponse(
        path=installer_path,
        media_type="application/octet-stream",
        filename=installer_path.name,
    )


@router.post(
    "/deployments/{target_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Report deployment progress or a final result",
    description=(
        "Report a status transition for one of the authenticated Client Agent's own deployment "
        "targets (FR-012): 'Downloading' when installer download begins, 'Installing' when silent "
        "installation begins, and 'Completed'/'Failed' for the final outcome. Scoped strictly to the "
        "authenticated client - a client can never report status for another client's deployment. "
        "Only legal forward transitions from the target's current status are accepted; terminal "
        "outcomes (Completed/Failed/Cancelled) can never be overwritten."
    ),
)
async def report_deployment_status(
    target_id: UUID,
    current_client: CurrentClient,
    db: DBSessionDependency,
    deployment_service: DeploymentServiceDependency,
    payload: DeploymentStatusReportRequest,
) -> Dict[str, Any]:
    """
    Record a status transition reported by the authenticated Client Agent
    (FR-012 Deployment Status Reporting).

    ``current_client`` - resolved and authenticated by
    ``require_client_api_key`` before this handler body runs - is the
    *only* source of the authorization identity passed to
    ``DeploymentService.report_status``; ``target_id`` alone (a value the
    requesting client supplies) is never trusted as an authorization
    boundary by itself, mirroring DEPLOY-002/DEPLOY-003's existing Client
    Isolation pattern. ``payload`` is validated by Pydantic
    (``DeploymentStatusReportRequest`` - only client-reportable statuses,
    ``error_message`` required for ``Failed``) before this handler is even
    invoked; the Service Layer re-validates the same rules plus the
    target's current-status transition legality, since it is this
    project's authoritative validation boundary.
    """
    updated = deployment_service.report_status(
        db,
        client=current_client,
        target_id=target_id,
        status=payload.status,
        exit_code=payload.exit_code,
        error_message=payload.error_message,
    )
    response = DeploymentTargetStatusResponse(
        target_id=updated.id,
        deployment_id=updated.deployment_id,
        status=updated.status,
        completion_time=updated.completion_time,
        exit_code=updated.exit_code,
        error_message=updated.error_message,
    )
    return {
        "success": True,
        "message": "Deployment status recorded.",
        "data": response.model_dump(mode="json"),
    }