"""
Shared enumerations used across ORM models.

Centralizing these here keeps status/type vocabularies consistent between
models and avoids re-declaring the same string literals in multiple files.
Each enum is stored using ``sqlalchemy.Enum(..., native_enum=False)`` (see
the individual model files), which renders as a portable ``VARCHAR`` +
``CHECK`` constraint rather than a database-native enum type. This keeps
the schema identical across SQLite (the prototype database) and a future
PostgreSQL migration (NFR-020), since PostgreSQL's native ``ENUM`` type
would otherwise require its own migration handling.
"""

from __future__ import annotations

import enum


class ClientStatus(str, enum.Enum):
    """Client operational status (PRS FR-014 / Section 7.5.1)."""

    ONLINE = "Online"
    OFFLINE = "Offline"
    UNKNOWN = "Unknown"


class InstallerType(str, enum.Enum):
    """Supported repository installer package types (PRS FR-006)."""

    EXE = "EXE"
    MSI = "MSI"


class ApprovalStatus(str, enum.Enum):
    """
    Repository package approval/availability status (PRS Section 7.5.3).

    Setting a package to ``INACTIVE`` is how FR-017 "removing obsolete
    repository entries" is implemented (a logical deactivation) rather
    than a physical row deletion - see the design note in
    ``backend/models/deployment.py`` for why this matters for
    ``Deployment.repository_id`` referential integrity.
    """

    APPROVED = "Approved"
    INACTIVE = "Inactive"


class DeploymentStatus(str, enum.Enum):
    """Per-client deployment execution status (PRS FR-012)."""

    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    INSTALLING = "Installing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class AuditSeverity(str, enum.Enum):
    """Audit log entry severity (PRS Section 7.5.6)."""

    INFO = "Information"
    WARNING = "Warning"
    ERROR = "Error"
