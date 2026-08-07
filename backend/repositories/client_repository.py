"""
Client repository.

Pure data-access layer for the ``Client`` entity, per the Repository
Pattern (SAD Section 5.4, Section 11).

CPM-002's ``backend/repositories/__init__.py`` deferred the full Client
repository to "the tickets that introduce their respective domains
(CLIENT-*...)". AUTH-002 added the single lookup method its own
deliverable ("API Key validation") required (``get_by_api_key_hash``).
CLIENT-001 extended the class with the creation, lookup-by-``agent_guid``,
and update operations FR-001 Client Registration requires. This ticket
(CLIENT-002) further extends it with ``update_heartbeat`` (FR-003) - per
AUTH-002's own note, methods are added here rather than in a second,
competing Client repository.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.client import Client
from backend.models.enums import ClientStatus


class ClientRepository:
    """Data-access operations for the ``clients`` table."""

    def get_by_id(self, db: Session, client_id: uuid.UUID) -> Client | None:
        """
        Return the ``Client`` with the given primary key, or ``None``.

        Added by INV-002 (FR-007 Software Version Comparison) so its
        administrator-facing endpoint can resolve a ``client_id`` path
        parameter to a real ``Client`` before comparing its inventory,
        the same "look up before acting" pattern used throughout this
        codebase (e.g. ``get_by_agent_guid``, ``get_by_api_key_hash``).
        Uses ``Session.get`` (primary-key lookup) rather than a ``select``
        statement, since ``id`` is always the table's primary key.
        """
        return db.get(Client, client_id)

    def get_by_api_key_hash(self, db: Session, api_key_hash: str) -> Client | None:
        """
        Return the ``Client`` whose ``api_key_hash`` matches, or ``None``.

        ``api_key_hash`` is unique (CPM-002), so at most one row can ever
        match.
        """
        stmt = select(Client).where(Client.api_key_hash == api_key_hash)
        return db.execute(stmt).scalar_one_or_none()

    def get_by_agent_guid(self, db: Session, agent_guid: uuid.UUID) -> Client | None:
        """
        Return the ``Client`` whose ``agent_guid`` matches, or ``None``.

        ``agent_guid`` is unique (CPM-002) and is the field FR-001
        mandates the server match re-registrations on - never hostname or
        IP address (see the design note on ``backend.models.client.Client``).
        """
        stmt = select(Client).where(Client.agent_guid == agent_guid)
        return db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        db: Session,
        *,
        agent_guid: uuid.UUID,
        api_key_hash: str,
        hostname: str,
        ip_address: str,
        operating_system: str,
        agent_version: str,
        status: ClientStatus = ClientStatus.UNKNOWN,
    ) -> Client:
        """Persist a brand-new ``Client`` record (first-time registration) and flush it."""
        client = Client(
            agent_guid=agent_guid,
            api_key_hash=api_key_hash,
            hostname=hostname,
            ip_address=ip_address,
            operating_system=operating_system,
            agent_version=agent_version,
            status=status,
        )
        db.add(client)
        db.flush()
        return client

    def update_registration(
        self,
        db: Session,
        client: Client,
        *,
        hostname: str,
        ip_address: str,
        operating_system: str,
        agent_version: str,
    ) -> Client:
        """
        Refresh the mutable registration fields of an already-registered
        ``Client`` (re-registration - FR-001 step 7).

        ``agent_guid`` and ``api_key_hash`` are deliberately not accepted
        here: they are the client's durable identity and are never
        rewritten by a routine re-registration. ``updated_at`` (inherited
        from ``AuditModel``) is refreshed automatically on flush/commit
        and serves as the "last registration timestamp".
        """
        client.hostname = hostname
        client.ip_address = ip_address
        client.operating_system = operating_system
        client.agent_version = agent_version
        db.add(client)
        db.flush()
        return client

    def update_heartbeat(self, db: Session, client: Client) -> Client:
        """
        Record a heartbeat for an already-registered ``Client`` (FR-003
        steps 2-4): stamp ``last_heartbeat`` with the current server time
        and mark ``status`` as ``ONLINE``.

        The timestamp is generated here, server-side, via
        ``datetime.now(timezone.utc)`` - the same pattern used by
        ``AdministratorSessionRepository`` for its own time-based fields -
        rather than accepting a caller-supplied value, per FR-003's own
        functional behavior ("The server records the current timestamp as
        the client's last heartbeat") and to avoid trusting a client's
        possibly-skewed or falsified clock.
        """
        client.last_heartbeat = datetime.now(timezone.utc)
        client.status = ClientStatus.ONLINE
        db.add(client)
        db.flush()
        return client