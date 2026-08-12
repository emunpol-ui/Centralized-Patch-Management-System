"""
Application configuration loader.

Defines the strongly-typed ``Settings`` model used throughout the CPMS
backend. Values are loaded from environment variables and, when present,
from a local ``.env`` file (see ``.env.example`` at the project root).

Configuration is exposed to the rest of the application exclusively through
the ``get_settings()`` dependency so that:

    * Settings are validated once, at startup, using Pydantic.
    * Settings can be injected into FastAPI routes via ``Depends`` (see
      ``backend/api/dependencies.py``), keeping the design testable and
      loosely coupled (per SAD Section 2.5, Principle 6 - "Configuration
      over Hardcoding").
    * Repeated instantiation is avoided through ``lru_cache``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (three levels up from this file:
# backend/core/config.py -> backend/core -> backend -> <project root>)
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application identity -------------------------------------------------
    APP_NAME: str = "Centralized Patch Management System"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # --- Server binding ---------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Logging -----------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = Path("logs")
    LOG_FILE: str = "application.log"

    # --- CORS ---------------------------------------------------------------
    # Stored as a raw comma-separated string to avoid pydantic-settings'
    # implicit JSON parsing of list-typed environment variables; exposed to
    # the application as a list via `cors_origins_list`.
    CORS_ORIGINS: str = "*"

    # --- Repository storage (REP-001) ---------------------------------------
    REPOSITORY_DIR: Path = Path("repository")

    # FR-006 Upload Validation Rules / FR-018 "Maximum installer upload
    # size". Expressed in megabytes in the environment for readability;
    # exposed to the application in bytes via
    # `max_installer_upload_size_bytes` below. 500 MB comfortably covers
    # typical Windows desktop application installers while still bounding
    # worst-case disk/request usage for this prototype.
    MAX_INSTALLER_UPLOAD_SIZE_MB: int = 500

    # --- Database (CPM-002) -------------------------------------------------
    # SQLite is the prototype default (Charter Section 8, SAD Section 6.4).
    # A relative "sqlite:///..." URL is resolved against BASE_DIR via the
    # `database_url` property below so the DB file location is stable
    # regardless of the working directory the server is launched from.
    DATABASE_URL: str = "sqlite:///./cpms.db"
    DATABASE_ECHO: bool = False

    @property
    def database_url(self) -> str:
        """
        Resolved SQLAlchemy database URL.

        Relative SQLite file paths are resolved against the project root
        (BASE_DIR). Non-SQLite URLs (e.g. a future PostgreSQL connection
        string per NFR-020) are returned unmodified.
        """
        prefix = "sqlite:///"
        if not self.DATABASE_URL.startswith(prefix):
            return self.DATABASE_URL

        raw_path = Path(self.DATABASE_URL[len(prefix):])
        if raw_path.is_absolute():
            return self.DATABASE_URL
        return f"{prefix}{(BASE_DIR / raw_path).resolve()}"

    # --- Administrator authentication (CPM-003) -----------------------------
    # FR-018 lists "Administrator session timeout" as a configurable setting
    # (ultimately intended to live in the DB-backed System Configuration
    # table implemented by SYS-001). Until that ticket exists, it is sourced
    # from the environment like every other setting here, consistent with
    # the "Configuration over Hardcoding" principle (SAD Section 2.5).
    SESSION_COOKIE_NAME: str = "session"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    SESSION_INACTIVITY_TIMEOUT_MINUTES: int = 30

    # NFR-028 calls for "secure session cookies" (the cookie `Secure`
    # attribute, which browsers only transmit over HTTPS). The Charter
    # (Section 8) and SAD (Section 5.5.1) both document the prototype as
    # communicating over plain HTTP within the LAN, with HTTPS explicitly
    # listed as a *future* enhancement. Defaulting this to True would make
    # the browser silently refuse to send the session cookie at all under
    # the prototype's own documented deployment model, breaking login
    # outright. This is therefore a deliberate, documented accommodation -
    # not a security oversight - and MUST be set to True once HTTPS is
    # deployed (see SESSION_COOKIE_SECURE in .env.example).
    SESSION_COOKIE_SECURE: bool = False

    # --- Client heartbeat / online status (DASH-001) ------------------------
    # FR-003/FR-014 describe a client as "Offline" once no heartbeat has been
    # received within a "configurable timeout period". No SYS-001-backed,
    # DB-persisted configuration table exists yet, so - consistent with
    # SESSION_INACTIVITY_TIMEOUT_MINUTES above - this is sourced from the
    # environment like every other setting in this class. The Dashboard
    # Home client summary (DASH-001) is the first feature that needs this
    # value; no existing code previously computed effective online/offline
    # status (see the design note in backend/services/dashboard_service.py).
    CLIENT_HEARTBEAT_TIMEOUT_MINUTES: int = 10

    @property
    def session_inactivity_timeout_seconds(self) -> int:
        """`SESSION_INACTIVITY_TIMEOUT_MINUTES` expressed in seconds."""
        return self.SESSION_INACTIVITY_TIMEOUT_MINUTES * 60

    @property
    def log_file_path(self) -> Path:
        """Absolute path to the rotating application log file."""
        log_dir = self.LOG_DIR if self.LOG_DIR.is_absolute() else BASE_DIR / self.LOG_DIR
        return log_dir / self.LOG_FILE

    @property
    def repository_path(self) -> Path:
        """Absolute path to the local software repository directory."""
        if self.REPOSITORY_DIR.is_absolute():
            return self.REPOSITORY_DIR
        return BASE_DIR / self.REPOSITORY_DIR

    @property
    def max_installer_upload_size_bytes(self) -> int:
        """`MAX_INSTALLER_UPLOAD_SIZE_MB` expressed in bytes (FR-006/FR-018)."""
        return self.MAX_INSTALLER_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins as a list, parsed from the comma-separated setting."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        """True when the application is running in development mode."""
        return self.APP_ENV.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached, singleton ``Settings`` instance.

    Using ``lru_cache`` ensures the environment/`.env` file is parsed only
    once per process while still allowing ``Settings`` to be used as a
    FastAPI dependency (see ``backend/api/dependencies.py``).
    """
    return Settings()
