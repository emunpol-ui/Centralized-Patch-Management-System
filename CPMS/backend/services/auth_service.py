"""
Authentication service.

Contains the business logic for administrator authentication (FR-019) and
session lifecycle management (NFR-028), per the Service Layer Pattern
(SAD Section 5.5, Section 10.5 "Authentication Service"). Coordinates the
Administrator, AdministratorSession, and AuditLog repositories; enforces
no rules beyond what FR-019/NFR-028 require ("do not implement
authorization beyond what is required").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.exceptions import AppException
from backend.core.security import generate_token, hash_password, hash_token, verify_password
from backend.models.administrator import Administrator
from backend.models.administrator_session import AdministratorSession
from backend.models.enums import AuditSeverity
from backend.repositories.administrator_repository import AdministratorRepository
from backend.repositories.administrator_session_repository import AdministratorSessionRepository
from backend.repositories.audit_log_repository import AuditLogRepository


class AuthenticationError(AppException):
    """Raised when login credentials or a session/CSRF token are invalid."""

    def __init__(self, message: str = "Authentication failed.", status_code: int = 401) -> None:
        super().__init__(message, status_code=status_code)


class AuthService:
    """
    Administrator authentication and session lifecycle.

    A single instance is stateless and safe to reuse across requests; all
    per-request state (the database session) is passed in explicitly by
    callers, consistent with the Repository/Service layering used
    throughout the backend.
    """

    def __init__(
        self,
        administrator_repository: AdministratorRepository | None = None,
        session_repository: AdministratorSessionRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
        session_timeout: timedelta | None = None,
    ) -> None:
        self._administrators = administrator_repository or AdministratorRepository()
        self._sessions = session_repository or AdministratorSessionRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()
        self._session_timeout = session_timeout or timedelta(minutes=30)

    # --- Credential management (used by scripts/create_admin.py) -----------

    def hash_new_password(self, plain_password: str) -> str:
        """Hash a plaintext password for storing a new/updated Administrator."""
        return hash_password(plain_password)

    # --- Login / logout -----------------------------------------------------

    def authenticate(self, db: Session, *, username: str, password: str) -> Administrator:
        """
        Verify a username/password pair (FR-019).

        Always performs a password verification, even when ``username``
        does not match any administrator, so that failed-login response
        timing does not reveal whether the username exists (see
        ``backend.core.security.verify_password``). Records the attempt
        in the audit log (FR-019 acceptance criterion: "Authentication
        attempts, successful and failed, are recorded in the audit log")
        regardless of outcome, then raises ``AuthenticationError`` on
        failure or returns the ``Administrator`` on success.
        """
        administrator = self._administrators.get_by_username(db, username)
        password_ok = verify_password(password, administrator.password_hash if administrator else None)

        if administrator is None or not password_ok:
            self._audit_logs.create(
                db,
                event_type="ADMIN_LOGIN_FAILURE",
                severity=AuditSeverity.WARNING,
                description=f"Failed administrator login attempt for username '{username}'.",
                admin_id=administrator.id if administrator else None,
            )
            db.commit()
            raise AuthenticationError("Invalid username or password.")

        self._administrators.update_last_login(db, administrator)
        self._audit_logs.create(
            db,
            event_type="ADMIN_LOGIN_SUCCESS",
            severity=AuditSeverity.INFO,
            description=f"Administrator '{administrator.username}' logged in successfully.",
            admin_id=administrator.id,
        )
        db.commit()
        return administrator

    def create_session(self, db: Session, *, administrator: Administrator) -> tuple[str, datetime]:
        """
        Establish a new session for ``administrator`` (FR-019 step 4).

        Returns the raw (unhashed) session token - to be placed directly
        in the ``session`` cookie by the caller (the router) - and the
        session's expiry timestamp. Only the token's hash is persisted.
        """
        raw_token = generate_token()
        expires_at = datetime.now(timezone.utc) + self._session_timeout
        self._sessions.create(
            db,
            admin_id=administrator.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        db.commit()
        return raw_token, expires_at

    def validate_session(self, db: Session, *, raw_token: str) -> Administrator:
        """
        Resolve a raw session-cookie token to its ``Administrator``.

        Implements NFR-028's sliding inactivity timeout: a valid session's
        ``last_activity_at``/``expires_at`` are refreshed on every
        successful validation. Raises ``AuthenticationError`` (401) if the
        token is missing, unknown, or expired.
        """
        session = self._sessions.get_valid_by_token_hash(db, hash_token(raw_token))
        if session is None:
            raise AuthenticationError("Session is invalid or has expired.")

        new_expiry = datetime.now(timezone.utc) + self._session_timeout
        self._sessions.touch(db, session, new_expiry)
        db.commit()

        administrator = self._administrators.get_by_id(db, session.admin_id)
        if administrator is None:
            # Defensive: the FK guarantees this cannot happen in practice
            # (CASCADE deletes sessions with their administrator), but a
            # missing administrator must never be treated as "authenticated".
            raise AuthenticationError("Session is invalid or has expired.")
        return administrator

    def invalidate_session(self, db: Session, *, raw_token: str) -> None:
        """
        Log out: delete the session matching ``raw_token``, if any.

        Intentionally does not raise if the token does not match an
        existing session - logging out twice, or with a stale cookie,
        should not be treated as an error.
        """
        session = self._sessions.get_valid_by_token_hash(db, hash_token(raw_token))
        if session is not None:
            self._audit_logs.create(
                db,
                event_type="ADMIN_LOGOUT",
                severity=AuditSeverity.INFO,
                description="Administrator logged out.",
                admin_id=session.admin_id,
            )
            self._sessions.delete(db, session)
        db.commit()


def get_session_timeout(minutes: int) -> timedelta:
    """Build a ``timedelta`` from `Settings.SESSION_INACTIVITY_TIMEOUT_MINUTES`."""
    return timedelta(minutes=minutes)
