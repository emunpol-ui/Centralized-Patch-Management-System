"""
System configuration service (SYS-001 - FR-018 System Configuration
Management).

Business logic behind the administrator Settings page: resolving the
*effective* value of each supported setting (a persisted override if an
administrator has saved one, otherwise the environment-sourced
``Settings`` default) and persisting validated administrator-submitted
changes with an audit log entry, per the Service Layer Pattern (SAD
Section 5.5).

Every runtime consumer of a SYS-001-managed setting -
``get_auth_service`` (``backend/api/dependencies.py``), ``DashboardService``'s
client heartbeat classification, and the repository package upload size
check (``backend/api/routers/repository.py``) - calls
``get_effective_settings`` below rather than reading
``Settings.SESSION_INACTIVITY_TIMEOUT_MINUTES`` /
``Settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES`` /
``Settings.MAX_INSTALLER_UPLOAD_SIZE_MB`` directly, so a saved override
takes effect on the very next request/read - no server restart required.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.models.enums import AuditSeverity
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.system_configuration_repository import SystemConfigurationRepository
from backend.schemas.system_configuration import SystemConfigurationUpdateRequest, SystemConfigurationValues

logger = logging.getLogger(__name__)


class SystemConfigurationService:
    """
    Effective-settings resolution and persistence for SYS-001.

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(
        self,
        system_configuration_repository: SystemConfigurationRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._config = system_configuration_repository or SystemConfigurationRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def get_effective_settings(self, db: Session, settings: Settings) -> SystemConfigurationValues:
        """
        Return the current effective value of every SYS-001-managed
        setting: the persisted override if one has been saved, otherwise
        the environment-sourced ``Settings`` default.

        Read-only - never creates a database row. This is called on
        (almost) every request via ``get_auth_service``, so it
        deliberately performs no writes and no query beyond the single
        ``SELECT`` already required to check for an override.
        """
        row = self._config.get_current(db)
        if row is not None:
            return SystemConfigurationValues(
                session_inactivity_timeout_minutes=row.session_inactivity_timeout_minutes,
                client_heartbeat_timeout_minutes=row.client_heartbeat_timeout_minutes,
                max_installer_upload_size_mb=row.max_installer_upload_size_mb,
                is_persisted=True,
            )
        return SystemConfigurationValues(
            session_inactivity_timeout_minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES,
            client_heartbeat_timeout_minutes=settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES,
            max_installer_upload_size_mb=settings.MAX_INSTALLER_UPLOAD_SIZE_MB,
            is_persisted=False,
        )

    def update_settings(
        self,
        db: Session,
        *,
        admin_id: UUID,
        request: SystemConfigurationUpdateRequest,
        previous: SystemConfigurationValues,
    ) -> SystemConfigurationValues:
        """
        Persist a new set of SYS-001-managed setting values.

        Field-level validation (positive integers, sensible upper
        bounds) is already enforced by ``SystemConfigurationUpdateRequest``
        before this method is ever called (FastAPI validates the request
        body against that schema at the router boundary); this method
        performs persistence and audit logging, mirroring
        ``RepositoryService.upload_package``'s "validate -> persist ->
        audit -> commit" shape.

        ``previous`` (the effective values immediately before this
        change, already computed by the router via
        ``get_effective_settings`` to render the just-submitted form) is
        used only to build a clear, human-readable audit description of
        what changed - it is not re-queried here, and no old/new values
        beyond these three plain integers are ever written to the audit
        log (nothing sensitive is involved).
        """
        row = self._config.upsert(
            db,
            session_inactivity_timeout_minutes=request.session_inactivity_timeout_minutes,
            client_heartbeat_timeout_minutes=request.client_heartbeat_timeout_minutes,
            max_installer_upload_size_mb=request.max_installer_upload_size_mb,
        )

        changes = []
        if previous.session_inactivity_timeout_minutes != request.session_inactivity_timeout_minutes:
            changes.append(
                f"session_inactivity_timeout_minutes: {previous.session_inactivity_timeout_minutes} -> "
                f"{request.session_inactivity_timeout_minutes}"
            )
        if previous.client_heartbeat_timeout_minutes != request.client_heartbeat_timeout_minutes:
            changes.append(
                f"client_heartbeat_timeout_minutes: {previous.client_heartbeat_timeout_minutes} -> "
                f"{request.client_heartbeat_timeout_minutes}"
            )
        if previous.max_installer_upload_size_mb != request.max_installer_upload_size_mb:
            changes.append(
                f"max_installer_upload_size_mb: {previous.max_installer_upload_size_mb} -> "
                f"{request.max_installer_upload_size_mb}"
            )

        description = (
            "System configuration updated: " + "; ".join(changes)
            if changes
            else "System configuration saved with no effective changes."
        )
        self._audit_logs.create(
            db,
            event_type="SYSTEM_CONFIGURATION_UPDATED",
            severity=AuditSeverity.INFO,
            description=description,
            admin_id=admin_id,
        )
        db.commit()

        logger.info(
            "System configuration updated by administrator %s: %s",
            admin_id,
            "; ".join(changes) if changes else "(no changes)",
        )

        return SystemConfigurationValues(
            session_inactivity_timeout_minutes=row.session_inactivity_timeout_minutes,
            client_heartbeat_timeout_minutes=row.client_heartbeat_timeout_minutes,
            max_installer_upload_size_mb=row.max_installer_upload_size_mb,
            is_persisted=True,
        )
