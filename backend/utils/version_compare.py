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
      applications from different vendors. ``normalize_publisher``
      provides the trim/case-fold normalization for this purpose, and
      ``software_identity_matches`` combines it with
      ``normalize_software_name`` into the single predicate shared by
      repository duplicate-detection (``RepositoryPackageRepository``)
      and inventory-to-repository matching
      (``VersionComparisonService``), so the two call sites can never
      disagree on what "the same software" means.

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
_ARCH_SUFFIX_PATTERN = re.compile(
    r"\s*\((?:32|64)-bit\)\s*$",
    re.IGNORECASE,
)

_TRAILING_VERSION_PATTERN = re.compile(
    r"\s+\d+(?:\.\d+)+\s*$"
)

# A version *segment* must be composed only of digits; anything else
# (letters, hyphens, pre-release tags, empty segments, etc.) makes the
# whole version string unparseable per FR-007.
_NUMERIC_SEGMENT_PATTERN = re.compile(r"^\d+$")


def normalize_software_name(name: str) -> str:
    """
    Normalize a software name for FR-007 matching purposes.

    Normalization performs the following operations in order:

    1. Trim leading/trailing whitespace.
    2. Strip a trailing architecture suffix such as ``(64-bit)`` or
       ``(32-bit)``.
    3. Strip a trailing dotted numeric version token such as ``3.13.14``
       or ``3.14.7`` when it is part of the software display name.
    4. Case-fold for case-insensitive comparison.

    The actual installed/approved version remains in the separate
    version fields and is compared by ``compare_versions()``.
    """
    trimmed = name.strip()

    without_arch_suffix = _ARCH_SUFFIX_PATTERN.sub(
        "",
        trimmed,
    ).strip()

    without_trailing_version = _TRAILING_VERSION_PATTERN.sub(
        "",
        without_arch_suffix,
    ).strip()

    return " ".join(without_trailing_version.split()).casefold()


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


def software_identity_matches(
    name_a: str,
    publisher_a: Optional[str],
    name_b: str,
    publisher_b: Optional[str],
) -> bool:
    """
    Decide whether two software records refer to the same software
    identity, per FR-007's Software Matching Rules.

    Rules applied (PRS FR-007 "Software Matching Rules"):

        * Names are always compared via ``normalize_software_name``
          (trim, strip a trailing architecture suffix, case-fold).
        * When *both* records report a publisher, the normalized
          publishers must also match - this is the "where available ...
          to reduce false matches between similarly named applications
          from different vendors" case.
        * When *either* record's publisher is missing/blank, matching
          falls back to name only, since there is nothing to compare -
          FR-007 does not require publisher, only that it be considered
          "where available".

    This is the single predicate shared by repository duplicate
    detection (``RepositoryPackageRepository.get_active_conflict``,
    ``list_approved_for_identity``) and inventory-to-repository matching
    (``VersionComparisonService``), so "the same software" means exactly
    the same thing in both places.
    """
    if normalize_software_name(name_a) != normalize_software_name(name_b):
        return False

    norm_publisher_a = normalize_publisher(publisher_a)
    norm_publisher_b = normalize_publisher(publisher_b)
    if norm_publisher_a is None or norm_publisher_b is None:
        return True
    return norm_publisher_a == norm_publisher_b


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


def same_version(version_a: str, version_b: str) -> bool:
    """
    Decide whether two version strings represent the same version, using
    the same numeric, period-delimited comparison rules as
    ``compare_versions`` (so, e.g., ``"4.15"`` and ``"4.15.0"`` are the
    same version here exactly as they are for update-status purposes).

    Falls back to a trimmed, case-sensitive exact string match when
    either string cannot be parsed into numeric segments, so two
    installers legitimately targeting the same unparseable version
    string (e.g. a vendor build tag) are still recognized as a
    duplicate - the same "duplicate repository entries violate
    repository rules" condition FR-006 guards against - without
    silently treating two *different* unparseable strings as equal.
    """
    comparison = compare_versions(version_a, version_b)
    if comparison is not None:
        return comparison == 0
    return version_a.strip() == version_b.strip()
