"""
Database engine configuration.

Builds the single, process-wide SQLAlchemy ``Engine`` used by the
application, based on the resolved ``database_url`` from
``backend.core.config.Settings``.

Notable behavior:
    * For SQLite (the prototype default per Charter Section 8 and SAD
      Section 6.4), ``check_same_thread`` is disabled so the engine's
      connection pool can be shared safely across the worker threads
      FastAPI/Uvicorn may use. This is safe because each unit of work
      obtains its own ``Session`` (see ``backend/database/session.py``)
      rather than sharing a connection concurrently.
    * SQLite disables foreign-key constraint enforcement by default; an
      event listener enables it (``PRAGMA foreign_keys=ON``) on every new
      connection so that the ``ForeignKey`` relationships declared on the
      ORM models are actually enforced by the database, not merely assumed
      by the ORM.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine, event

from backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_engine(settings: Settings) -> Engine:
    """Construct and configure the SQLAlchemy engine for ``settings``."""
    is_sqlite = settings.database_url.startswith("sqlite")

    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine = create_engine(
        settings.database_url,
        echo=settings.DATABASE_ECHO,
        future=True,
        connect_args=connect_args,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
            """Enable SQLite foreign-key constraint enforcement per-connection."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    logger.info(
        "Database engine created (dialect=%s, url=%s).",
        engine.dialect.name,
        engine.url.render_as_string(hide_password=True),
    )
    return engine


# Single, process-wide engine instance. Built eagerly at import time so
# that a misconfigured DATABASE_URL fails fast during application startup
# rather than on the first request that happens to touch the database.
engine: Engine = _build_engine(get_settings())
