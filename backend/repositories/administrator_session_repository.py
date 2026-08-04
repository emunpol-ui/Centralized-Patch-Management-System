"""
Administrator session repository.

Pure data-access layer for the ``AdministratorSession`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). Contains no business
rules (e.g. how long a session should live) - callers
(``backend.services.auth_service``) supply all timing decisions;
this layer only persists and queries what it is given.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.administrator_session import AdministratorSession


class AdministratorSessionRepository:
    """Data-access operations for the ``administrator_sessions`` table."""

    def create(
        self,
        db: Session,
        *,
        admin_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> AdministratorSession:
        """Persist a new session record and flush it."""
        session = AdministratorSession(
            admin_id=admin_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(session)
        db.flush()
        return session

    def get_valid_by_token_hash(self, db: Session, token_hash: str) -> AdministratorSession | None:
        """
        Return the session matching ``token_hash`` if it exists AND has not
        expired, otherwise ``None``. Expiry comparison is performed here
        (not left to the caller) so every consumer applies the same rule.
        """
        stmt = select(AdministratorSession).where(
            AdministratorSession.token_hash == token_hash,
            AdministratorSession.expires_at > datetime.now(timezone.utc),
        )
        return db.execute(stmt).scalar_one_or_none()

    def touch(self, db: Session, session: AdministratorSession, expires_at: datetime) -> AdministratorSession:
        """
        Update a session's ``last_activity_at`` to now and extend
        ``expires_at`` to the value supplied by the caller, implementing
        the "sliding window" inactivity timeout required by NFR-028.
        """
        session.last_activity_at = datetime.now(timezone.utc)
        session.expires_at = expires_at
        db.add(session)
        db.flush()
        return session

    def delete(self, db: Session, session: AdministratorSession) -> None:
        """Remove a single session record (logout)."""
        db.delete(session)
        db.flush()

    def delete_expired(self, db: Session) -> int:
        """
        Remove all sessions whose ``expires_at`` has passed.

        Not invoked automatically by anything in this ticket - provided as
        a reusable maintenance operation for a future scheduled cleanup
        task (SYS-002 Logging System / a future scheduler ticket).
        """
        stmt = delete(AdministratorSession).where(AdministratorSession.expires_at <= datetime.now(timezone.utc))
        result = db.execute(stmt)
        db.flush()
        return result.rowcount or 0
