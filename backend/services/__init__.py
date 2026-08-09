"""
Service layer package (business logic).

Per the Service Layer Pattern (SAD Section 5.5, Section 10), services in
this package coordinate repositories and enforce business rules. Routers
(API Layer) never call repositories directly - they call services.

Implemented so far:
    * AuthService (AUTH-001) - administrator authentication and session
      lifecycle.
    * ClientAuthService (AUTH-002; extended by CLIENT-001) - Client Agent
      API-key authentication, plus the FR-020 credential resolution and
      key-issuance logic FR-001 registration depends on.
    * ClientService (CLIENT-001) - FR-001 Client Registration business
      logic (create-or-update by Agent GUID).
    * HeartbeatService (CLIENT-002) - FR-003 Client Heartbeat business
      logic (last-seen timestamp + Online status updates).
    * InventoryService (INV-001) - FR-005 Software Inventory Upload
      business logic (insert / update / remove sync against the client's
      most recently uploaded inventory snapshot).
    * VersionComparisonService (INV-002) - FR-007 Software Version
      Comparison business logic (classifies each installed inventory
      item as Up-to-Date / Update Available / Not Managed against the
      approved repository catalog; computed on demand, not persisted -
      see that module's own design note).
    * RepositoryService (REP-001; extended by REP-002 with
      ``list_packages``/``get_package``/``deactivate_package``) - FR-006
      Software Repository Management business logic (installer
      extension/installer-type validation, duplicate-entry rejection,
      SHA-256 checksum computation, and package metadata persistence),
      plus FR-017 Repository Maintenance's listing/detail/deactivation
      operations.
    * DeploymentService (DEPLOY-001) - FR-008 Deployment Job Creation /
      FR-009 Deployment Job Retrieval targeting business logic (package
      approval validation, target client existence validation, Business
      Rule 9 "one active deployment per client" enforcement, and atomic
      batch + per-client target creation). Composes ``RepositoryService``
      to reuse its existing package lookup/validation rather than
      duplicating it.

Together, AuthService and ClientAuthService implement the SAD's single
"Authentication Module" (Section 9.4), which covers FR-002, FR-019, and
FR-020; they are split into two classes/files per FR/domain rather than
one large class, per the Single Responsibility principle already applied
throughout this package (SAD Section 10.14).

Remaining services (Configuration) are added by the tickets that
introduce their respective domains (SYS-*).
"""