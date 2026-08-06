"""
Database package (implemented by CPM-002).

Contains:
    * base.py       - the SQLAlchemy DeclarativeBase (``Base``).
    * database.py   - engine configuration (``engine``).
    * session.py    - session factory and the ``get_db()`` dependency.
    * migrations/   - Alembic migration environment and generated
                       revisions.
"""
