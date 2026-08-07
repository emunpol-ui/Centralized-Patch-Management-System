"""
Windows Registry software scanner (client-side; FR-004 Software Inventory
Scan).

Enumerates installed applications from the standard Windows "Uninstall"
registry locations documented in PRS FR-004:

    * ``HKEY_LOCAL_MACHINE``, native (64-bit) view
    * ``HKEY_LOCAL_MACHINE``, ``WOW6432Node`` (32-bit-on-64-bit) view
    * ``HKEY_CURRENT_USER`` (per-user installs)

Only raw registry reads live in this module - normalization, date
parsing, deduplication, and JSON-ready serialization are the
responsibility of ``agent.scanner.inventory_collector`` (INV-001's
"Inventory serialization" deliverable), per the Single Responsibility
principle already applied throughout this codebase (SAD Section 10.14 /
12.4).

This module is Windows-only at *runtime* (the CPMS Client Agent is a
Windows-only component - Charter Section 9, PRS Section 2.5). ``winreg``
is imported defensively so the module remains import-safe (e.g. for
tooling, code review, or a non-Windows development machine); calling any
scan function on a platform without ``winreg`` raises ``RuntimeError``
immediately, rather than failing later with a confusing ``NameError``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only on non-Windows hosts
    winreg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

UNINSTALL_KEY_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


def _registry_locations() -> List[Tuple[int, int]]:
    """
    Return the (root hive, WOW64 access flag) pairs to scan (PRS FR-004:
    "querying the Uninstall registry keys under both HKEY_LOCAL_MACHINE
    and HKEY_CURRENT_USER, including the WOW6432Node view on 64-bit
    systems").

    Built lazily (rather than as a module-level constant) so importing
    this module never touches ``winreg`` attributes on a platform where
    it is unavailable.
    """
    return [
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),  # Native 64-bit applications
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),  # WOW6432Node - 32-bit applications
        (winreg.HKEY_CURRENT_USER, 0),  # Per-user installs
    ]


def _read_string_value(key: Any, name: str) -> Optional[str]:
    """Return a trimmed string registry value, or None if absent/empty."""
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_dword_value(key: Any, name: str) -> Optional[int]:
    """Return an integer (DWORD) registry value, or None if absent/invalid."""
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enumerate_subkey_names(key: Any) -> Iterator[str]:
    """Yield every immediate subkey name under an open registry key."""
    index = 0
    while True:
        try:
            yield winreg.EnumKey(key, index)
        except OSError:
            return
        index += 1


def _read_uninstall_entry(parent_key: Any, subkey_name: str) -> Optional[Dict[str, Any]]:
    """
    Read one Uninstall subkey and return a raw entry dict, or None if the
    subkey does not represent a user-facing installed application (missing
    display name, or explicitly marked as a system/OS component).
    """
    try:
        with winreg.OpenKey(parent_key, subkey_name) as subkey:
            display_name = _read_string_value(subkey, "DisplayName")
            if not display_name:
                return None
            if _read_dword_value(subkey, "SystemComponent") == 1:
                return None
            return {
                "software_name": display_name,
                "version": _read_string_value(subkey, "DisplayVersion") or "",
                "publisher": _read_string_value(subkey, "Publisher"),
                "install_date_raw": _read_string_value(subkey, "InstallDate"),
                "install_location": _read_string_value(subkey, "InstallLocation"),
            }
    except OSError as exc:
        logger.debug("Skipping unreadable Uninstall subkey '%s': %s", subkey_name, exc)
        return None


def scan_installed_software() -> List[Dict[str, Any]]:
    """
    Enumerate installed applications from every registry location required
    by FR-004 and return the raw (unnormalized, possibly duplicated)
    entries.

    Each entry is a dict with keys: ``software_name``, ``version``,
    ``publisher``, ``install_date_raw`` (a raw ``InstallDate`` string such
    as ``"20240115"``, or None), and ``install_location``. Normalization,
    date parsing, and deduplication happen in
    ``agent.scanner.inventory_collector.collect_installed_software``.

    Raises ``RuntimeError`` if called on a platform without ``winreg``
    (i.e. anywhere other than Windows).
    """
    if winreg is None:
        raise RuntimeError(
            "Windows Registry access is unavailable on this platform. "
            "The CPMS Client Agent's software scanner requires Windows."
        )

    entries: List[Dict[str, Any]] = []
    for hive, wow64_flag in _registry_locations():
        access = winreg.KEY_READ | wow64_flag
        try:
            with winreg.OpenKeyEx(hive, UNINSTALL_KEY_PATH, 0, access) as uninstall_key:
                for subkey_name in _enumerate_subkey_names(uninstall_key):
                    entry = _read_uninstall_entry(uninstall_key, subkey_name)
                    if entry is not None:
                        entries.append(entry)
        except FileNotFoundError:
            # This particular hive/view has no Uninstall key at all (e.g. a
            # 32-bit view on a machine with no 32-bit software installed).
            # Not an error - simply nothing to report from this location.
            logger.debug("No Uninstall key found for hive=%s wow64_flag=%s.", hive, wow64_flag)
        except OSError as exc:
            logger.warning(
                "Unable to read registry location (hive=%s, wow64_flag=%s): %s", hive, wow64_flag, exc
            )

    logger.info("Registry scan collected %d raw Uninstall entries.", len(entries))
    return entries
