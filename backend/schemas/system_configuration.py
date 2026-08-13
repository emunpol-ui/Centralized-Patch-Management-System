"""
System Configuration schemas (DTOs) - SYS-001, per the DTO Pattern (SAD
Section 5.8).

``SystemConfigurationValues`` is the read/response shape, used both for
the Settings page's initial render and as the *runtime resolution*
result consumed internally by every SYS-001-managed setting's runtime
integration point (``get_auth_service``, ``DashboardService``, the
repository upload route) - see
``backend.services.system_configuration_service.
SystemConfigurationService.get_effective_settings``.

``SystemConfigurationUpdateRequest`` is the administrator-submitted
Settings page form. Field-level validation bounds below are the FR-018
"invalid input that should be rejected" cases explicitly called out by
this ticket (negative/zero intervals, negative upload size), plus a
generous upper bound chosen only to catch obvious fat-finger input (e.g.
a session timeout of 999999999 minutes) - not derived from any specific
documented requirement, since none of PRS/SAD/Charter specifies a
numeric ceiling for these settings.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SystemConfigurationValues(BaseModel):
    """
    The effective (persisted-override-or-environment-default) value of
    every SYS-001-managed setting.

    ``is_persisted`` distinguishes "an administrator has saved an
    override" (``True``) from "no row exists yet; these are the
    application's environment-sourced defaults" (``False``), so the
    Settings page can tell the administrator which state they are in.
    """

    session_inactivity_timeout_minutes: int
    client_heartbeat_timeout_minutes: int
    max_installer_upload_size_mb: int
    is_persisted: bool

    @property
    def max_installer_upload_size_bytes(self) -> int:
        """`max_installer_upload_size_mb` expressed in bytes, mirroring `Settings.max_installer_upload_size_bytes`."""
        return self.max_installer_upload_size_mb * 1024 * 1024


class SystemConfigurationUpdateRequest(BaseModel):
    """
    Administrator-submitted Settings page form (SYS-001).

    Bounds:
        * ``session_inactivity_timeout_minutes``: 1-1440 (1 minute to 24
          hours). The existing environment default is 30.
        * ``client_heartbeat_timeout_minutes``: 1-1440 (1 minute to 24
          hours). The existing environment default is 10.
        * ``max_installer_upload_size_mb``: 1-2048 (1 MB to 2 GB). The
          existing environment default is 500.

    A value of 0 or below is rejected for every field (FR-018 "zero
    values where zero is invalid" / "negative upload size" /
    "negative intervals").
    """

    session_inactivity_timeout_minutes: int = Field(
        ge=1, le=1440, description="Administrator session inactivity timeout, in minutes."
    )
    client_heartbeat_timeout_minutes: int = Field(
        ge=1, le=1440, description="Client heartbeat timeout before a client is considered Offline, in minutes."
    )
    max_installer_upload_size_mb: int = Field(
        ge=1, le=2048, description="Maximum accepted repository installer upload size, in megabytes."
    )
