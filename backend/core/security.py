"""
Password hashing and secure token utilities.

Provides the cryptographic primitives used by the authentication module
(CPM-003):

    * Administrator password hashing/verification, using Passlib's bcrypt
      backend (SAD Section 6.8 - "Passlib provides password hashing for
      administrator authentication... secure cryptographic hashes are
      stored within the database").
    * Opaque, cryptographically random token generation for session
      identifiers and CSRF tokens, plus a one-way hash used to store
      session tokens at rest (mirroring the pattern already established
      for ``Client.api_key_hash`` in CPM-002 - the raw token is only ever
      held by the client, never persisted).

No FastAPI, database, or business-logic concerns belong in this module -
only stateless cryptographic helpers.
"""

from __future__ import annotations

import hashlib
import secrets

from passlib.context import CryptContext

# A single, process-wide CryptContext. "bcrypt" is the only configured
# scheme (per the SAD's technology stack); `deprecated="auto"` means any
# future scheme added ahead of "bcrypt" in this list would automatically
# be treated as the preferred one, with existing bcrypt hashes still
# verifiable and flagged for re-hashing via `needs_update`.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# A fixed, valid bcrypt hash of a value nobody will ever supply as a real
# password. Verifying against this when a username lookup fails keeps the
# response time of a failed login (unknown user) statistically similar to
# a failed login (wrong password for a known user), reducing the
# usefulness of timing as a username-enumeration side channel.
_DUMMY_HASH = _pwd_context.hash("cpms-dummy-hash-not-a-real-password")

# Number of random bytes used for session/CSRF tokens. 32 bytes (256 bits)
# of entropy is well beyond what is brute-forceable and is the same
# strength commonly used for session identifiers in production systems.
_TOKEN_BYTES = 32


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage in ``Administrator.password_hash``."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """
    Verify a plaintext password against a stored hash.

    If ``password_hash`` is ``None`` (e.g. the caller is verifying against
    a username that does not exist), verification is performed against a
    fixed dummy hash instead of short-circuiting to ``False`` immediately,
    so the call still takes approximately the same amount of time as a
    genuine verification (see ``_DUMMY_HASH`` above).
    """
    return _pwd_context.verify(plain_password, password_hash or _DUMMY_HASH)


def generate_token() -> str:
    """
    Generate a new, cryptographically random, URL-safe opaque token.

    Used for both session identifiers and CSRF tokens. The raw value
    returned here is what is placed in a cookie; it is never stored
    server-side as-is (see ``hash_token``).
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(raw_token: str) -> str:
    """
    Compute a SHA-256 hex digest of a raw token, for at-rest storage.

    A fast hash (rather than bcrypt) is appropriate here: unlike a
    password, a session token already has 256 bits of entropy and is not
    memorized or reused by a human, so it carries no risk of dictionary or
    rainbow-table attack. The purpose of hashing it is solely to ensure
    that a database compromise does not directly hand over usable session
    tokens (mirroring ``Client.api_key_hash`` from CPM-002).
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
