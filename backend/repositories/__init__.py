"""
Repository layer package (data access).

Per the Repository Pattern (SAD Section 5.4, Section 11), repositories in
this package encapsulate all SQLAlchemy query logic and expose CRUD-style
operations to the Service Layer. They contain no business rules.

Implemented so far (CPM-003):
    * AdministratorRepository
    * AdministratorSessionRepository
    * AuditLogRepository

Remaining repositories (Client, SoftwareInventory, RepositoryPackage,
Deployment, DeploymentTarget) are added by the tickets that introduce
their respective domains (CLIENT-*, INV-*, REP-*, DEPLOY-*).
"""
