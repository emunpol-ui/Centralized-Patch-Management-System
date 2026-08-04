"""
Database session management.

Provides ``SessionLocal``, a configured session factory bound to the
application engine, and ``get_db()``, a generator suitable for use as a
FastAPI dependency that yields one ``Session`` per request/unit-of-work
and guarantees it is closed afterwards.

No routers use ``get_db()`` yet (per CPM-002 scope: repositories, services,
and APIs are implemented in later tickets). It is wired into
``backend.api.dependencies`` as ``DBSessionDependency`` so those later
tickets can start consuming it immediately, following the same pattern
already established for ``SettingsDependency`` in CPM-001.
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import engine

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    """
    Yield a database ``Session`` for the duration of a single request.

    The session is always closed in a ``finally`` block, regardless of
    whether the request succeeded, raised a handled ``AppException``, or
    raised an unhandled exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
