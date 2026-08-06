"""
Alembic migration environment.

Configures Alembic to:
    * Source the database URL from the application's own Settings
      (``backend.core.config.get_settings()``) rather than duplicating it
      in ``alembic.ini``, so ``.env`` remains the single source of truth
      for the connection string.
    * Use ``backend.database.base.Base.metadata`` as the autogenerate
      comparison target, after importing ``backend.models`` so every
      model's table is actually registered on it.
    * Run in SQLite "batch" mode (table-recreate strategy), which SQLite
      requires for most ALTER TABLE operations that Alembic would
      otherwise emit directly; this is skipped automatically for other
      dialects (e.g. a future PostgreSQL database).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the models package *before* reading target_metadata below - this
# import's side effect is what registers every table on Base.metadata.
import backend.models  # noqa: F401
from backend.core.config import get_settings
from backend.database.base import Base

# Alembic Config object, providing access to values within alembic.ini.
config = context.config

# Inject the application's resolved database URL so alembic.ini does not
# need to duplicate connection configuration.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging, unless already configured
# by whatever process invoked Alembic.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata object used for 'autogenerate' schema comparisons.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL without a live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (executes against a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
