"""
SQLAlchemy Declarative Base configuration.

Defines the single ``Base`` class that every ORM model in the CPMS
backend inherits from (directly, or indirectly through
``backend.models.base.BaseModel`` / ``AuditModel``). All model tables are
registered on ``Base.metadata``, which is the single object used both by
SQLAlchemy at runtime and by Alembic's autogenerate environment
(``backend/database/migrations/env.py``) to compare the ORM's view of the
schema against the actual database.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root declarative base for all CPMS ORM models."""
