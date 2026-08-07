"""
Heartbeat service.

Contains the business logic behind Client Agent heartbeat processing
(FR-003 Client Heartbeat), per the Service Layer Pattern (SAD Section
5.5, Section 10.7 "Heartbeat Service"). The SAD documents Heartbeat
Service as its own component, distinct from Client Service (Section
10.4's service list; Section 9.6's module breakdown), so this ticket
(CLIENT-002) introduces it as a separate class rather than folding one
more responsibility into ``ClientService`` - consistent with "one service
is responsible for one business domain" (SAD Section 10.14).

--------------------------------------------------------------------------
DESIGN NOTE - why there is no "client not found" / "unknown client" branch
here

FR-003's own preconditions state "The Client Agent has successfully
registered" and "The Client Agent has a valid API key". By the time a
request reaches this service, ``require_client_api_key``
(``backend/api/dependencies.py``, AUTH-002) has already resolved the
presented ``Authorization: Bearer`` key to an existing, registered
``Client`` row - an unrecognized or missing key is rejected with 401
(and audit-logged as ``CLIENT_AUTH_FAILURE`` by
``ClientAuthService.authenticate``) before this service is ever invoked.
There is therefore no "authenticated but unregistered" state left for
this service to additionally guard against; the CLIENT-002 acceptance
criteria "Authentication enforced" and "unknown clients handled
gracefully" are satisfied entirely by the already-completed AUTH-002
mechanism this service composes with, not by new logic here.

--------------------------------------------------------------------------
DESIGN NOTE - why a successful heartbeat is not written to the audit log

Mirroring ``ClientAuthService.authenticate``'s own documented rationale:
heartbeats are frequent, routine traffic (unlike, e.g., FR-001
registration or FR-020 key issuance, which are rare, higher-value
events). Auditing every single heartbeat would flood the audit trail
with noise rather than security-relevant signal, so only the Python
application log (this module's ``logger``) records each one. This
matches CURRENT_STATE.md's Logging Standards table, which already
anticipated this ticket ("Client Registration (not yet implemented)"
etc. are listed as *application*-log events; client authentication
*failures* are the only client-related event documented as
audit-logged).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.models.client import Client
from backend.repositories.client_repository import ClientRepository

logger = logging.getLogger(__name__)


class HeartbeatService:
    """
    Client Agent heartbeat processing (FR-003).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(self, client_repository: ClientRepository | None = None) -> None:
        self._clients = client_repository or ClientRepository()

    def record_heartbeat(self, db: Session, *, client: Client) -> Client:
        """
        Record a heartbeat for ``client`` (FR-003 functional behavior
        steps 2-4: authenticate, record timestamp, update status).

        ``client`` must already be the authenticated, registered ``Client``
        resolved by ``require_client_api_key`` - see the module docstring
        for why no additional existence check is performed here.

        Idempotent by construction: repeated calls simply overwrite
        ``last_heartbeat`` with the current time and re-assert ``ONLINE``
        status, matching CLIENT-002's "the endpoint should be idempotent"
        requirement without any special-casing.
        """
        updated = self._clients.update_heartbeat(db, client)
        db.commit()
        logger.info(
            "Heartbeat recorded for client %s (%s); status=ONLINE, last_heartbeat=%s.",
            updated.id,
            updated.hostname,
            updated.last_heartbeat.isoformat() if updated.last_heartbeat else None,
        )
        return updated