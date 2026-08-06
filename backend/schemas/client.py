"""
Client registration request/response schemas (DTOs).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define and
validate the request body for ``POST /api/register`` (FR-001). Field
sizes mirror the ``clients`` table's column widths (CPM-002 /
``backend/models/client.py``) so oversized input is rejected by Pydantic
(422) before it ever reaches the database.
"""

from __future__ import annotations

import ipaddress
import uuid

from pydantic import BaseModel, Field, field_validator


class ClientRegistrationRequest(BaseModel):
    """
    Request body for ``POST /api/register`` (PRS FR-001 Inputs table).

    ``agent_guid`` is the persistent identifier the Client Agent generates
    and stores locally on first execution (FR-001); the server uses it,
    never hostname or IP address, to decide whether this is a new or
    returning client (see ``backend.services.client_service.ClientService.
    register``).
    """

    agent_guid: uuid.UUID = Field(..., description="Persistent identifier generated locally by the Client Agent.")
    hostname: str = Field(..., max_length=255, description="Windows computer name.")
    ip_address: str = Field(..., max_length=45, description="Client network address (IPv4 or IPv6).")
    operating_system: str = Field(..., max_length=100, description="Windows version.")
    agent_version: str = Field(..., max_length=50, description="Installed CPMS Agent version.")

    @field_validator("hostname", "operating_system", "agent_version")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("ip_address")
    @classmethod
    def valid_ip_address(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("must be a valid IPv4 or IPv6 address") from exc
        return value
