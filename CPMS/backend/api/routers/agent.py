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
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, status

from backend.api.dependencies import CurrentClient, require_client_api_key

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
