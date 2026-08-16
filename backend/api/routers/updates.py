"""
Version comparison router (FR-007 Software Version Comparison).

Exposes the administrator-facing "available updates" endpoint (Backlog
UPDATE-001 "Available updates endpoint" deliverable), which compares a
registered client's installed software inventory (INV-001) against the
approved repository catalog and reports each item's update status
(Up-to-Date / Update Available / Not Managed).

Grouped under ``/api/admin`` - like ``backend/api/routers/auth.py`` -
since this is an administrator-facing, session-protected read operation
belonging to the SAD's "Dashboard Module" / "Inventory Management Module"
(SAD Section 9.4, Section 10.8), not a Client Agent-facing endpoint
(contrast with ``backend/api/routers/agent.py``, whose router-wide
``dependencies=[Depends(require_client_api_key)]`` this router does not
use). This is a read-only endpoint, so - unlike the state-changing routes
in ``auth.py`` - no CSRF token is required: NFR-028 scopes CSRF
enforcement to "state-changing dashboard requests", and comparing
inventory changes no server state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, status

from backend.api.dependencies import (
    CurrentAdministrator,
    DBSessionDependency,
    VersionComparisonServiceDependency,
)
from backend.services.client_service import ClientNotFoundError
from backend.core.exceptions import AppException
from backend.models.enums import UpdateStatus
from backend.repositories.client_repository import ClientRepository
from backend.schemas.updates import ClientUpdateStatusSummary, SoftwareUpdateStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Version Comparison"])

# A plain, stateless repository instance, constructed once at import time -
# consistent with how this router's own read-only lookup needs are met
# elsewhere in this codebase without a dedicated DI factory (repositories
# are otherwise only ever instantiated inside a service's constructor).
_client_repository = ClientRepository()



@router.get(
    "/clients/{client_id}/updates",
    status_code=status.HTTP_200_OK,
    summary="Compare a client's software inventory against the repository",
    description=(
        "Compare every installed software item reported by the specified client (INV-001) against the "
        "approved repository catalog (FR-007), classifying each item as Up-to-Date, Update Available, "
        "or Not Managed."
    ),
)
async def get_client_updates(
    client_id: UUID,
    db: DBSessionDependency,
    comparison_service: VersionComparisonServiceDependency,
    _current_admin: CurrentAdministrator,
) -> Dict[str, Any]:
    """
    Return FR-007 version comparison results for every software item
    installed on the specified client.

    Requires an active administrator session (``CurrentAdministrator``);
    this mirrors the "protected route" pattern already established by
    ``backend/api/routers/auth.py``'s ``GET /api/admin/me``. Raises
    ``ClientNotFoundError`` (404) if ``client_id`` does not match any
    registered ``Client`` - this endpoint is scoped to a single, existing
    client rather than silently returning an empty result for an unknown
    ID, since an administrator following a dashboard link should see a
    clear "not found" rather than an ambiguous empty list.
    """
    client = _client_repository.get_by_id(db, client_id)
    if client is None:
        raise ClientNotFoundError(client_id)

    results = comparison_service.compare_client_inventory(db, client_id=client.id)
    items = [SoftwareUpdateStatusResponse.model_validate(item) for item in results]

    summary = ClientUpdateStatusSummary(
        up_to_date=sum(1 for item in results if item.status == UpdateStatus.UP_TO_DATE),
        update_available=sum(1 for item in results if item.status == UpdateStatus.UPDATE_AVAILABLE),
        not_managed=sum(1 for item in results if item.status == UpdateStatus.NOT_MANAGED),
        total=len(results),
    )

    logger.debug(
        "Administrator %s requested version comparison for client %s (%d item(s)).",
        _current_admin.id,
        client.id,
        summary.total,
    )

    return {
        "success": True,
        "message": "Version comparison computed.",
        "data": {
            "client_id": str(client.id),
            "hostname": client.hostname,
            "summary": summary.model_dump(),
            "items": [item.model_dump(mode="json") for item in items],
        },
    }
