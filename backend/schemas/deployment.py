"""
Deployment creation request/response schemas (DTOs).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define and
validate the administrator-facing deployment creation request (FR-008
Deployment Job Creation, FR-009 Deployment Job Retrieval targeting;
Backlog DEPLOY-001 "Deployment creation API" deliverable) and shape the
resulting API response.

Mirrors the conventions already established in
``backend/schemas/repository.py`` (``model_config = ConfigDict(from_attributes=True)``
so response schemas can be built directly from ORM model instances) and
``backend/schemas/updates.py`` (UUIDs surfaced as UUIDs, not raw strings).
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.enums import DeploymentStatus


class DeploymentCreateRequest(BaseModel):
    """
    Administrator request body for creating a new deployment batch
    (FR-008 Deployment Job Creation).

    ``repository_package_id`` identifies the single approved software
    package to deploy; ``client_ids`` identifies one or more registered
    target clients that will each receive their own ``DeploymentTarget``
    record within the resulting batch (FR-008 functional behavior:
    "the server creates one deployment job record per targeted client,
    all sharing a common Batch ID").
    """

    repository_package_id: UUID = Field(
        ..., description="Identifier of the approved repository package to deploy."
    )
    client_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="Identifiers of the registered target clients (at least one required).",
    )

    @field_validator("client_ids")
    @classmethod
    def no_duplicate_clients(cls, value: List[UUID]) -> List[UUID]:
        """
        Reject a request that lists the same target client more than
        once (FR-008 "one deployment job record...per targeted client" -
        a repeated client id would otherwise attempt to create two
        target rows for the same client within the same batch, which
        ``DeploymentTarget``'s ``uq_deployment_target_deployment_client``
        unique constraint would reject anyway; failing fast here gives a
        clearer 400 response instead of surfacing a database integrity
        error).
        """
        if len(set(value)) != len(value):
            raise ValueError("client_ids must not contain duplicate entries")
        return value


class DeploymentTargetResponse(BaseModel):
    """
    One targeted client's initial state within a newly created deployment
    batch (FR-008 Outputs: "Deployment ID - Unique identifier per targeted
    client's deployment job").

    ``model_config``'s ``from_attributes=True`` allows this schema to be
    built directly from a ``backend.models.deployment_target.
    DeploymentTarget`` ORM instance, matching the pattern already used by
    ``backend.schemas.repository.RepositoryPackageResponse``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Deployment target identifier.")
    client_id: UUID = Field(..., description="Identifier of the targeted client.")
    status: DeploymentStatus = Field(..., description="Current per-client deployment status.")
    created_at: datetime = Field(..., description="Timestamp this deployment target was created.")


class DeploymentResponse(BaseModel):
    """
    Response body describing a newly created deployment batch (FR-008
    Outputs: "Batch ID - Identifier shared by all deployment job records
    created from this request").

    ``model_config``'s ``from_attributes=True`` allows this schema to be
    built directly from a ``backend.models.deployment.Deployment`` ORM
    instance (``targets`` resolves via the model's own relationship).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Deployment batch identifier (PRS 'Batch ID').")
    repository_id: UUID = Field(..., description="Identifier of the deployed repository package.")
    created_by_admin_id: UUID = Field(
        ..., description="Identifier of the administrator who created this deployment."
    )
    created_at: datetime = Field(..., description="Deployment batch creation timestamp.")
    targets: List[DeploymentTargetResponse] = Field(
        ..., description="One entry per targeted client, each with its initial Pending status."
    )
    target_count: int = Field(..., description="Number of clients targeted by this deployment batch.")
