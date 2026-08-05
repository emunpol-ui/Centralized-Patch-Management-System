"""
Client repository.

Pure data-access layer for the ``Client`` entity, per the Repository
Pattern (SAD Section 5.4, Section 11).

CPM-002's ``backend/repositories/__init__.py`` deferred the full Client
repository to "the tickets that introduce their respective domains
(CLIENT-*...)". This ticket (AUTH-002) adds only the single lookup method
its own deliverable ("API Key validation") requires
(``get_by_api_key_hash``). CLIENT-001 (Client Registration) will extend
this class with creation/update/listing operations when it implements
FR-001 - it should add methods here, not create a second, competing
Client repository.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.client import Client


class ClientRepository:
    """Data-access operations for the ``clients`` table."""

    def get_by_api_key_hash(self, db: Session, api_key_hash: str) -> Client | None:
        """
        Return the ``Client`` whose ``api_key_hash`` matches, or ``None``.

        ``api_key_hash`` is unique (CPM-002), so at most one row can ever
        match.
        """
        stmt = select(Client).where(Client.api_key_hash == api_key_hash)
        return db.execute(stmt).scalar_one_or_none()
