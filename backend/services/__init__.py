"""
Service layer package (business logic).

Per the Service Layer Pattern (SAD Section 5.5, Section 10), services in
this package coordinate repositories and enforce business rules. Routers
(API Layer) never call repositories directly - they call services.

Implemented so far (CPM-003):
    * AuthService - administrator authentication and session lifecycle.

Remaining services (Client, Inventory, Repository, Deployment,
Configuration) are added by the tickets that introduce their respective
domains (CLIENT-*, INV-*, REP-*, DEPLOY-*, SYS-*).
"""
