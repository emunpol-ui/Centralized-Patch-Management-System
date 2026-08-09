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
download/execution (DEPLOY-003), status reporting (DEPLOY-004), a
deployment-history listing endpoint, and deployment cancellation are all
explicitly out of scope for this router in this ticket.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, status

from backend.api.dependencies import (
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    DeploymentServiceDependency,
)
from backend.schemas.deployment import DeploymentCreateRequest, DeploymentResponse, DeploymentTargetResponse

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
