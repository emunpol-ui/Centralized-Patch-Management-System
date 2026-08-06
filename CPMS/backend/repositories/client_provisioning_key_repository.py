"""
Client provisioning key repository.

Pure data-access layer for the ``ClientProvisioningKey`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). See
``backend/models/client_provisioning_key.py`` for why this table exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.client_provisioning_key import ClientProvisioningKey


class ClientProvisioningKeyRepository:
    """Data-access operations for the ``client_provisioning_keys`` table."""

    def create(
        self,
        db: Session,
        *,
        key_hash: str,
        created_by_admin_id: uuid.UUID | None,
    ) -> ClientProvisioningKey:
        """Persist a newly issued (unclaimed) provisioning key and flush it."""
        key = ClientProvisioningKey(key_hash=key_hash, created_by_admin_id=created_by_admin_id)
        db.add(key)
        db.flush()
        return key

    def get_by_key_hash(self, db: Session, key_hash: str) -> ClientProvisioningKey | None:
        """Return the unclaimed provisioning key matching ``key_hash``, or ``None``."""
        stmt = select(ClientProvisioningKey).where(ClientProvisioningKey.key_hash == key_hash)
        return db.execute(stmt).scalar_one_or_none()

    def delete(self, db: Session, key: ClientProvisioningKey) -> None:
        """Consume (delete) a provisioning key once it has been claimed by a Client."""
        db.delete(key)
        db.flush()
