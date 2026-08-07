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
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, status

from backend.api.dependencies import (
    CurrentClient,
    DBSessionDependency,
    HeartbeatServiceDependency,
    require_client_api_key,
)
from backend.schemas.heartbeat import HeartbeatRequest

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