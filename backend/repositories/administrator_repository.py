"""
Administrator repository.

Pure data-access layer for the ``Administrator`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). Contains no business
rules or password handling - callers (``backend.services.auth_service``)
are responsible for all authentication logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.administrator import Administrator


class AdministratorRepository:
    """Data-access operations for the ``administrators`` table."""

    def get_by_username(self, db: Session, username: str) -> Administrator | None:
        """Return the ``Administrator`` with the given username, or ``None``."""
        stmt = select(Administrator).where(Administrator.username == username)
        return db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, db: Session, admin_id: uuid.UUID) -> Administrator | None:
        """Return the ``Administrator`` with the given primary key, or ``None``."""
        return db.get(Administrator, admin_id)

    def update_last_login(self, db: Session, administrator: Administrator) -> Administrator:
        """Stamp ``last_login`` with the current time and flush the change."""
        administrator.last_login = datetime.now(timezone.utc)
        db.add(administrator)
        db.flush()
        return administrator
