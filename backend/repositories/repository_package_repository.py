"""
Repository package repository.

Pure data-access layer for the ``RepositoryPackage`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). Introduced by this
ticket (INV-002 / Backlog UPDATE-001, FR-007 Software Version Comparison)
as the minimal read-only slice needed to compare installed software
against the approved repository catalog. The ``repository_packages``
table itself was already defined by CORE-002
(``backend/models/repository_package.py``), but - like
``software_inventory`` before INV-001 - no repository consumed it until
now (see the deferral note in ``backend/repositories/__init__.py``).

Package *upload*, metadata editing, and checksum validation (FR-006,
Backlog REP-001) are out of scope for this ticket and are not implemented
here; only the read operation FR-007 requires is provided. Write
operations belong to the repository that REP-001 introduces.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.enums import ApprovalStatus
from backend.models.repository_package import RepositoryPackage


class RepositoryPackageRepository:
    """Data-access operations for the ``repository_packages`` table."""

    def list_approved(self, db: Session) -> List[RepositoryPackage]:
        """
        Return every ``RepositoryPackage`` currently ``APPROVED`` (FR-007
        precondition: "Approved software versions have been defined").

        Packages set to ``INACTIVE`` (the FR-017 "removal" mechanism -
        see the design note on ``backend.models.repository_package.
        RepositoryPackage``) are intentionally excluded: an inactive
        package is no longer an administrator-approved version and must
        not be treated as an update target for comparison purposes.
        """
        stmt = select(RepositoryPackage).where(RepositoryPackage.approval_status == ApprovalStatus.APPROVED)
        return list(db.execute(stmt).scalars().all())
