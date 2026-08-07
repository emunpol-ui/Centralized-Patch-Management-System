"""
Repository layer package (data access).

Per the Repository Pattern (SAD Section 5.4, Section 11), repositories in
this package encapsulate all SQLAlchemy query logic and expose CRUD-style
operations to the Service Layer. They contain no business rules.

Implemented so far:
    * AdministratorRepository (AUTH-001)
    * AdministratorSessionRepository (AUTH-001)
    * AuditLogRepository (AUTH-001)
    * ClientRepository (AUTH-002; extended by CLIENT-001 with
      `get_by_agent_guid`, `create`, and `update_registration`)
    * ClientProvisioningKeyRepository (CLIENT-001) - the minimal FR-020
      slice needed to unblock FR-001 registration; see
      `backend/models/client_provisioning_key.py`.
    * SoftwareInventoryRepository (INV-001) - FR-005 inventory persistence
      (create / update / delete / list-for-client).

Remaining repositories (RepositoryPackage, Deployment, DeploymentTarget)
are added by the tickets that introduce their respective domains (REP-*,
DEPLOY-*).
"""