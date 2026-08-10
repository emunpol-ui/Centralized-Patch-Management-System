"""
CPMS Client Agent.

A standalone Python application, separate from the ``backend`` package,
installed on managed Windows computers (SAD Section 12). It does not
import from or depend on ``backend`` - the two communicate exclusively
over the REST API (PRS Chapter 5 / Appendix B).

Introduced by INV-001 (Software Inventory Collection), the first ticket
with a Client Agent-side deliverable:
    * ``agent.scanner`` - Windows Registry scanning and inventory
      serialization (FR-004).
    * ``agent.communication`` - authenticated HTTP upload to the CPMS
      Server (FR-005).
    * ``agent.config`` - Client Agent configuration (server URL, API key).

Run as ``python -m agent.main`` from the project root.

--------------------------------------------------------------------------
DEPLOY-003 ADDITION

Two further packages implement installer download and silent installation
(FR-010, FR-011):
    * ``agent.communication.deployment_client`` - authenticated HTTP calls
      to poll for a pending deployment (FR-009, reused from DEPLOY-002's
      server-side endpoint) and download its installer (FR-010).
    * ``agent.installer`` - SHA-256 checksum verification and direct
      (non-shell) silent installer process execution (FR-011).
    * ``agent.deployment`` - orchestrates the full poll -> download ->
      verify -> execute cycle. Run as ``python -m agent.deployment.manager``.

Deployment status reporting (FR-012) back to the server remains out of
scope for this package until DEPLOY-004 is implemented.
--------------------------------------------------------------------------
"""