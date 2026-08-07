"""
Client Agent entry point - Inventory Collection (INV-001).

Ties together the Registry scanner, inventory serializer, and upload
client implemented for this ticket into a single, manually-runnable
command, run from the project root:

    python -m agent.main

This intentionally does not integrate with a Scheduler Module yet (SAD
Section 12.11 documents one, but it is not part of INV-001's deliverables
per the Backlog - "Windows Registry scanner", "Inventory serialization",
"Upload endpoint", "Inventory storage" - none of which mention recurring
execution). Running this script once performs exactly one scan-and-upload
cycle, sufficient to demonstrate this ticket's acceptance criteria
("Installed software detected", "Inventory uploaded successfully").
Recurring/background execution is expected to be introduced by a future
ticket alongside the other scheduled agent operations (heartbeat,
deployment polling) the SAD documents as sharing one Scheduler Module.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from agent.communication.inventory_client import InventoryUploadError, upload_inventory
from agent.config.settings import get_agent_settings
from agent.scanner.inventory_collector import collect_installed_software

_LOG_DIR = Path(__file__).resolve().parent / "logs"
logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """
    Configure Client Agent logging: console output plus a rotating-in-name
    (single, append-mode) file under ``agent/logs/`` - the location
    documented for client-side log files in SAD Section 7.5 / 12.13.

    Kept local to this entry point rather than a separate logging module,
    since no other agent component needs logging configuration of its
    own yet - each module simply calls ``logging.getLogger(__name__)``
    and relies on this root configuration.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(_LOG_DIR / "agent.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    """Run one scan-and-upload inventory cycle. Returns a process exit code."""
    _configure_logging()
    settings = get_agent_settings()

    if not settings.api_key:
        logger.error(
            "AGENT_API_KEY is not configured. Set it to a Client API key issued via "
            "POST /api/admin/keys and claimed via POST /api/register before running the agent."
        )
        return 1

    logger.info("Starting software inventory scan...")
    try:
        items = collect_installed_software()
    except RuntimeError as exc:
        logger.error("Inventory scan failed: %s", exc)
        return 1

    logger.info("Uploading %d software inventory record(s) to %s...", len(items), settings.server_url)
    try:
        result = upload_inventory(
            items,
            server_url=settings.server_url,
            api_key=settings.api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
    except InventoryUploadError as exc:
        logger.error("Inventory upload failed: %s", exc)
        return 1

    logger.info("Inventory upload complete: %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
