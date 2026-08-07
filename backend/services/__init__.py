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

Together, AuthService and ClientAuthService implement the SAD's single
"Authentication Module" (Section 9.4), which covers FR-002, FR-019, and
FR-020; they are split into two classes/files per FR/domain rather than
one large class, per the Single Responsibility principle already applied
throughout this package (SAD Section 10.14).

Remaining services (Inventory, Repository, Deployment, Configuration) are
added by the tickets that introduce their respective domains (INV-*,
REP-*, DEPLOY-*, SYS-*).
"""