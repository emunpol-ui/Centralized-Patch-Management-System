"""
Pydantic schema (DTO) package.

Per the DTO Pattern (SAD Section 5.8), schemas in this package define the
public request/response contract of the REST API.

Implemented so far:
    * auth.py (AUTH-001) - administrator login request/response schemas.
    * client.py (CLIENT-001) - client registration request schema.

Remaining schemas (inventory, repository, deployment) are added by the
tickets that introduce their respective endpoints (INV-*, REP-*,
DEPLOY-*).
"""
