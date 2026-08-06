"""
ClientProvisioningKey ORM model.

--------------------------------------------------------------------------
DESIGN NOTE - an addition beyond the PRS/SAD data dictionary, required to
resolve a documented gap between AUTH-002 and this ticket (CLIENT-001)

This entity does not appear in the PRS Appendix D data dictionary or the
SAD's entity list. It is added here because FR-001's own precondition
("The Client Agent possesses a valid API key issued by the administrator
[FR-020]") and AUTH-002's completion report both establish that a brand
new Client Agent authenticates for the very first time using a key that
has no ``Client`` row yet:

    * ``backend.api.dependencies.require_client_api_key`` (AUTH-002)
      authenticates by looking up ``Client.api_key_hash`` - which only
      exists for an *already-registered* client.
    * ``Client``'s columns (``agent_guid``, ``hostname``, ``ip_address``,
      ``operating_system``, ``agent_version``) are all ``NOT NULL``
      (CPM-002), so a "shell" ``Client`` row cannot be created ahead of
      registration without relaxing that completed schema - something
      ``backend.services.client_auth_service`` explicitly declined to do
      when it deferred FR-020 to this ticket, and which this ticket's own
      instructions ("do not redesign the database unless absolutely
      required") likewise rule out.

``CURRENT_STATE.md``'s "Notes for CLIENT-001's implementer" anticipates
exactly this and directs that FR-020's provisioning endpoint be built
together with CLIENT-001, "since the two are chronologically coupled."
This model is the minimal piece of FR-020 required to unblock FR-001: an
administrator-issued, not-yet-claimed API key. Once a Client Agent
presents it to ``POST /api/register`` for the first time, the key is
"claimed" - a ``Client`` row is created using this row's ``key_hash`` as
its own ``api_key_hash``, and this row is deleted (see
``backend.services.client_service.ClientService.register``). A
provisioning key's existence therefore *is* its "unclaimed" state; no
separate ``claimed_at`` column is needed.

Full FR-020 concerns not required to unblock registration (e.g. a
dashboard listing of outstanding provisioned-but-unclaimed keys) are left
to a future dashboard ticket, consistent with "implement only the
requested ticket."
--------------------------------------------------------------------------
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import AuditModel


class ClientProvisioningKey(AuditModel):
    """
    An administrator-issued API key not yet claimed by any ``Client``.

    ``key_hash`` mirrors ``Client.api_key_hash`` exactly (a SHA-256 digest
    via ``backend.core.security.hash_token``): the raw key is only ever
    displayed once, at generation time (FR-020), and never stored at rest
    here, matching the pattern already established for ``Client`` and
    ``AdministratorSession``.

    ``created_by_admin_id`` is optional and uses ``ondelete="SET NULL"``,
    matching ``AuditLog.admin_id`` and ``AuditLog.client_id`` (SAD Section
    7.6): removing the issuing administrator later must never invalidate
    or orphan-delete an outstanding provisioning key.
    """

    __tablename__ = "client_provisioning_keys"

    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<ClientProvisioningKey id={self.id}>"
