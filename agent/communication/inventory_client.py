"""
Inventory upload client (client-side; INV-001's "Inventory upload client"
deliverable).

Uploads the software inventory collected by
``agent.scanner.inventory_collector.collect_installed_software`` to the
CPMS Server's ``POST /api/agent/inventory/upload`` endpoint (FR-005),
authenticated using the same ``Authorization: Bearer <api_key>`` scheme
the server's existing AUTH-002 dependency (``require_client_api_key``)
already enforces for every route under ``/api/agent/*`` - no new
server-side authentication mechanism is introduced by this ticket.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

INVENTORY_UPLOAD_PATH = "/api/agent/inventory/upload"


class InventoryUploadError(Exception):
    """Raised when the server rejects, or cannot be reached for, an inventory upload."""


def upload_inventory(
    items: List[Dict[str, Any]],
    *,
    server_url: str,
    api_key: str,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Upload a collected software inventory to the CPMS Server.

    ``items`` must already be in the JSON-ready shape produced by
    ``agent.scanner.inventory_collector.collect_installed_software``.
    Returns the parsed JSON response body on success (HTTP 200).

    Raises ``InventoryUploadError`` if the request cannot be sent (network
    failure), if the server responds with a non-success status code, or if
    the response body is not valid JSON. Per FR-005's own error-handling
    requirement ("the Client Agent shall retain the inventory locally and
    retry the upload according to the configured retry policy"), retry
    scheduling itself is the caller's responsibility (the Scheduler
    Module - SAD Section 12.11 - not yet implemented); this function
    performs a single upload attempt and reports success or failure.
    """
    url = server_url.rstrip("/") + INVENTORY_UPLOAD_PATH
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"items": items}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        logger.error("Inventory upload to %s failed: %s", url, exc)
        raise InventoryUploadError(f"Unable to reach CPMS Server at {url}: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        logger.error(
            "Inventory upload to %s returned a non-JSON response (status=%d).", url, response.status_code
        )
        raise InventoryUploadError(
            f"CPMS Server returned an unreadable response (status={response.status_code})."
        ) from exc

    if not response.ok:
        message = body.get("message") if isinstance(body, dict) else None
        logger.error("Inventory upload to %s rejected (status=%d): %s", url, response.status_code, message)
        raise InventoryUploadError(message or f"Inventory upload rejected (status={response.status_code}).")

    logger.info("Inventory upload to %s succeeded (status=%d).", url, response.status_code)
    return body
