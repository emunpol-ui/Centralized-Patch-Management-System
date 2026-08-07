"""
Installer file storage utilities (FR-006 Software Repository Management -
"Upload Validation Rules").

Pure, database-independent helpers for validating an uploaded installer's
extension, generating a server-controlled storage filename, and streaming
the file to disk while computing its SHA-256 checksum. No FastAPI, ORM, or
business-logic concerns belong here - only filesystem/hashing primitives -
mirroring the separation already established by
``backend/utils/version_compare.py`` (pure rule functions, unit-testable
without a database session).

--------------------------------------------------------------------------
FR-006 Upload Validation Rules implemented here:

    * "Only files with an extension of .exe or .msi shall be accepted,
      consistent with the Installer Type field." -> ``validate_extension``.
    * "Uploaded files shall not exceed the configured maximum installer
      upload size." -> ``save_and_hash``'s ``max_size_bytes`` enforcement.
    * "The server shall generate a new, sanitized internal filename for
      storage; the client-supplied filename shall not be trusted for
      storage or path construction." -> ``generate_storage_filename``
      (a fresh UUID4-based name; the client-supplied ``original_filename``
      is used only to validate the extension, never as part of the
      resulting path).
    * "Installer files shall be stored in a directory that is not
      directly accessible via the web server." -> enforced operationally
      by ``Settings.REPOSITORY_DIR`` (backend/core/config.py) living
      outside ``backend/static/``, which is this application's only
      web-server-exposed directory.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import BinaryIO, Tuple

from backend.models.enums import InstallerType

# Extensions accepted per FR-006, keyed by the declared Installer Type.
_EXTENSION_BY_INSTALLER_TYPE = {
    InstallerType.EXE: ".exe",
    InstallerType.MSI: ".msi",
}

# Streamed in fixed-size chunks so that large installer files never need
# to be fully buffered in memory at once.
_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB


class InstallerFileError(ValueError):
    """
    Raised when an uploaded installer file fails an FR-006 validation
    rule (extension mismatch, oversized upload, or an empty file).

    Deliberately a plain ``ValueError`` subclass, not
    ``backend.core.exceptions.AppException``: this module has no FastAPI
    or HTTP-status concerns (per the module docstring). Callers in the
    Service Layer (``backend.services.repository_service.
    RepositoryService``) are responsible for translating this into the
    appropriate ``AppException`` subclass for the API response.
    """


def get_original_extension(original_filename: str | None) -> str:
    """
    Return the lowercase extension (including the leading dot) of
    ``original_filename``, or an empty string if absent/extension-less.
    """
    if not original_filename:
        return ""
    return Path(original_filename).suffix.lower()


def validate_extension(original_filename: str | None, installer_type: InstallerType) -> None:
    """
    Validate that ``original_filename``'s extension matches the declared
    ``installer_type`` (FR-006 Upload Validation Rules).

    Raises ``InstallerFileError`` if the extension is missing or does not
    match the expected ``.exe``/``.msi`` extension for ``installer_type``.
    """
    expected_extension = _EXTENSION_BY_INSTALLER_TYPE[installer_type]
    actual_extension = get_original_extension(original_filename)
    if actual_extension != expected_extension:
        raise InstallerFileError(
            f"Uploaded file extension '{actual_extension or '(none)'}' does not match the declared "
            f"installer type '{installer_type.value}' (expected '{expected_extension}')."
        )


def generate_storage_filename(installer_type: InstallerType) -> str:
    """
    Generate a new, sanitized, server-controlled filename for storage
    (FR-006: the client-supplied filename is never trusted for storage or
    path construction).

    A random UUID4 hex string guarantees the generated filename cannot
    collide with an existing one and contains no path separators or other
    characters that could be used for path traversal.
    """
    extension = _EXTENSION_BY_INSTALLER_TYPE[installer_type]
    return f"{uuid.uuid4().hex}{extension}"


def save_and_hash(
    source: BinaryIO,
    destination_dir: Path,
    filename: str,
    *,
    max_size_bytes: int,
) -> Tuple[int, str]:
    """
    Stream ``source`` to ``destination_dir / filename`` in fixed-size
    chunks, computing its SHA-256 checksum as it is written (FR-006
    functional behavior: "The server computes a SHA-256 checksum of the
    installer file" / "The installer is stored ... in the repository"),
    while enforcing ``max_size_bytes`` (FR-006 Upload Validation Rules /
    FR-018 "Maximum installer upload size").

    Returns ``(file_size, checksum_hex)``.

    ``destination_dir`` is created (including parent directories) if it
    does not already exist. If the source exceeds ``max_size_bytes``
    partway through, or turns out to be empty, the partially-written file
    is removed and ``InstallerFileError`` is raised - a partial or empty
    file must never be left in the repository, where a future Deployment
    Job (DEPLOY-*) could reference it.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / filename

    hasher = hashlib.sha256()
    total_size = 0

    try:
        with destination_path.open("wb") as output_file:
            while True:
                chunk = source.read(_CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise InstallerFileError(
                        f"Uploaded file exceeds the maximum allowed installer upload size "
                        f"of {max_size_bytes} bytes."
                    )
                hasher.update(chunk)
                output_file.write(chunk)

        if total_size == 0:
            raise InstallerFileError("Uploaded installer file is empty.")
    except Exception:
        destination_path.unlink(missing_ok=True)
        raise

    return total_size, hasher.hexdigest()
