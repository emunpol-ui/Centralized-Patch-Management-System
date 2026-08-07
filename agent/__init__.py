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
"""
