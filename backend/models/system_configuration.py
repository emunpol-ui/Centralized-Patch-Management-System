"""
SystemConfiguration ORM model.

Persists the CPMS system settings exposed through the administrator
Settings page (SYS-001 - FR-018 System Configuration Management). A
single-row ("singleton") table: exactly one ``SystemConfiguration`` row
ever exists, holding the current persisted override for each supported
setting. Uses typed columns (per this ticket's "typed configuration
fields where appropriate" instruction) rather than an unstructured
key/value table, since the set of configurable settings is small,
enumerated, and each has an obvious primitive type - the same reasoning
already applied to every other CPMS entity (see PRS Section 7.3).

Only settings with a concrete, verified runtime integration point are
represented here (see ``backend.services.system_configuration_service.
SystemConfigurationService`` for exactly where each column is consumed).
Settings identified in the PRS/SAD/Backlog but with no existing runtime
consumer (inventory scan interval, deployment polling interval, client
retry interval, repository path, log retention) are intentionally NOT
included here - see the SYS-001 completion report for the rationale for
each.

If no row exists yet, every runtime consumer falls back to the
environment-sourced ``Settings`` default (``backend.core.config``) - see
``SystemConfigurationService.get_effective_settings``. A row is created
only when an administrator actually saves the Settings page for the
first time (see ``SystemConfigurationRepository.upsert``); no seed row is
inserted by the migration.
"""

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import AuditModel


class SystemConfiguration(AuditModel):
    """
    The single persisted row of CPMS runtime-configurable settings
    (SYS-001).

    Every column mirrors an existing ``Settings`` (``backend.core.
    config``) field of the same unit, so a saved value can always be
    compared directly against - and used to override - that field's
    environment-sourced default. No column is nullable: a row, once
    created, always carries a concrete value for every supported
    setting, keeping "effective settings" resolution in the service
    layer simple (no partial-row handling required).
    """

    __tablename__ = "system_configuration"

    session_inactivity_timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    client_heartbeat_timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_installer_upload_size_mb: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<SystemConfiguration id={self.id} "
            f"session_timeout={self.session_inactivity_timeout_minutes}m "
            f"heartbeat_timeout={self.client_heartbeat_timeout_minutes}m "
            f"max_upload={self.max_installer_upload_size_mb}MB>"
        )
