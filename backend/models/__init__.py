"""
SQLAlchemy ORM models package.

Importing this package registers every model class's table definition on
``backend.database.base.Base.metadata``. Both Alembic's autogenerate
environment (``backend/database/migrations/env.py``) and any code that
calls ``Base.metadata.create_all()`` must import ``backend.models``
(directly or transitively) before doing so, or the tables defined here
will be invisible to them.
"""

from __future__ import annotations

from backend.database.base import Base
from backend.models.administrator import Administrator
from backend.models.administrator_session import AdministratorSession
from backend.models.audit_log import AuditLog
from backend.models.client import Client
from backend.models.client_provisioning_key import ClientProvisioningKey
from backend.models.deployment import Deployment
from backend.models.deployment_target import DeploymentTarget
from backend.models.repository_package import RepositoryPackage
from backend.models.software_inventory import SoftwareInventory
from backend.models.system_configuration import SystemConfiguration

__all__ = [
    "Base",
    "Administrator",
    "AdministratorSession",
    "AuditLog",
    "Client",
    "ClientProvisioningKey",
    "Deployment",
    "DeploymentTarget",
    "RepositoryPackage",
    "SoftwareInventory",
    "SystemConfiguration",
]