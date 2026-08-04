"""
Authentication request/response schemas (DTOs).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define and
validate the request bodies for the authentication endpoints. Response
bodies follow the standardized envelope already established in
``backend.core.exceptions`` and used by every endpoint (``{"success":
..., "message": ..., "data": ...}``); per PRS Appendix B, the login
response's ``data`` payload is documented precisely, so it is modeled
explicitly here as ``AdminLoginResponseData`` for a typed, self-
documenting Swagger schema.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class AdminLoginRequest(BaseModel):
    """
    Request body for ``POST /api/admin/login`` (PRS Appendix B).

    Validation rules per PRS Appendix B: "``username`` and ``password``
    are required and shall not be empty strings."
    """

    username: str = Field(..., description="Administrator login name.")
    password: str = Field(..., description="Administrator login password.")

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value


class AdminLoginResponseData(BaseModel):
    """The ``data`` payload of a successful login response (PRS Appendix B)."""

    admin_id: uuid.UUID
    username: str
