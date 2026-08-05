"""
Repository layer package (data access).

Per the Repository Pattern (SAD Section 5.4, Section 11), repositories in
this package encapsulate all SQLAlchemy query logic and expose CRUD-style
operations to the Service Layer. They contain no business rules.

Implemented so far:
    * AdministratorRepository (AUTH-001)
    * AdministratorSessionRepository (AUTH-001)
    * AuditLogRepository (AUTH-001)
    * ClientRepository (AUTH-002) - currently only `get_by_api_key_hash`;
      CLIENT-001 will extend it with registration/update/listing methods.

Remaining repositories (SoftwareInventory, RepositoryPackage, Deployment,
DeploymentTarget) are added by the tickets that introduce their
respective domains (INV-*, REP-*, DEPLOY-*).
"""
