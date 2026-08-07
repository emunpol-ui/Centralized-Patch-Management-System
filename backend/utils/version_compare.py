"""
Version comparison utilities (FR-007 Software Version Comparison).

Implements the "Software Matching Rules" and "Version Comparison Rules"
defined in PRS Section 4.3 FR-007, as pure, stateless helper functions
with no database or ORM dependency, so they can be unit-tested and reused
independently of ``backend.services.version_comparison_service.
VersionComparisonService``, which is the only current caller.

--------------------------------------------------------------------------
FR-007 Software Matching Rules implemented here:

    * Leading/trailing whitespace shall be trimmed.
    * Comparison shall be case-insensitive.
    * Common architecture suffixes (e.g., "(64-bit)", "(32-bit)") shall
      be removed before comparison.
    * Where available, software publisher shall additionally be
      considered to reduce false matches between similarly named
      applications from different vendors. ``normalize_publisher`` below
      provides the same trim/case-fold normalization for this purpose;
      it is not currently invoked by ``VersionComparisonService`` because
      ``RepositoryPackage`` (the repository-side match target) has no
      publisher column in the existing schema - see the design note on
      that service's ``_select_best_match`` - but is provided here as a
      general-purpose helper for any future caller that compares two
      publisher-bearing records (e.g. a future repository schema change).

FR-007 Version Comparison Rules implemented here:

    * A version string shall be parsed as period-delimited numeric
      segments (e.g., MAJOR.MINOR.BUILD.REVISION).
    * Segments shall be compared numerically, left to right; a
      higher-order segment takes precedence over lower-order segments.
    * If a version string cannot be parsed into numeric segments, the
      associated software shall be classified as Not Managed - callers
      must treat ``None`` from ``compare_versions``/``parse_version``
      accordingly and must never assume Up-to-Date on a parse failure.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# "Common architecture suffixes (e.g., '(64-bit)', '(32-bit)') shall be
# removed before comparison." Matches only a trailing suffix so that a
# legitimate architecture token embedded elsewhere in a name is left
# untouched.
_ARCH_SUFFIX_PATTERN = re.compile(r"\s*\((?:32|64)-bit\)\s*$", re.IGNORECASE)

# A version *segment* must be composed only of digits; anything else
# (letters, hyphens, pre-release tags, empty segments, etc.) makes the
# whole version string unparseable per FR-007.
_NUMERIC_SEGMENT_PATTERN = re.compile(r"^\d+$")


def normalize_software_name(name: str) -> str:
    """
    Normalize a software name for FR-007 matching purposes: trim
    leading/trailing whitespace, strip a trailing architecture suffix
    such as ``(64-bit)`` or ``(32-bit)``, then case-fold for
    case-insensitive comparison.

    ``casefold`` (rather than ``lower``) is used for the same reason it
    is used elsewhere in this codebase (see
    ``backend.services.inventory_service._normalize_key``): it is the
    more thorough Unicode-aware case-insensitive comparison primitive.
    """
    trimmed = name.strip()
    without_arch_suffix = _ARCH_SUFFIX_PATTERN.sub("", trimmed).strip()
    return without_arch_suffix.casefold()


def normalize_publisher(publisher: Optional[str]) -> Optional[str]:
    """
    Normalize a publisher name for FR-007 matching purposes (trim +
    case-fold), or ``None`` if ``publisher`` is ``None`` or blank.

    A blank/whitespace-only publisher is treated the same as a missing
    one, consistent with how ``backend.schemas.inventory.
    SoftwareInventoryItem`` already normalizes blank optional fields to
    ``None`` on upload.
    """
    if publisher is None:
        return None
    trimmed = publisher.strip()
    return trimmed.casefold() if trimmed else None


def parse_version(version: str) -> Optional[Tuple[int, ...]]:
    """
    Parse a version string into a tuple of numeric segments (FR-007:
    "A version string shall be parsed as period-delimited numeric
    segments").

    Returns ``None`` if the string is empty/blank, or if any
    period-delimited segment is not composed entirely of digits (e.g.
    ``"1.2.3-beta"``, ``"N/A"``, ``""``). Callers must treat ``None`` as
    "unparseable" per FR-007, not as version ``0``.
    """
    if not version or not version.strip():
        return None

    segments = version.strip().split(".")
    parsed_segments: list[int] = []
    for raw_segment in segments:
        segment = raw_segment.strip()
        if not _NUMERIC_SEGMENT_PATTERN.match(segment):
            return None
        parsed_segments.append(int(segment))

    return tuple(parsed_segments) if parsed_segments else None


def compare_versions(installed_version: str, approved_version: str) -> Optional[int]:
    """
    Compare an installed version string against an approved repository
    version string (FR-007 Version Comparison Rules).

    Returns:
        ``-1`` if ``installed_version`` is older than ``approved_version``.
        ``0`` if the two versions are equal.
        ``1`` if ``installed_version`` is newer than ``approved_version``.
        ``None`` if either string cannot be parsed into numeric segments
        (FR-007: the associated software "shall be classified as Not
        Managed ... it shall not be assumed to be Up-to-Date").

    Version tuples of unequal length are compared with the shorter one
    treated as zero-padded on the right (e.g. ``"1.2"`` == ``"1.2.0"``).
    This is a direct, natural extension of "compared numerically, left to
    right" for versions with differing segment counts, and is not
    prohibited by FR-007.
    """
    installed_segments = parse_version(installed_version)
    approved_segments = parse_version(approved_version)
    if installed_segments is None or approved_segments is None:
        return None

    length = max(len(installed_segments), len(approved_segments))
    padded_installed = installed_segments + (0,) * (length - len(installed_segments))
    padded_approved = approved_segments + (0,) * (length - len(approved_segments))

    if padded_installed < padded_approved:
        return -1
    if padded_installed > padded_approved:
        return 1
    return 0
