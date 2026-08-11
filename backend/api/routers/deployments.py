"""
Deployment management router (FR-008 Deployment Job Creation, FR-009
Deployment Job Retrieval targeting).

Implements the administrator-facing deployment creation endpoint (Backlog
DEPLOY-001 "Deployment creation API" deliverable): ``POST
/api/admin/deployments``. Grouped under ``/api/admin`` - consistent with
``backend/api/routers/repository.py`` and ``backend/api/routers/
updates.py`` - since this is an administrator-facing action belonging to
the SAD's "Deployment Management Module" (SAD Section 9.4, Section
10.10), not a Client Agent-facing endpoint. It is a state-changing
request, so it is protected by both an active administrator session
(``CurrentAdministrator``) and a valid CSRF token (``CSRFProtection``),
per NFR-028 - the same pattern already used by
``POST /api/admin/repository/packages``.

Deployment *retrieval by clients* (agent polling, DEPLOY-002), installer
download/execution (DEPLOY-003), and status reporting (DEPLOY-004) are all
Client Agent-facing and therefore live on
``backend/api/routers/agent.py`` instead - explicitly out of scope for
this router. A deployment-history *listing* endpoint remains out of scope
here as well (DASH-002 per the Backlog).

--------------------------------------------------------------------------
DEPLOY-004 ADDITION - ``POST /{target_id}/cancel``

Implements FR-021 Deployment Cancellation. PRS Appendix B documents this
endpoint's path as ``/api/deployments/{deployment_id}/cancel``; per the
design note at the top of ``backend/models/deployment.py`` (the PRS's
per-client "Deployment Jobs" row corresponds to this project's
``DeploymentTarget``, not the batch-level ``Deployment``), ``target_id``
here identifies a ``DeploymentTarget`` - the same identifier already
returned by DEPLOY-002's polling response and used by DEPLOY-003's
download endpoint - rather than a ``Deployment`` batch id. Grouped under
this router's existing ``/api/admin/deployments`` prefix, consistent with
``POST /api/admin/deployments`` (DEPLOY-001) above.

An administrator-facing, state-changing operation: protected by both an
active administrator session (``CurrentAdministrator``) and a valid CSRF
token (``CSRFProtection``), the same pattern already used by ``POST
/api/admin/deployments``, per NFR-028. A Client Agent has no ability to
cancel its own deployment - FR-021 is exclusively an administrator
capability.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, status

from backend.api.dependencies import (
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    DeploymentServiceDependency,
)
from backend.schemas.deployment import (
    DeploymentCancelResponse,
    DeploymentCreateRequest,
    DeploymentResponse,
    DeploymentTargetResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/deployments", tags=["Deployment Management"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a deployment batch",
    description=(
        "Create a new deployment batch, targeting one or more registered clients with a single "
        "approved repository package (FR-008). One DeploymentTarget record is created per targeted "
        "client, each initialized to Pending status (FR-009)."
    ),
)
async def create_deployment(
    request: DeploymentCreateRequest,
    db: DBSessionDependency,
    deployment_service: DeploymentServiceDependency,
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
) -> Dict[str, Any]:
    """
    Create a deployment batch (FR-008).

    Requires both an active administrator session and a valid CSRF token
    (NFR-028), since this is a state-changing request. All business
    validation (package approval status, target client existence, no
    duplicate active deployments) is performed by ``DeploymentService``;
    this handler only authenticates the request, delegates to the
    service, and shapes the response.
    """
    deployment = deployment_service.create_deployment(
        db,
        admin_id=current_admin.id,
        repository_package_id=request.repository_package_id,
        client_ids=request.client_ids,
    )

    targets = [DeploymentTargetResponse.model_validate(target) for target in deployment.targets]
    response = DeploymentResponse(
        id=deployment.id,
        repository_id=deployment.repository_id,
        created_by_admin_id=deployment.created_by_admin_id,
        created_at=deployment.created_at,
        targets=targets,
        target_count=len(targets),
    )

    logger.debug(
        "Administrator %s created deployment %s targeting %d client(s).",
        current_admin.id,
        deployment.id,
        response.target_count,
    )

    return {
        "success": True,
        "message": "Deployment created successfully.",
        "data": response.model_dump(mode="json"),
    }


@router.post(
    "/{target_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending deployment target",
    description=(
        "Cancel a single deployment target that is still Pending (FR-021). Once a Client Agent has "
        "retrieved the deployment (i.e. its status is no longer Pending), it is no longer eligible "
        "for cancellation through this endpoint."
    ),
)
async def cancel_deployment(
    target_id: UUID,
    db: DBSessionDependency,
    deployment_service: DeploymentServiceDependency,
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
) -> Dict[str, Any]:
    """
    Cancel a Pending deployment target (FR-021 Deployment Cancellation).

    Requires both an active administrator session and a valid CSRF token
    (NFR-028), since this is a state-changing request - the same pattern
    already used by ``create_deployment`` above. All business validation
    (target existence, current status must be Pending) is performed by
    ``DeploymentService.cancel_deployment_target``; this handler only
    authenticates the request, delegates to the service, and shapes the
    response.
    """
    updated = deployment_service.cancel_deployment_target(
        db,
        admin_id=current_admin.id,
        target_id=target_id,
    )

    response = DeploymentCancelResponse(
        target_id=updated.id,
        deployment_id=updated.deployment_id,
        status=updated.status,
    )

    logger.debug(
        "Administrator %s cancelled deployment target %s (deployment=%s).",
        current_admin.id,
        updated.id,
        updated.deployment_id,
    )

    return {
        "success": True,
        "message": "Deployment cancelled successfully.",
        "data": response.model_dump(mode="json"),
    }
