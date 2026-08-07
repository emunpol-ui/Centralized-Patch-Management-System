"""
Inventory collection & serialization (client-side; FR-004 Software
Inventory Scan "Inventory Data Collected" + INV-001's "Inventory
serialization" deliverable).

Takes the raw registry entries produced by
``agent.scanner.registry_scanner.scan_installed_software`` and turns them
into the normalized, deduplicated, JSON-ready list of dicts the CPMS
Server's ``POST /api/agent/inventory/upload`` endpoint (FR-005) expects -
i.e. the same shape as ``backend.schemas.inventory.SoftwareInventoryItem``
on the server side, kept in sync by convention rather than shared code
(the Client Agent is a separate, standalone Python application - SAD
Section 12 - and does not import ``backend`` code).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from agent.scanner.registry_scanner import scan_installed_software

logger = logging.getLogger(__name__)

# Windows' Uninstall registry `InstallDate` value is documented as an
# 8-digit `YYYYMMDD` string.
_INSTALL_DATE_FORMAT = "%Y%m%d"


def _parse_install_date(raw_value: Optional[str]) -> Optional[str]:
    """
    Parse a raw Windows Uninstall ``InstallDate`` value into an ISO-8601
    date string (``YYYY-MM-DD``) suitable for JSON upload.

    Returns None if the value is missing or does not match the expected
    format, rather than raising - a malformed or absent install date must
    never block the rest of that software's inventory record from being
    collected and uploaded (FR-004 documents "Installation Date" itself
    as optional).
    """
    if not raw_value:
        return None
    try:
        parsed: date = datetime.strptime(raw_value, _INSTALL_DATE_FORMAT).date()
    except ValueError:
        logger.debug("Ignoring unparsable InstallDate value: %r", raw_value)
        return None
    return parsed.isoformat()


def collect_installed_software() -> List[Dict[str, Any]]:
    """
    Scan the local Windows computer and return the deduplicated,
    JSON-ready software inventory (FR-004 steps 2-6).

    Deduplication key: the software name (trimmed, case-insensitive)
    together with its version (also case-insensitive). The same installed
    application can legitimately be reported more than once by
    ``scan_installed_software`` - e.g. an identical Uninstall subkey
    occasionally mirrored between the native and WOW6432Node registry
    views - and FR-004 explicitly requires such duplicates to be filtered
    "where applicable" before upload. Two entries sharing a name but
    reporting genuinely different versions are kept as distinct records
    rather than collapsed, since that scenario reflects real,
    independently-installed software (e.g. side-by-side runtime versions)
    rather than a duplicate registry view of the same installation.

    Raises ``RuntimeError`` (propagated from ``scan_installed_software``)
    if called on a platform without Windows Registry access.
    """
    raw_entries = scan_installed_software()

    deduplicated: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for raw_entry in raw_entries:
        name = str(raw_entry.get("software_name") or "").strip()
        if not name:
            continue
        version = str(raw_entry.get("version") or "").strip()
        key = (name.casefold(), version.casefold())
        if key in deduplicated:
            continue
        deduplicated[key] = {
            "software_name": name,
            "version": version,
            "publisher": (raw_entry.get("publisher") or "").strip() or None,
            "install_date": _parse_install_date(raw_entry.get("install_date_raw")),
            "install_location": (raw_entry.get("install_location") or "").strip() or None,
        }

    items = list(deduplicated.values())
    logger.info(
        "Collected %d unique installed software records (from %d raw registry entries).",
        len(items),
        len(raw_entries),
    )
    return items
