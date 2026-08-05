"""
Client authentication service.

Contains the business logic for authenticating CPMS Client Agent requests
using API keys (FR-002 Client Authentication). Together with
``backend.services.auth_service.AuthService`` (administrator sessions),
this implements the single "Authentication Module" the SAD describes as
covering FR-002, FR-019, and FR-020 (Section 9.4 Component Design). The
two are kept in separate classes/files - administrator session auth and
client API-key auth are different domains with no shared state or
lifecycle (SAD Section 10.14, "one service is responsible for one
business domain") - but share the same token-hashing primitives from
``backend.core.security`` and the same ``AuthenticationError`` response
shape.

--------------------------------------------------------------------------
SCOPING NOTE - FR-020 (Client API Key Provisioning) is not implemented
here, despite the Backlog listing FR-020 as this ticket's "Related
Requirement"

FR-020 describes an administrator generating and displaying a plaintext
API key *before* any Client row exists, to be handed to whoever installs
the Agent; FR-001's own precondition confirms the key must already exist
prior to registration ("The Client Agent possesses a valid API key issued
by the administrator (see FR-020)"). Implementing that "pending,
not-yet-claimed key" workflow properly would require either:

    (a) a new table for provisioned-but-unclaimed keys, whose "claiming"
        step only makes sense as part of FR-001 Client Registration
        (CLIENT-001, an explicitly out-of-scope future ticket), or
    (b) relaxing `Client`'s existing NOT NULL columns (hostname,
        agent_guid, etc.) to allow a "shell" row before registration -
        a redesign of CPM-002's completed schema, which this ticket's own
        instructions prohibit absent a genuine integration need.

FR-002 (Client Authentication), by contrast, explicitly assumes
registration has *already* happened: its own preconditions state "The
Client Agent has completed the registration process. A valid API key has
been issued and configured." This matches AUTH-002's actual literal
deliverables ("API Key validation, Client authentication middleware,
Authentication dependency") and acceptance criteria ("valid/invalid
clients accepted/rejected") far more directly than FR-020's provisioning
concern does.

This ticket therefore implements FR-002 in full (validating an API key
against an already-registered ``Client`` row) and leaves FR-020's
issuance workflow to be introduced together with FR-001/CLIENT-001, where
the "pending key" and "registration" halves of that workflow naturally
belong together. See ``scripts/dev_seed_client.py`` for how this ticket's
own testing need for a registered client-with-a-known-key is met in the
interim.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.security import hash_token
from backend.models.client import Client
from backend.models.enums import AuditSeverity
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.client_repository import ClientRepository
from backend.services.auth_service import AuthenticationError


class ClientAuthService:
    """
    Client Agent API-key authentication.

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(
        self,
        client_repository: ClientRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._clients = client_repository or ClientRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def authenticate(self, db: Session, *, raw_api_key: str) -> Client:
        """
        Resolve a raw API key (from the ``Authorization: Bearer`` header,
        per PRS Appendix B "Standard Request Headers") to its ``Client``.

        Raises ``AuthenticationError`` (401) if the key does not match any
        registered client (covers FR-002's "invalid," "not recognized,"
        and - since there is currently no separate revocation flag on
        ``Client`` - "revoked" error conditions alike; a key stops working
        the moment it no longer matches a client's stored hash).

        Unlike administrator login (FR-019, which explicitly requires
        logging *both* successful and failed attempts), FR-002's own
        acceptance criteria requires only that "authentication failures
        are recorded in the audit log." Client requests (heartbeats,
        deployment polling) are expected to be frequent - routinely
        auditing every successful one would flood the audit trail with
        routine traffic rather than security-relevant events, so only
        failures are recorded here.
        """
        client = self._clients.get_by_api_key_hash(db, hash_token(raw_api_key))
        if client is None:
            self._audit_logs.create(
                db,
                event_type="CLIENT_AUTH_FAILURE",
                severity=AuditSeverity.WARNING,
                description="Client authentication failed: API key did not match any registered client.",
            )
            db.commit()
            raise AuthenticationError("Invalid API key.")

        return client
