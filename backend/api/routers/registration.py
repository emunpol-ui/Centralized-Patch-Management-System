"""
Client Registration router.

Implements ``POST /api/register`` exactly as named in PRS Appendix B
(FR-001 Client Registration).

--------------------------------------------------------------------------
DESIGN NOTE - why this endpoint is its own router, not added to
``backend/api/routers/agent.py``

``agent.py``'s ``APIRouter(dependencies=[Depends(require_client_api_key)])``
applies API-key authentication - by looking up an *already-registered*
``Client``'s ``api_key_hash`` - to every route on that router, present or
future, by design (see that file's own docstring). A brand-new Client
Agent's very first registration request cannot satisfy that dependency,
since no ``Client`` row exists for it yet (confirmed by
``CURRENT_STATE.md``'s "Notes for CLIENT-001's implementer": "registration
cannot go through ``require_client_api_key`` as currently written").

Rather than weakening ``agent.py``'s router-wide guarantee - which
AUTH-002 (a completed, do-not-redesign module) established specifically
so every current and future agent route is automatically protected -
this endpoint lives on its own router, matching the path PRS Appendix B
actually documents (``/api/register``, not ``/api/agent/register``) and
performing its own authentication inline via ``ClientAuthService.
resolve_registration_credential`` (see that method's docstring for the
full FR-001/FR-020 reasoning). ``agent.py`` itself is untouched by this
ticket.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, status

from backend.api.dependencies import (
    ClientAuthServiceDependency,
    ClientServiceDependency,
    DBSessionDependency,
    extract_bearer_token,
)
from backend.schemas.client import ClientRegistrationRequest
from backend.services.auth_service import AuthenticationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Client Registration"])


@router.post(
    "/api/register",
    status_code=status.HTTP_200_OK,
    summary="Client Agent registration",
    description=(
        "Register a new Client Agent, or refresh the registration details of an already-registered one "
        "(FR-001). Idempotent: repeated registration with the same Agent GUID updates the existing record "
        "rather than creating a duplicate."
    ),
)
async def register_client(
    payload: ClientRegistrationRequest,
    request: Request,
    response: Response,
    db: DBSessionDependency,
    client_auth_service: ClientAuthServiceDependency,
    client_service: ClientServiceDependency,
) -> Dict[str, Any]:
    """
    Register (or re-register) a Client Agent.

    Authenticates the presented ``Authorization: Bearer`` API key against
    either an existing ``Client`` or an unclaimed provisioning key (FR-020),
    then delegates the create-or-update decision to ``ClientService.register``
    (FR-001 steps 3-6). Returns ``201 Created`` for a brand-new client and
    ``200 OK`` for an idempotent update of an existing one.
    """
    raw_key = extract_bearer_token(request)
    if not raw_key:
        raise AuthenticationError("Not authenticated. Missing or malformed Authorization header.")

    credential = client_auth_service.resolve_registration_credential(db, raw_api_key=raw_key)

    client, created = client_service.register(
        db,
        credential=credential,
        agent_guid=payload.agent_guid,
        hostname=payload.hostname,
        logged_in_user=payload.logged_in_user,
        ip_address=payload.ip_address,
        operating_system=payload.operating_system,
        agent_version=payload.agent_version,
    )

    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

    return {
        "success": True,
        "message": "Client registered successfully." if created else "Client registration updated successfully.",
        "data": {
            "client_id": str(client.id),
            "agent_guid": str(client.agent_guid),
            "hostname": client.hostname,
            "status": client.status.value,
            "created": created,
        },
    }
