"""
System configuration repository (SYS-001).

Pure data-access layer for the singleton ``SystemConfiguration`` row, per
the Repository Pattern (SAD Section 5.4, Section 11). Contains no
business rules or validation - those belong to
``backend.services.system_configuration_service.
SystemConfigurationService``, consistent with every other repository in
this codebase.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.system_configuration import SystemConfiguration


class SystemConfigurationRepository:
    """Data-access operations for the ``system_configuration`` table."""

    def get_current(self, db: Session) -> Optional[SystemConfiguration]:
        """
        Return the single persisted configuration row, or ``None`` if no
        administrator has ever saved the Settings page.

        The table is expected to hold at most one row (enforced by
        application logic in ``upsert`` below, not a database
        constraint - a single nullable-free row is simpler here than a
        fixed/sentinel primary key, and this prototype has no concurrent
        multi-administrator write scenario that would make a race
        plausible).
        """
        stmt = select(SystemConfiguration).limit(1)
        return db.execute(stmt).scalars().first()

    def upsert(
        self,
        db: Session,
        *,
        session_inactivity_timeout_minutes: int,
        client_heartbeat_timeout_minutes: int,
        max_installer_upload_size_mb: int,
    ) -> SystemConfiguration:
        """
        Create the singleton row if it does not yet exist, or update it
        in place if it does.

        Flushes but does not commit - the caller
        (``SystemConfigurationService.update_settings``) commits once,
        alongside its audit log entry, consistent with every other write
        path in this codebase (see e.g.
        ``RepositoryService.upload_package``).
        """
        row = self.get_current(db)
        if row is None:
            row = SystemConfiguration(
                session_inactivity_timeout_minutes=session_inactivity_timeout_minutes,
                client_heartbeat_timeout_minutes=client_heartbeat_timeout_minutes,
                max_installer_upload_size_mb=max_installer_upload_size_mb,
            )
            db.add(row)
        else:
            row.session_inactivity_timeout_minutes = session_inactivity_timeout_minutes
            row.client_heartbeat_timeout_minutes = client_heartbeat_timeout_minutes
            row.max_installer_upload_size_mb = max_installer_upload_size_mb
        db.flush()
        return row
