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
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.enums import DeploymentStatus, InstallerType


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


# --------------------------------------------------------------------------
# DEPLOY-002 ADDITION - Client Agent deployment polling (FR-009)
#
# These schemas shape the response of the new agent-facing
# ``GET /api/agent/deployments/poll`` endpoint (see
# ``backend/api/routers/agent.py``). They are read-only response DTOs -
# there is no corresponding request body schema, since the poll carries no
# input beyond the authenticated client's own identity (resolved from the
# ``Authorization: Bearer`` header, never from the request body/path -
# see this ticket's "Client Isolation" requirement).
#
# Deliberately excludes anything belonging to DEPLOY-003 ("installer
# download... checksum verification... silent installation") beyond the
# static metadata (checksum, silent command, installer type/filename) the
# Client Agent needs to *proceed to* that later step - this endpoint does
# not perform the download itself.
# --------------------------------------------------------------------------


class DeploymentPollPackageDetail(BaseModel):
    """
    The approved repository package associated with a pending deployment
    target, shaped for Client Agent consumption (FR-009 "deployment
    details, including the software package, installer location, and
    installation parameters").

    Deliberately omits administrator-only/internal fields (e.g.
    ``approval_status``, ``created_at``/``updated_at``) that
    ``backend.schemas.repository.RepositoryPackageResponse`` exposes to
    the dashboard - the Client Agent only needs what it will use in
    DEPLOY-003 to download and (eventually) verify and execute the
    installer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Repository package identifier.")
    software_name: str = Field(..., description="Approved software name.")
    version: str = Field(..., description="Approved software version.")
    installer_type: InstallerType = Field(..., description="Installer type (EXE or MSI).")
    installer_filename: str = Field(
        ..., description="Server-generated storage filename (FR-006 Upload Validation Rules)."
    )
    silent_command: str = Field(
        ...,
        description=(
            "Silent installation command template (FR-006/FR-011). References the downloaded "
            "installer only via the {installer_path} placeholder token."
        ),
    )
    checksum: str = Field(
        ..., description="SHA-256 checksum computed at upload time (FR-006), for FR-011 verification."
    )
    file_size: int = Field(..., description="Installer file size in bytes.")


class DeploymentPollTargetResponse(BaseModel):
    """
    A single pending deployment assigned to the polling Client Agent
    (FR-009 Outputs: "Deployment Details - Installer information and
    parameters").

    ``deployment_id`` is the batch identifier (PRS "Batch ID");
    ``target_id`` is this client's own per-client
    ``DeploymentTarget.id`` - the identifier the Client Agent should carry
    forward into DEPLOY-003 (installer download) and DEPLOY-004 (status
    reporting).
    """

    model_config = ConfigDict(from_attributes=True)

    target_id: UUID = Field(..., description="This client's deployment target identifier.")
    deployment_id: UUID = Field(..., description="Deployment batch identifier (PRS 'Batch ID').")
    status: DeploymentStatus = Field(..., description="Current per-client deployment status (Pending).")
    created_at: datetime = Field(..., description="Timestamp this deployment target was created.")
    package: DeploymentPollPackageDetail = Field(
        ..., description="The approved repository package to be installed."
    )


class DeploymentPollResponse(BaseModel):
    """
    Response body for ``GET /api/agent/deployments/poll`` (FR-009).

    ``has_deployment`` is ``False`` and ``deployment`` is ``None`` when
    the polling client has no pending deployment (FR-009 Alternative Flow:
    "No deployment exists... the server returns a 'No Pending Deployment'
    response") - modeled as a normal ``200 OK`` response with an empty
    payload rather than a ``404``, since "nothing to do right now" is an
    expected, routine polling outcome for a Client Agent, not an error
    condition.
    """

    has_deployment: bool = Field(
        ..., description="True if a pending deployment was found for the authenticated client."
    )
    deployment: Optional[DeploymentPollTargetResponse] = Field(
        default=None, description="The pending deployment's details, or null if none exists."
    )
