"""
Software inventory upload request schema (DTO).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define and
validate the request body for ``POST /api/agent/inventory/upload`` (FR-005
Software Inventory Upload). Field sizes mirror the ``software_inventory``
table's column widths (CORE-002 / ``backend/models/software_inventory.py``)
so oversized input is rejected by Pydantic (422) before it ever reaches the
database, consistent with the pattern already established by
``backend.schemas.client.ClientRegistrationRequest``.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SoftwareInventoryItem(BaseModel):
    """
    One installed-application record, as collected by the Client Agent's
    Registry scanner (PRS FR-004 "Inventory Data Collected").

    ``software_name`` and ``version`` are required (every Uninstall
    registry entry that reaches this far has already had its
    ``DisplayName`` verified non-empty by the Client Agent's scanner -
    see ``agent/scanner/registry_scanner.py``); the remaining fields are
    optional per FR-004's own table ("where available").
    """

    software_name: str = Field(..., max_length=255, description="Installed application name.")
    version: str = Field(..., max_length=100, description="Installed application version.")
    publisher: Optional[str] = Field(None, max_length=255, description="Software publisher.")
    install_date: Optional[date] = Field(None, description="Installation date, if reported by the installer.")
    install_location: Optional[str] = Field(
        None, max_length=500, description="Installation directory, if available."
    )

    @field_validator("software_name", "version")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("publisher", "install_location")
    @classmethod
    def blank_optional_to_none(cls, value: Optional[str]) -> Optional[str]:
        """Treat a whitespace-only optional field the same as an absent one."""
        if value is not None and not value.strip():
            return None
        return value


class InventoryUploadRequest(BaseModel):
    """
    Request body for ``POST /api/agent/inventory/upload`` (PRS FR-005
    Inputs table: "Software Inventory - JSON representation of installed
    applications").

    ``items`` defaults to an empty list rather than being strictly
    required: a client that has no (or no longer any) installed software
    to report is a valid, if unusual, state, and the upload should still
    be accepted and processed (as a full sync - see
    ``backend.services.inventory_service.InventoryService``) rather than
    rejected outright.
    """

    items: List[SoftwareInventoryItem] = Field(
        default_factory=list, description="Installed software collected by the Client Agent."
    )
