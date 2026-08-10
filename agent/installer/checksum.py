"""
Installer checksum verification (client-side; DEPLOY-003, FR-011 Silent
Software Installation - "the Client Agent computes the SHA-256 checksum
of the downloaded installer file and compares it to the checksum provided
by the server").

Deliberately pure and dependency-free (aside from the standard library),
mirroring the separation already established server-side by
``backend.utils.file_storage`` - filesystem/hashing primitives only, no
network or process-execution concerns.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Matches the server's own streaming chunk size
# (``backend.utils.file_storage._CHUNK_SIZE_BYTES``) so neither side of
# the checksum computation needs to buffer a large installer file fully
# in memory.
_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB


def compute_sha256(path: Path) -> str:
    """Compute and return the lowercase hex SHA-256 digest of the file at ``path``."""
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_checksum(path: Path, expected_checksum: str) -> bool:
    """
    Return ``True`` only if the SHA-256 checksum of the file at ``path``
    matches ``expected_checksum`` (case-insensitive comparison, since hex
    digests are conventionally lowercase but this must not be assumed of
    every value the server might ever store).

    A mismatch here is a definitive security/integrity failure (FR-011:
    "If the checksums do not match, the installer shall not be executed
    and the deployment shall be reported as Failed") - callers must never
    retry a checksum failure as though it were a transient network error;
    the caller is responsible for surfacing it as a definitive deployment
    failure rather than attempting the download again.
    """
    actual_checksum = compute_sha256(path)
    return actual_checksum.lower() == expected_checksum.lower()


__all__ = ["compute_sha256", "verify_checksum"]
