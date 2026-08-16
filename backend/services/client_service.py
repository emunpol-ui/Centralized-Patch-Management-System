"""
Client service.

Contains the business logic for Client Agent registration (FR-001), per
the Service Layer Pattern (SAD Section 5.5, Section 10.6 "Client
Service"). Coordinates the Client and ClientProvisioningKey repositories
and the Audit Log repository; enforces no rules beyond what FR-001
requires.

Authentication concerns (resolving whether a presented API key is
legitimate, and what it represents) belong to ``ClientAuthService`` - see
that module's "CLIENT-001 ADDITION" note for why FR-001 needs a second,
FR-020-aware resolution path alongside AUTH-002's ``authenticate()``.
This service consumes the already-resolved ``RegistrationCredential`` and
is responsible only for the create-or-update decision described in FR-001
step 3-6: "Search for an existing client using Agent GUID... If not
found, create... If found, update...".
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session


from backend.core.exceptions import AppException
from backend.models.client import Client
from backend.models.enums import AuditSeverity, ClientStatus
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.client_provisioning_key_repository import ClientProvisioningKeyRepository
from backend.repositories.client_repository import ClientRepository
from backend.services.client_auth_service import RegistrationCredential

logger = logging.getLogger(__name__)


class ClientRegistrationConflictError(AppException):
    """
    Raised when a registration request's Agent GUID and presented API key
    do not consistently identify the same client (FR-001's uniqueness/
    idempotency rules - see ``ClientService.register`` for the two
    specific scenarios this guards against).
    """

    def __init__(self, message: str = "Client registration conflict.", status_code: int = 409) -> None:
        super().__init__(message, status_code=status_code)
class ClientNotFoundError(AppException):
    """Raised when a requested client does not exist."""

    def __init__(
        self,
        client_id: uuid.UUID,
        status_code: int = 404,
    ) -> None:
        super().__init__(
            f"Client '{client_id}' was not found.",
            status_code=status_code,
        )

class ClientService:
    """
    Client Agent registration (FR-001).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(
        self,
        client_repository: ClientRepository | None = None,
        provisioning_key_repository: ClientProvisioningKeyRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._clients = client_repository or ClientRepository()
        self._provisioning_keys = provisioning_key_repository or ClientProvisioningKeyRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def register(
        self,
        db: Session,
        *,
        credential: RegistrationCredential,
        agent_guid: uuid.UUID,
        hostname: str,
        logged_in_user: str | None,
        ip_address: str,
        operating_system: str,
        agent_version: str,
    ) -> tuple[Client, bool]:
        """
        Create or update a ``Client`` record for a registration request
        (FR-001), given the already-authenticated ``credential``.

        Returns ``(client, created)`` where ``created`` is ``True`` only
        when a brand-new ``Client`` row was inserted.

        The Agent GUID is the sole key used to decide create-vs-update
        (FR-001: "the server shall use the Agent GUID - not hostname or IP
        address - to determine whether a client already exists"). The
        resolved ``credential`` is then used purely as an authorization
        check on top of that decision, guarding two conflict scenarios
        that must never silently overwrite data:

            1. An Agent GUID already belongs to a registered ``Client``,
               but the presented key belongs to a *different* client (or
               is an unclaimed provisioning key). Rejected - a key must
               not be able to update a client it does not own.
            2. An Agent GUID is not yet registered, but the presented key
               already belongs to a *different, existing* client (i.e. it
               is not an unclaimed provisioning key). Rejected - one
               issued key must not be able to spawn a second client
               identity.
        """
        existing_by_guid = self._clients.get_by_agent_guid(db, agent_guid)

        if existing_by_guid is not None:
            if credential.existing_client is None or credential.existing_client.id != existing_by_guid.id:
                self._log_conflict(
                    db,
                    description=(
                        f"Registration rejected: Agent GUID {agent_guid} is already registered to a "
                        "different client than the one identified by the presented API key."
                    ),
                    client_id=existing_by_guid.id,
                )
                raise ClientRegistrationConflictError(
                    "This Agent GUID is already registered under a different API key."
                )

            updated = self._clients.update_registration(
                db,
                existing_by_guid,
                hostname=hostname,
                logged_in_user=logged_in_user,
                ip_address=ip_address,
                operating_system=operating_system,
                agent_version=agent_version,
            )
            self._audit_logs.create(
                db,
                event_type="CLIENT_REGISTRATION_UPDATED",
                severity=AuditSeverity.INFO,
                description=f"Client '{hostname}' (agent_guid={agent_guid}) re-registered; details updated.",
                client_id=updated.id,
            )
            db.commit()
            logger.info("Client %s (%s) re-registered; registration details updated.", updated.id, hostname)
            return updated, False

        if credential.provisioning_key is None:
            self._log_conflict(
                db,
                description=(
                    f"Registration rejected: the presented API key is already assigned to a different "
                    f"client and cannot register new Agent GUID {agent_guid}."
                ),
                client_id=credential.existing_client.id if credential.existing_client else None,
            )
            raise ClientRegistrationConflictError(
                "This API key is already assigned to a different client."
            )

        new_client = self._clients.create(
            db,
            agent_guid=agent_guid,
            api_key_hash=credential.provisioning_key.key_hash,
            hostname=hostname,
            logged_in_user=logged_in_user,
            ip_address=ip_address,
            operating_system=operating_system,
            agent_version=agent_version,
            status=ClientStatus.UNKNOWN,
        )
        self._provisioning_keys.delete(db, credential.provisioning_key)
        self._audit_logs.create(
            db,
            event_type="CLIENT_REGISTERED",
            severity=AuditSeverity.INFO,
            description=f"New client '{hostname}' (agent_guid={agent_guid}) registered successfully.",
            client_id=new_client.id,
        )
        db.commit()
        logger.info("New client %s (%s) registered successfully.", new_client.id, hostname)
        return new_client, True

    
    def delete_client(
        self,
        db: Session,
        client_id: uuid.UUID,
    ) -> None:
        """
        Delete a registered client and preserve an audit trail.
        """

        client = self._clients.get_by_id(db, client_id)

        if client is None:
            raise ClientNotFoundError(client_id)

        hostname = client.hostname

        # Create audit record BEFORE deleting the client.
        self._audit_logs.create(
            db,
            event_type="CLIENT_DELETED",
            severity=AuditSeverity.WARNING,
            description=(
                f"Client '{hostname}' (client_id={client_id}) "
                "was deleted by an administrator."
            ),
            client_id=client_id,
        )

        # Now delete the client. The FK's ON DELETE SET NULL
        # will preserve the audit row while clearing client_id.
        self._clients.delete(db, client)

        db.commit()

        logger.info(
            "Client %s (%s) deleted successfully.",
            client_id,
            hostname,
        )





    def _log_conflict(self, db: Session, *, description: str, client_id: uuid.UUID | None) -> None:
        self._audit_logs.create(
            db,
            event_type="CLIENT_REGISTRATION_CONFLICT",
            severity=AuditSeverity.WARNING,
            description=description,
            client_id=client_id,
        )
        db.commit()
        logger.warning(description)
