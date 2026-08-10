"""
Client Agent configuration loader (INV-001).

The Client Agent is a separate, standalone Python application from the
CPMS Server (SAD Section 12) and therefore does not reuse
``backend.core.config.Settings`` - it has its own, much smaller
configuration surface: where the server is, and which API key to
authenticate with. Values are read from environment variables and,
optionally, a ``.env`` file at the project root (``python-dotenv``,
already a project dependency per ``requirements.txt`` since CORE-001),
consistent with this project's "Configuration over Hardcoding" principle
(SAD Section 2.5, Charter Section 11).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root directory (two levels up from this file:
# agent/config/settings.py -> agent/config -> agent -> <project root>)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Loading here (module import time) mirrors `backend.core.config`'s own
# approach of resolving configuration once, near the top of the module,
# rather than repeating the lookup on every call. `override=False` means
# real environment variables (e.g. set by a Windows Scheduled Task - PRS
# Section 8 "Initial deployment") always take precedence over `.env`.
load_dotenv(_PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class AgentSettings:
    """Strongly-typed Client Agent configuration."""

    server_url: str
    api_key: str
    request_timeout_seconds: float

    # --- DEPLOY-003 additions (FR-010/FR-011) -----------------------------
    # Installer download HTTP timeout is kept separate from
    # `request_timeout_seconds` (used for the small, fast JSON calls -
    # registration, heartbeat, inventory, polling) since installer files
    # can be substantially larger and slower to transfer.
    download_timeout_seconds: float
    # Number of installer *download* attempts before giving up (FR-010
    # Error Conditions: "The Client Agent shall retry the download
    # according to the configured retry policy"). Deliberately does NOT
    # apply to a checksum mismatch (FR-011) - that is a definitive
    # integrity failure, never retried.
    download_max_retries: int
    download_retry_delay_seconds: float
    # Ceiling on how long a single silent installation may run before
    # being forcibly terminated and reported as failed (FR-011 Error
    # Conditions: "Installation times out").
    installer_execution_timeout_seconds: float


def get_agent_settings() -> AgentSettings:
    """
    Build ``AgentSettings`` from the current environment.

    ``AGENT_API_KEY`` is intentionally not given a non-empty default - a
    Client Agent with no key configured must fail loudly and immediately
    (see ``agent.main.main``) rather than silently attempt an
    unauthenticated request that the server would reject anyway (FR-002).
    """
    return AgentSettings(
        server_url=os.getenv("AGENT_SERVER_URL", "http://localhost:8000").strip(),
        api_key=os.getenv("AGENT_API_KEY", "").strip(),
        request_timeout_seconds=float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "30")),
        download_timeout_seconds=float(os.getenv("AGENT_DOWNLOAD_TIMEOUT_SECONDS", "120")),
        download_max_retries=int(os.getenv("AGENT_DOWNLOAD_MAX_RETRIES", "3")),
        download_retry_delay_seconds=float(os.getenv("AGENT_DOWNLOAD_RETRY_DELAY_SECONDS", "5")),
        installer_execution_timeout_seconds=float(
            os.getenv("AGENT_INSTALLER_EXECUTION_TIMEOUT_SECONDS", "600")
        ),
    )