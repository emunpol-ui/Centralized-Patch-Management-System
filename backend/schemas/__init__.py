"""
Pydantic schema (DTO) package.

Per the DTO Pattern (SAD Section 5.8), schemas in this package define the
public request/response contract of the REST API.

Implemented so far (CPM-003):
    * auth.py - administrator login request/response schemas.

Remaining schemas (client registration, inventory, repository,
deployment) are added by the tickets that introduce their respective
endpoints (CLIENT-*, INV-*, REP-*, DEPLOY-*).
"""
