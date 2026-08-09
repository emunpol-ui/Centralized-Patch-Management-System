# CURRENT_STATE.md

**Version:** 1.2  
**Last Updated:** August 9, 2026

---

## Project Overview

### Centralized Patch Management System (CPMS)

A proof-of-concept centralized software patch management system for Windows computers within a Local Area Network (LAN).

**Purpose:** Demonstrate centralized software inventory collection, version comparison, repository management, and remote software deployment.

**Scope:** OJT/Capstone project — **not intended** to replace enterprise solutions such as Microsoft SCCM or Microsoft Intune.

### Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLAlchemy ORM (2.x), Alembic, SQLite, Pydantic/Pydantic-Settings |
| Frontend | Bootstrap 5 (Jinja2 Templates not yet wired) |
|Client Agent | Inventory collection scaffolding implemented (server-side inventory upload complete)|
| Authentication | Admin: Session + CSRF cookie; Client: Bearer API Key (SHA-256) |
| Deployment | Local Package Repository (upload + administrator dashboard listing/search/details/deactivation implemented — REP-001, REP-002); deployment **creation** implemented (DEPLOY-001 — batch + per-client target persistence, initial `Pending` status); deployment **polling** implemented (DEPLOY-002 — client-scoped `GET /api/agent/deployments/poll`, read-only, no status transition); installer download/execution/status reporting not yet implemented |
| File Handling | `python-multipart` (installer upload parsing), SHA-256 (`hashlib`, standard library) |

### Architecture

```
Presentation Layer (Frontend)
        │
        ▼
FastAPI Routers (thin)
        │
        ▼
Service Layer (business logic)
        │
        ▼
Repository Layer (data access)
        │
        ▼
SQLAlchemy ORM
        │
        ▼
SQLite Database
```

### Project Structure (Current)

```
backend/
├── api/
│   ├── routers/
│   │   ├── health.py
│   │   ├── auth.py                # Admin login/logout/me/keys
│   │   ├── agent.py               # Protected agent endpoints (ping, heartbeat, inventory upload,
│   │   │                          # deployment poll — DEPLOY-002: GET /api/agent/deployments/poll)
│   │   ├── registration.py        # POST /api/register (CLIENT-001)
│   │   ├── updates.py             # Admin version-comparison endpoint (INV-002)
│   │   ├── repository.py          # Admin installer upload (REP-001) + list/detail/deactivate (REP-002)
│   │   └── deployments.py         # Admin deployment creation endpoint (DEPLOY-001, unmodified by DEPLOY-002)
│   └── dependencies.py            # DI providers (admin + client + services); extended (DEPLOY-001): DeploymentServiceDependency
├── core/
│   ├── config.py                  # Extended (REP-001): MAX_INSTALLER_UPLOAD_SIZE_MB
│   ├── security.py                # Token/hash primitives
│   ├── logging.py
│   └── exceptions.py              # Global exception handlers
├── database/
│   ├── base.py
│   ├── database.py
│   ├── session.py
│   └── migrations/
├── models/
│   ├── base.py                    # UUID PKs, audit mixins
│   ├── enums.py                   # Shared enums, incl. UpdateStatus (INV-002)
│   ├── administrator.py
│   ├── administrator_session.py
│   ├── client.py
│   ├── client_provisioning_key.py
│   ├── software_inventory.py
│   ├── repository_package.py      # Reused unmodified by REP-001
│   ├── deployment.py
│   ├── deployment_target.py
│   └── audit_log.py
├── repositories/
│   ├── administrator_repository.py
│   ├── administrator_session_repository.py
│   ├── audit_log_repository.py
│   ├── client_repository.py               # Extended (INV-002): get_by_id
│   ├── client_provisioning_key_repository.py
│   ├── software_inventory_repository.py   # INV-001 inventory persistence
│   ├── repository_package_repository.py   # Extended (REP-001): create, get_active_conflict
│   │                                       # Extended (REP-002): list_all, get_by_id, deactivate
│   └── deployment_repository.py           # NEW (DEPLOY-001): Deployment/DeploymentTarget data access
│                                           # Extended (DEPLOY-002): get_pending_target_for_client (client-scoped poll query)
├── services/
│   ├── auth_service.py
│   ├── client_auth_service.py
│   ├── client_service.py
│   ├── heartbeat_service.py
│   ├── inventory_service.py               # Inventory synchronization service
│   ├── version_comparison_service.py      # FR-007 version comparison business logic (INV-002)
│   ├── repository_service.py              # FR-006 installer upload (REP-001) + list/get/deactivate (REP-002)
│   └── deployment_service.py              # NEW (DEPLOY-001): FR-008/FR-009 deployment creation business logic
│                                           # Extended (DEPLOY-002): poll_pending_deployment (read-only, FR-009 polling)
├── utils/
│   ├── version_compare.py                 # FR-007 name/version matching + comparison rules (INV-002)
│   └── file_storage.py                    # FR-006 extension validation, SHA-256 hashing, file streaming (REP-001)
└── schemas/
    ├── auth.py
    ├── client.py
    ├── inventory.py                       # Inventory upload request schemas
    ├── updates.py                         # Version comparison response schemas (INV-002)
    ├── repository.py                      # Upload metadata + response schemas (REP-001); list response,
    │                                       # created_at/updated_at fields (REP-002)
    └── deployment.py                      # NEW (DEPLOY-001): deployment creation request/response schemas
                                            # Extended (DEPLOY-002): DeploymentPollResponse/DeploymentPollTargetResponse/
                                            # DeploymentPollPackageDetail (agent polling response DTOs)

agent/                                     # Client Agent (initial implementation)
├── communication/                         # Server communication helpers
├── scanner/                               # Windows Registry inventory scanner
└── main.py                                # Agent entry point

repository/                                # Local package repository (REP-001 — now receives uploaded installers)

scripts/
├── create_admin.py                        # Production admin provisioning
└── dev_seed_client.py                     # Development/testing client seed

docs/

tests/                                     # Empty skeleton (no pytest configured)

---

## Overall Progress

| Metric                    | Status                                          |
| ------------------------- | ------------------------------------------------ |
| **Current Version**       | v1.2                                            |
| **Development Stage**     | DEPLOY-003 — Installer Download & Execution (not yet started) |
| **Latest Stable Release** | DEPLOY-002 — Agent Polling                      |
| **Repository Status**     | Active Development                              |
| **Architecture Status**   | Stable                                          |
| **Regression Status**     | No known regressions from completed tickets     |

### Completed Milestones

| Version | Tickets Completed                                     |
| ------- | ----------------------------------------------------- |
| v0.1    | CORE-001 — Backend Foundation                         |
| v0.2    | CORE-002 — Database Layer                             |
| v0.3    | AUTH-001 — Administrator Authentication               |
| v0.4    | AUTH-002 — Client Authentication                      |
| v0.5    | CLIENT-001 — Client Registration (incl. FR-020 slice) |
| v0.6    | CLIENT-002 — Heartbeat Service                        |
| v0.7    | INV-001 — Inventory Collection                        |
| v0.8    | INV-002 — Version Comparison                          |
| v0.9    | REP-001 — Repository Management                       |
| v1.0    | REP-002 — Repository Dashboard                        |
| v1.1    | DEPLOY-001 — Deployment Creation                      |
| v1.2    | DEPLOY-002 — Agent Polling                            |

### Current Ticket

**DEPLOY-002 — Agent Polling** ✅ Complete

### Next Ticket

**DEPLOY-003 — Installer Download & Execution**

**Purpose:** Allow a Client Agent that has retrieved a pending deployment (DEPLOY-002) to download the associated installer, verify its SHA-256 checksum against the value returned by the poll endpoint, and execute it silently (FR-010 Installer Download, FR-011 Silent Software Installation), building on the now-complete client-scoped polling endpoint (DEPLOY-002).

---

## Completed Implementation

### Backend Foundation

| Ticket | Status |
|--------|--------|
| CORE-001 | ✅ Production Ready |

**Features Implemented:**
- FastAPI application initialization with project structure
- Configuration loader (environment + Pydantic-Settings)
- Dependency injection setup
- Logging configuration
- Startup events
- Swagger/OpenAPI documentation
- Requirements management

**Important Files:** `backend/main.py`, `backend/core/config.py`

---

### Database Layer

| Ticket | Status |
|--------|--------|
| CORE-002 | ✅ Production Ready |

**Features Implemented:**
- SQLAlchemy 2.x declarative style configuration
- Session management
- Declarative Base with `Uuid` primary keys
- `BaseModel` / `AuditModel` abstract mixins
- All database models (Administrator, Client, SoftwareInventory, RepositoryPackage, Deployment, DeploymentTarget, AuditLog)
- Alembic integration with migrations under `backend/database/migrations/`
- Relationships and constraints (FK `ondelete` semantics documented in model docstrings)
- Database initialization

**Migration Round-trip Verified:** `upgrade head` → `downgrade base` → `upgrade head` → `alembic check` all clean.

**Important Files:**
- `backend/database/database.py`, `backend/database/session.py`, `backend/database/base.py`
- `backend/models/` (all models)
- `alembic.ini`, `backend/database/migrations/`

---

### Authentication

#### AUTH-001 — Administrator Authentication

| Status | ✅ Production Ready |

**Features Implemented:**
- Admin login (`POST /api/admin/login`)
- Admin logout (`POST /api/admin/logout`)
- Current admin provider (`GET /api/admin/me`)
- Password hashing (Passlib/bcrypt — bcrypt 4.0.1 for passlib 1.7.4 compatibility)
- `AdministratorSession` DB-backed session model (docstring explains addition beyond PRS/SAD)
- Session cookie middleware/dependency (`require_administrator`, `CurrentAdministrator`)
- CSRF protection (double-submit cookie pattern — `verify_csrf_token` / `CSRFProtection`)
- Audit logging (`ADMIN_LOGIN_SUCCESS`, `ADMIN_LOGIN_FAILURE`, `ADMIN_LOGOUT`)
- Admin bootstrap CLI (`scripts/create_admin.py` — FR-019 documented)

**Known, Documented Deviation:** Ticket text requested JWT; implemented session-cookie authentication per FR-019/NFR-028/PRS Appendix B. Documented in `backend/services/auth_service.py`.

---

#### AUTH-002 — Client Authentication

| Status | ✅ Production Ready |

**Features Implemented:**
- API key validation (`ClientAuthService.authenticate` — SHA-256 hash-at-rest)
- `ClientRepository.get_by_api_key_hash` (minimal, scoped to this ticket)
- Client authentication dependency (`require_client_api_key` / `CurrentClient`)
- Bearer token extraction (`Authorization: Bearer <key>` per PRS Appendix B)
- Router-level protection: `APIRouter(prefix="/api/agent", dependencies=[Depends(require_client_api_key)])` — ensures every current and future route on this router is automatically protected
- Demonstration endpoint: `GET /api/agent/ping` (verification)
- Audit logging: `CLIENT_AUTH_FAILURE` (successes intentionally not logged — see AUTH-002 rationale)
- Development utility: `scripts/dev_seed_client.py` (creates `Client` with known API key)

**Scoping Decision (Documented):** FR-020 (admin-facing `POST /api/admin/keys` issuance) was deferred to CLIENT-001, as it was structurally coupled to registration/claiming logic. AUTH-002 implemented FR-002 (Client Authentication) only.

**Bugfix Carried from AUTH-001:** `handle_validation_error` in `backend/core/exceptions.py` now passes Pydantic errors through `jsonable_encoder` — raw exception objects inside `field_validator` `ctx` were not JSON-serializable, causing unhandled 500s.

---

### Client Management

#### CLIENT-001 — Client Registration

| Status | ✅ Production Ready |

**Features Implemented:**
- Registration endpoint: `POST /api/register` (FR-001 create-or-update workflow, matched on `agent_guid`)
- `ClientService.register` — business logic:
  - Unknown `agent_guid`: creates new `Client`
  - Known `agent_guid`: refreshes `hostname`, `ip_address`, `operating_system`, `agent_version` (idempotent)
  - `updated_at` serves as "last registration timestamp"
- `ClientRepository` extended with `get_by_agent_guid`, `create`, `update_registration`
- `ClientRegistrationRequest` schema with validation:
  - `agent_guid` (UUID)
  - `hostname`, `operating_system`, `agent_version` (length-limited)
  - `ip_address` (real IPv4/IPv6 via `ipaddress`)
- Audit logging: `CLIENT_REGISTERED`, `CLIENT_REGISTRATION_UPDATED`, `CLIENT_REGISTRATION_CONFLICT`, `CLIENT_KEY_PROVISIONED`
- Dashboard integration: registered clients are ordinary rows in `clients` table — no schema or repository changes needed for future listing

**Resolved Conflict (Documented):** The ticket brief required registration to use `require_client_api_key`/`CurrentClient`, but this dependency only resolves keys matching *existing* `Client` rows — impossible for first-time registration. Resolved by implementing the minimal FR-020 slice:

- Added `ClientProvisioningKey` model + migration (`96d9bed20171_add_client_provisioning_keys_table`)
- Administrator-issued, not-yet-claimed API key (existence = unclaimed; claimed at first successful registration)
- `POST /api/admin/keys` (FR-020) — admin session + CSRF protected, returns plain-text key exactly once
- `ClientProvisioningKeyRepository` (`create`, `get_by_key_hash`, `delete`)
- `ClientAuthService.resolve_registration_credential` — resolves against *either* existing `Client` OR unclaimed `ClientProvisioningKey`
- `POST /api/register` lives on its own router (`registration.py`), **not** `agent.py` — `agent.py`'s router-wide `require_client_api_key` guarantee remains untouched
- `extract_bearer_token` helper made public (renamed from `_extract_bearer_token`, logic unchanged)

**Conflict Scenarios Guarded (both verified):**
1. Already-claimed key cannot register a second, different Agent GUID → 409
2. Fresh/different key cannot hijack an Agent GUID that already belongs to another client → 409

**Regression Status:** Passed. Full regression suite re-verified:
- CORE-001 health check
- AUTH-001 login/session/CSRF/logout/protected-route rejection
- AUTH-002 `dev_seed_client.py`-issued key authenticates on `/api/agent/ping`; invalid key rejected
- 20 new CLIENT-001-specific checks (new registration, idempotent re-registration, invalid payload, invalid API key, missing Authorization header, both conflict scenarios, provisioning-key issuance auth/CSRF gating)
- Direct SQLite and audit-log inspection
- Migration round-trip re-verified
- `pyflakes` reports no new warnings (one pre-existing unused import in AUTH-001's `auth_service.py` untouched)

---

#### CLIENT-002 — Heartbeat Service

| Status | ✅ Production Ready |

**Features Implemented:**
- Heartbeat endpoint: `POST /api/agent/heartbeat` (agent liveness reporting)
- `HeartbeatService.record_heartbeat`:
  - Updates authenticated client's `last_heartbeat` timestamp
  - Transitions client status to `ONLINE` (from `UNKNOWN`)
- Protected via AUTH-002's `require_client_api_key` (router-level)
- Repository integration through existing `ClientRepository` (no schema changes)
- Audit logging: successful and failed heartbeat requests
- Response returns authenticated client information for downstream use

**Manual Verification:**
- ✅ Rejects requests without `Authorization: Bearer <API Key>` (401)
- ✅ Valid API key authenticates
- ✅ Returns successful response
- ✅ Client status updates `UNKNOWN` → `ONLINE`
- ✅ `last_heartbeat` timestamp persisted correctly (verified via SQLite)
- ✅ No regressions in AUTH-001, AUTH-002, or CLIENT-001

**Important Note:** No automated test framework exists — all verification is manual/scripted against real SQLite database.

---
### INV-001 — Inventory Collection

| Status | ✅ Production Ready |

**Features Implemented:**

- Authenticated software inventory upload endpoint: `POST /api/agent/inventory/upload` (FR-005)
- `InventoryService` implementing complete inventory snapshot synchronization:
  - Inserts newly discovered software records
  - Updates existing software metadata when changes are detected
  - Removes software records no longer present in the uploaded inventory
- `SoftwareInventoryRepository` providing persistence operations for software inventory records
- `InventoryUploadRequest` schema validating uploaded inventory payloads before business logic execution
- Protected via AUTH-002's `require_client_api_key` (`CurrentClient`)
- Inventory records persisted to the existing `software_inventory` table (no database schema changes required)
- Initial Client Agent scaffolding implemented under the `agent/` package:
  - `scanner/` for future Windows Registry inventory collection
  - `communication/` for server communication
  - `main.py` as the client agent entry point

**Manual Verification:**

- ✅ Administrator authentication verified
- ✅ Client API key provisioning verified
- ✅ Client registration verified
- ✅ Client authentication verified
- ✅ Heartbeat endpoint verified
- ✅ Agent ping endpoint verified
- ✅ Inventory upload endpoint accepted authenticated requests successfully
- ✅ Uploaded software inventory persisted correctly to the SQLite database
- ✅ Complete end-to-end workflow validated:

```text
Administrator Login
        ↓
Generate API Key
        ↓
Client Registration
        ↓
Client Authentication
        ↓
Heartbeat
        ↓
Inventory Upload
        ↓
Database Persistence
```

- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, or CLIENT-002

**Important Note:** Inventory uploads were validated using manually constructed payloads submitted through authenticated PowerShell (`Invoke-RestMethod`) requests. Automated Windows Registry inventory collection has been scaffolded within the Client Agent and will be exercised through the deployed Windows Agent in future milestones. Swagger UI currently cannot exercise authenticated agent endpoints because the OpenAPI specification does not expose the required Bearer/API Key authentication scheme.

---

### INV-002 — Version Comparison

| Status | ✅ Production Ready |

**Objective:** Compare each installed software item reported by a Client (INV-001) against the administrator-approved Repository Package catalog and classify it as Up-to-Date, Update Available, or Not Managed (FR-007).

**Features Implemented:**

- `backend/utils/version_compare.py` — pure, database-independent FR-007 rule functions:
  - `normalize_software_name` — trim, strip trailing `(64-bit)`/`(32-bit)` architecture suffixes, case-fold (FR-007 Software Matching Rules)
  - `normalize_publisher` — trim + case-fold, provided as a general-purpose helper (see limitation note below)
  - `parse_version` — parses a period-delimited numeric-segment version string; returns `None` if unparseable
  - `compare_versions` — left-to-right numeric segment comparison (shorter tuples zero-padded); returns `None` if either side is unparseable (FR-007 Version Comparison Rules)
- `RepositoryPackageRepository` (introduced) — minimal read-only slice (`list_approved`) needed for comparison; excludes `INACTIVE` packages (FR-017 "removal" mechanism). Package upload/maintenance was deferred at the time to REP-001 (now implemented — see below).
- `VersionComparisonService` (new) — `compare_client_inventory(db, client_id=...)`:
  - Loads a client's `SoftwareInventory` records (reusing `SoftwareInventoryRepository.list_for_client` unmodified) and the approved `RepositoryPackage` catalog
  - Groups approved packages by normalized software name for lookup
  - Classifies each inventory item per FR-007 Status Definitions: `NOT_MANAGED` when no approved package matches the normalized name, `NOT_MANAGED` when either version string fails to parse (never assumed Up-to-Date), otherwise `UPDATE_AVAILABLE` when installed < approved or `UP_TO_DATE` when installed >= approved
  - Comparison results are computed on demand, not persisted — consistent with the project's existing "OFFLINE status computed at read time" pattern (see Architecture Notes)
- `UpdateStatus` enum (new, `backend/models/enums.py`): `UP_TO_DATE`, `UPDATE_AVAILABLE`, `NOT_MANAGED`
- `backend/schemas/updates.py` (new) — `SoftwareUpdateStatusResponse`, `ClientUpdateStatusSummary` response DTOs
- `ClientRepository.get_by_id` (new method) — resolves a `client_id` path parameter for the endpoint below
- New administrator-facing, read-only endpoint: `GET /api/admin/clients/{client_id}/updates` (Backlog UPDATE-001 "Available updates endpoint" deliverable)
  - Protected by `CurrentAdministrator` (session cookie); no CSRF token required (read-only, NFR-028 scopes CSRF to state-changing requests)
  - Returns per-item comparison results plus an aggregate summary (`up_to_date`, `update_available`, `not_managed`, `total`)
  - Returns 404 (`ClientNotFoundError`) for an unknown `client_id`

**Documented Schema Limitation:** FR-007 allows publisher to be considered "where available" to reduce false matches, but `RepositoryPackage` (defined by CORE-002) has no `publisher` column — only `SoftwareInventory` does. Publisher-based disambiguation is therefore not applied when matching against the repository catalog; matching is name-only (after normalization). This is a pre-existing schema constraint, not a deviation introduced by this ticket, and `RepositoryPackage` was not modified to stay within this ticket's minimal-file-change scope. When multiple approved packages share a normalized name, the candidate with the highest parseable version is preferred.

**Manual/Scripted Verification:**

- ✅ `version_compare` utility functions unit-verified (name/publisher normalization, version parsing, version comparison, including unequal-length and unparseable inputs)
- ✅ `VersionComparisonService` verified end-to-end against a real SQLAlchemy/SQLite session: Update Available, Up-to-Date, Not Managed (no matching package), and Not Managed (unparseable installed version) all classified correctly
- ✅ `INACTIVE` repository packages confirmed excluded from matching (classified Not Managed even when a same-named inactive package exists)
- ✅ `GET /api/admin/clients/{client_id}/updates` verified via `TestClient` against a full FastAPI app + SQLite database:
  - Authenticated administrator receives correct comparison payload and summary counts
  - Unauthenticated request rejected (401)
  - Unknown `client_id` rejected (404)
- ✅ Full application import and OpenAPI schema generation confirmed the new route registers correctly alongside all existing routes
- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, CLIENT-002, or INV-001 (existing endpoints, models, and services were not modified beyond the additive `ClientRepository.get_by_id` method)

**Important Note:** No database schema or migration changes were required — `UpdateStatus` is a Python-level enum used only for in-memory classification and API response shaping, not a database column. Repository package data was empty until REP-001; the endpoint has been re-verified below to now report real comparison results once approved packages exist.

---

### REP-001 — Repository Management

| Status | ✅ Production Ready |

**Objective:** Implement the Local Package Repository (FR-006 Software Repository Management): allow an administrator to upload installer packages, validate their metadata, compute and verify a SHA-256 checksum, and persist package metadata for future deployment (DEPLOY-*).

**Features Implemented:**

- `backend/utils/file_storage.py` (new) — pure, database-independent FR-006 "Upload Validation Rules" helpers:
  - `validate_extension` — rejects an uploaded file whose extension does not match the declared Installer Type (`.exe` for EXE, `.msi` for MSI)
  - `generate_storage_filename` — generates a new, random, server-controlled filename (UUID4 hex + extension); the client-supplied filename is never trusted for storage or path construction
  - `save_and_hash` — streams the uploaded file to disk in fixed-size (1 MiB) chunks, computing its SHA-256 checksum while writing, enforcing the configured maximum upload size, and rejecting/cleaning up empty or oversized uploads (the partially-written file is deleted on any failure)
- `backend/schemas/repository.py` (new):
  - `RepositoryPackageUploadMetadata` — validates the `multipart/form-data` metadata fields accompanying an upload (non-blank software name/version; the Silent Installation Command must reference the installer only via the `{installer_path}` placeholder token and must not contain shell operators, `..`, or other unsafe sequences — enforcing FR-006's Repository Metadata constraint on `silent_command` at upload time, ahead of FR-011's execution-time direct-process-execution behavior)
  - `RepositoryPackageResponse` — response DTO built from a persisted `RepositoryPackage` ORM instance
- `RepositoryPackageRepository` (introduced by INV-002) extended with:
  - `create` — persists a new `RepositoryPackage` row (defaults to `APPROVED`)
  - `get_active_conflict` — FR-006 duplicate-entry detection: returns an existing `APPROVED` package sharing the same normalized software name (reusing INV-002's `normalize_software_name`) and exact version string, or `None`
  - `list_approved` (INV-002) unchanged
- `RepositoryService` (new, `backend/services/repository_service.py`) — `upload_package(...)` orchestrates the full FR-006 upload workflow: extension validation → duplicate-conflict check (audit-logged and rejected before any file I/O) → server-generated filename → streamed checksum/size-enforced file write → metadata persistence → audit log (`REPOSITORY_PACKAGE_UPLOADED`) → commit
  - `RepositoryPackageValidationError` (400) — extension mismatch, oversized upload, or empty file
  - `RepositoryPackageConflictError` (409) — duplicate approved package for the same name + version
- New administrator-facing, state-changing endpoint: `POST /api/admin/repository/packages` (Backlog REP-001 "Installer upload" deliverable)
  - `multipart/form-data`: `installer` (file, `.exe`/`.msi`) + `software_name`, `version`, `installer_type`, `silent_command` (form fields)
  - Protected by `CurrentAdministrator` (session cookie) **and** `CSRFProtection` (state-changing request, NFR-028) — the same pattern as `POST /api/admin/keys`
  - Returns `201 Created` with the persisted package's metadata (including its computed SHA-256 checksum) on success
- `backend/core/config.py` extended: `MAX_INSTALLER_UPLOAD_SIZE_MB` (default `500`) and the derived `max_installer_upload_size_bytes` property, filling in FR-018's "Maximum installer upload size" configurable setting (the `REPOSITORY_DIR`/`repository_path` setting was already reserved by CORE-001/config.py and required no changes)
- `requirements.txt` extended: `python-multipart==0.0.20` (required by FastAPI to parse `multipart/form-data` — the installer file + form metadata fields)
- `backend/api/dependencies.py` extended: `get_repository_service` / `RepositoryServiceDependency`, following the existing per-service DI factory pattern
- `backend/main.py` extended: registers the new `repository_router`

**Design Decisions (Documented):**

- **Duplicate detection scope:** "Duplicate" is defined as an existing `APPROVED` package sharing the same FR-007-normalized software name and an exact (trimmed) version-string match. `INACTIVE` (FR-017 "removed") packages are excluded from the conflict check, so a previously removed package does not block re-uploading the same name/version.
- **Approval status on upload:** A newly uploaded package is persisted directly as `APPROVED` (matching `RepositoryPackage.approval_status`'s existing default). PRS FR-006 describes an uploaded, validated package as immediately "available for deployment selection," with no separate approval workflow currently defined; introducing one was judged out of scope for REP-001.
- **Order of validation:** Extension/installer-type consistency is checked first (no I/O), then the duplicate-entry check (a single, bounded database query — no file I/O yet), and only then is the (potentially large) file streamed to disk. This ensures a request that will ultimately be rejected fails as early and cheaply as possible.
- **Silent command safety enforced at two layers:** `RepositoryPackageUploadMetadata` rejects an unsafe `silent_command` at upload time (FR-006), independent of and in addition to FR-011's already-implemented execution-time direct-process-execution behavior (`shell=False`-equivalent invocation, implemented client-agent-side prior to this ticket) — defense in depth, not a replacement for either control.
- **Repository storage location unchanged:** Reused the existing `Settings.REPOSITORY_DIR` / `repository_path` (reserved since CORE-001), which resolves to a project-root `repository/` directory outside `backend/static/` — the only web-server-exposed directory in this application — satisfying FR-006's "not directly accessible via the web server" rule without any new configuration.

**Manual/Scripted Verification (via `TestClient` against a full FastAPI app + real SQLite database):**

- ✅ Successful upload: `201 Created`, response `checksum` matches an independently computed `hashlib.sha256` digest of the uploaded content, `file_size` matches the byte count, `installer_filename` is a server-generated UUID4-based name (not the client-supplied name), and the file is confirmed present on disk under the configured repository directory
- ✅ Duplicate upload (same normalized software name + version, already `APPROVED`): rejected `409 Conflict`; audit log entry (`REPOSITORY_UPLOAD_CONFLICT`) recorded; no file written for the rejected request
- ✅ Extension/installer-type mismatch (`.msi` file with `installer_type=EXE`): rejected `400 Bad Request` before any file write
- ✅ Invalid Silent Installation Command (missing `{installer_path}` placeholder): rejected `400 Bad Request` at the Pydantic metadata-validation layer, before the file is streamed
- ✅ Missing/invalid CSRF token: rejected `403 Forbidden`
- ✅ Unauthenticated request (no administrator session): rejected `401 Unauthorized`
- ✅ Full application import and OpenAPI schema generation confirmed `POST /api/admin/repository/packages` registers correctly alongside all existing routes
- ✅ `pyflakes` reports no warnings across all new/modified files
- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, CLIENT-002, INV-001, or INV-002 — `RepositoryPackageRepository.list_approved` and `VersionComparisonService` were not modified; `GET /api/admin/clients/{client_id}/updates` will automatically reflect newly uploaded packages with no further code changes

**Important Note:** No database schema or migration changes were required — `RepositoryPackage` (defined by CORE-002) already had every column this ticket needed (`checksum`, `file_size`, `installer_filename`, `silent_command`, `installer_type`, `approval_status`). REP-001 is upload-only: metadata *editing* and *removal* (FR-017 Repository Maintenance) and a package-listing/browse view (REP-002 Repository Dashboard) remain unimplemented.

---

### REP-002 — Repository Dashboard

| Status | ✅ Production Ready |

**Objective:** Implement the administrator-facing Repository Dashboard (Backlog REP-002, FR-006 dashboard integration / FR-017 Repository Maintenance): allow an administrator to view uploaded repository packages, search/filter them, view package details, and delete (deactivate) a package.

**Features Implemented:**

- `RepositoryPackageRepository` (introduced by INV-002, extended by REP-001) extended with:
  - `list_all` — returns repository packages, optionally filtered by a case-insensitive substring `search` against `software_name`/`version` and/or by `approval_status` (`Approved`/`Inactive`); results ordered by `software_name`, then `version`
  - `get_by_id` — resolves a single package by primary key, or `None`
  - `deactivate` — sets `approval_status = INACTIVE` on an existing package and flushes the change (FR-017 "removal" semantics — a logical status change, **not** a physical row delete)
- `RepositoryService` (introduced by REP-001) extended with:
  - `list_packages(db, search=..., approval_status=...)` — read-only, delegates to `RepositoryPackageRepository.list_all`; no audit log entry recorded (read-only query, matching `VersionComparisonService`'s existing rationale — see Logging Standards)
  - `get_package(db, package_id)` — returns a single package or raises `RepositoryPackageNotFoundError` (404)
  - `deactivate_package(db, admin_id=..., package_id=...)` — resolves the package (404 if missing), deactivates it, records an audit log entry (`REPOSITORY_PACKAGE_DEACTIVATED`, INFO) unless the package was already `Inactive` (idempotent re-deactivation does not double-log), and commits
  - New exception: `RepositoryPackageNotFoundError` (`AppException`, 404)
- `backend/schemas/repository.py` extended:
  - `RepositoryPackageResponse` gained `created_at` / `updated_at` fields (already present on the ORM model via `AuditModel`; `created_at` doubles as the PRS's `upload_date`) so the detail/list views can surface upload and last-modified timestamps
  - New `RepositoryPackageListResponse` (`packages: list[RepositoryPackageResponse]`, `total: int`) wrapping the listing endpoint's response body; reuses `RepositoryPackageResponse` for each item rather than introducing a second, overlapping DTO
- Three new administrator-facing endpoints added to the existing `backend/api/routers/repository.py` (alongside REP-001's unmodified upload endpoint):
  - `GET /api/admin/repository/packages` — list/search packages; optional `search` and `approval_status` query parameters; read-only, `CurrentAdministrator` only (no CSRF — NFR-028 scopes CSRF to state-changing requests, matching the existing pattern on `GET /api/admin/clients/{client_id}/updates`)
  - `GET /api/admin/repository/packages/{package_id}` — package details; read-only, `CurrentAdministrator` only; 404 via `RepositoryPackageNotFoundError` for an unknown id
  - `POST /api/admin/repository/packages/{package_id}/deactivate` — deactivate ("delete") a package; state-changing, `CurrentAdministrator` **and** `CSRFProtection`, the same pattern already used by the upload endpoint

**Design Decisions (Documented):**

- **Deletion = deactivation, not a row delete:** Per the existing `ApprovalStatus.INACTIVE` semantics already defined by CORE-002/REP-001 and documented on `RepositoryPackage`/`ApprovalStatus`, "delete" is implemented purely as `approval_status → INACTIVE`. This was a pre-existing design decision in the baseline (not introduced by this ticket) and is simply reused. An `INACTIVE` package continues to satisfy `Deployment.repository_id` referential integrity and is automatically excluded from `list_approved`/`get_active_conflict` (both already status-filtered), so `VersionComparisonService` and duplicate-upload detection required no changes.
- **Idempotent deactivation:** Re-deactivating an already-`Inactive` package succeeds (200) rather than erroring, and does not write a second audit log entry for the same transition — a reasonable behavior for a "delete" action a dashboard user might click more than once, and consistent with not treating a repeated no-op as a new administrative event.
- **Listing scope:** `list_all` returns packages of *any* status by default (not just `Approved`) so the administrator can review previously deactivated packages from the same dashboard view; `approval_status` is an optional filter for narrowing to one status at a time. This differs intentionally from `list_approved` (INV-002/REP-001), which remains unchanged and continues to return only `Approved` packages for version-comparison/duplicate-detection purposes.
- **Search implementation:** A simple case-insensitive `LIKE`/`ilike` substring match against `software_name` and `version`, appropriate for the current SQLite-backed proof-of-concept scope — no full-text search engine or additional index was introduced.
- **No new database schema/migration:** `RepositoryPackage` (CORE-002) already had every column REP-002's listing/detail/deactivation needed; `created_at`/`updated_at` were already present via `AuditModel` and simply had not yet been exposed through `RepositoryPackageResponse`.
- **No frontend templates added:** The repository (`backend/templates/`, `backend/static/`) contains no wired Jinja2 templates as of v0.9/v1.0 (per CURRENT_STATE's existing "No frontend UI" note, unchanged by this ticket). REP-002 was implemented as the three API endpoints above, consistent with the project's current API-first, dashboard-templates-not-yet-wired state; a future dashboard-templating ticket can consume these endpoints without further backend changes.

**Manual/Scripted Verification (via `TestClient` against a full FastAPI app + real SQLite database):**

- ✅ `GET /api/admin/repository/packages` returns all uploaded packages with `total` matching the returned count
- ✅ `search` query parameter correctly narrows results by software name/version substring (case-insensitive)
- ✅ `approval_status` query parameter correctly restricts results to `Approved`-only or `Inactive`-only
- ✅ `GET /api/admin/repository/packages/{package_id}` returns full package metadata (including `created_at`/`updated_at`) for an existing package
- ✅ `GET /api/admin/repository/packages/{package_id}` returns `404` for an unknown package id
- ✅ `POST /api/admin/repository/packages/{package_id}/deactivate` without a CSRF token: rejected `403 Forbidden`
- ✅ `POST /api/admin/repository/packages/{package_id}/deactivate` with a valid session + CSRF token: `200 OK`, `approval_status` becomes `"Inactive"`
- ✅ A deactivated package is excluded from `GET .../packages?approval_status=Approved` and included under `approval_status=Inactive`
- ✅ Deactivated package row remains present in the database (not physically deleted) — verified via direct query
- ✅ Full application import and OpenAPI schema generation confirmed all three new routes register correctly alongside the existing upload endpoint
- ✅ `pyflakes` reports no warnings across all new/modified files
- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, CLIENT-002, INV-001, INV-002, or REP-001 — `RepositoryService.upload_package`, `VersionComparisonService`, `RepositoryPackageRepository.list_approved`/`get_active_conflict`/`create`, and every existing endpoint were not behaviorally modified

**Important Note:** REP-002 is API-only, matching the current state of the project's frontend (no Jinja2 templates wired yet). Metadata *editing* (e.g. changing an uploaded package's silent install command) remains unimplemented and out of scope, as it was not part of this ticket's deliverables.

---

### DEPLOY-001 — Deployment Creation

| Status | ✅ Production Ready |

**Objective:** Implement Deployment Creation (Backlog DEPLOY-001, FR-008 Deployment Job Creation, FR-009 Deployment Job Retrieval targeting): allow an administrator to create a deployment batch selecting one approved repository package and one or more registered target clients, creating one `Deployment` (batch) record and one `DeploymentTarget` record per targeted client, each initialized to `Pending` status.

**Features Implemented:**

- `DeploymentRepository` (new, `backend/repositories/deployment_repository.py`) — pure data-access layer for the pre-existing (CORE-002) `Deployment`/`DeploymentTarget` tables, which no repository had consumed until this ticket (the same deferral pattern already used for `RepositoryPackageRepository` prior to INV-002):
  - `create_deployment` — persists a new `Deployment` (batch) row
  - `add_target` — persists a new `DeploymentTarget` row for one client, defaulting to `DeploymentStatus.PENDING`
  - `get_active_target_for_client` / `get_active_targets_for_clients` — single-client and batched lookups (via the pre-existing `ix_deployment_targets_client_status` index) for any `DeploymentTarget` whose status is not yet terminal (`Pending`, `Downloading`, or `Installing`), used to enforce Business Rule 9
  - `get_by_id` — resolves a `Deployment` by primary key
  - Module-level `ACTIVE_DEPLOYMENT_STATUSES` constant (`Pending`, `Downloading`, `Installing`) — the existing `DeploymentStatus` enum's non-terminal values, reused rather than a new status vocabulary being invented
- `DeploymentService` (new, `backend/services/deployment_service.py`) — `create_deployment(...)` orchestrates the full FR-008 creation workflow, entirely as validation-before-mutation so no partial batch can ever be left behind:
  1. **Package validation** — resolves the repository package via the existing `RepositoryService.get_package` (REP-002, composed rather than duplicated), which already raises `RepositoryPackageNotFoundError` (404) for an unknown id; additionally rejects (`DeploymentPackageUnavailableError`, 400) a package that exists but is not currently `Approved` (i.e. has been deactivated/"removed" per FR-017)
  2. **Client validation** — resolves every requested `client_id` via the existing `ClientRepository.get_by_id` (INV-002), de-duplicating defensively and raising `DeploymentClientNotFoundError` (404) listing every unknown id if any are missing
  3. **Active-deployment validation** — Business Rule 9 (PRS Section 2.7: "A client may process only one deployment job at a time"), enforced here in the Service Layer (explicitly *not* as model-level logic, per this ticket's instructions) via `DeploymentRepository.get_active_targets_for_clients`; raises `DeploymentClientActiveError` (409) listing every conflicting client id if any target client already has a non-terminal deployment target
  4. **Atomic creation** — only after all three validations succeed: one `Deployment` row is created, then one `DeploymentTarget` row per validated client (status `Pending`), then one `DEPLOYMENT_CREATED` audit log entry, then a single `db.commit()`
  - New exceptions (`AppException` subclasses, following the existing `RepositoryPackageValidationError`/`RepositoryPackageConflictError` pattern): `DeploymentPackageUnavailableError` (400), `DeploymentClientNotFoundError` (404), `DeploymentClientActiveError` (409)
- `backend/schemas/deployment.py` (new):
  - `DeploymentCreateRequest` — `repository_package_id: UUID`, `client_ids: List[UUID]` (`min_length=1`); a `field_validator` rejects a request listing the same client more than once (`DeploymentTarget`'s own `uq_deployment_target_deployment_client` unique constraint would reject this at the database layer regardless, but failing fast here returns a clearer `422` instead of surfacing a database integrity error)
  - `DeploymentTargetResponse` — one targeted client's initial state (`id`, `client_id`, `status`, `created_at`)
  - `DeploymentResponse` — the created batch (`id` — serves as the PRS's "Batch ID" — `repository_id`, `created_by_admin_id`, `created_at`, `targets: list[DeploymentTargetResponse]`, `target_count`)
- New administrator-facing, state-changing endpoint: `POST /api/admin/deployments` (Backlog DEPLOY-001 "Deployment creation API" deliverable), added on a new `backend/api/routers/deployments.py` router (`prefix="/api/admin/deployments"`, grouped like `repository.py`/`updates.py`)
  - Protected by `CurrentAdministrator` (session cookie) **and** `CSRFProtection` (state-changing request, NFR-028) — the same pattern as `POST /api/admin/repository/packages`
  - Returns `201 Created` with the created batch's id, package reference, administrator reference, and the full list of created targets (each `Pending`) on success
  - Router stays thin: authenticates, delegates the entire request body straight to `DeploymentService.create_deployment`, and shapes the response — no business logic lives in the router
- `backend/api/dependencies.py` extended: `get_deployment_service` / `DeploymentServiceDependency`, following the existing per-service DI factory pattern (`DeploymentService()` constructed fresh per request, stateless like every other service)
- `backend/main.py` extended: registers the new `deployments_router`

**Design Decisions (Documented):**

- **Composition over duplication for package validation:** `DeploymentService` takes a `RepositoryService` dependency (constructor-injected, defaulting to a fresh instance) and calls its existing `get_package` method rather than re-implementing package lookup against `RepositoryPackageRepository` directly. This mirrors this ticket's explicit instruction to reuse existing repository/service methods rather than duplicate package-validation logic.
- **Active-deployment rule lives in the Service Layer, not the model:** `DeploymentTarget`'s own docstring (introduced by CORE-002) already anticipated this, describing Business Rule 9 as "a *business* rule, enforced by the Service Layer in DEPLOY-001" and pointing at the `ix_deployment_targets_client_status` index as the supporting data-layer artifact. No new database constraint (e.g. a partial unique index limiting one non-terminal target per client) was added — the existing index is sufficient for an efficient service-layer check, and adding a hard database constraint was judged unnecessary and outside this ticket's minimal-change scope.
- **Non-terminal status set:** `Pending`, `Downloading`, and `Installing` are treated as "active" (i.e. a client currently "processing" a deployment per Business Rule 9's wording); `Completed`, `Failed`, and `Cancelled` are terminal. These are the pre-existing `DeploymentStatus` enum values (FR-012) — no new status was introduced.
- **Atomicity without explicit rollback calls:** Every validation step runs to completion *before* any `Deployment`/`DeploymentTarget` row is created. Because `backend.database.session.get_db` never calls `db.commit()` itself (only `close()` in its `finally` block) and this service's own `db.commit()` sits at the very end of `create_deployment` (after every validation has already succeeded), any exception raised during validation propagates out of the method with nothing yet committed — any rows `flush()`-ed by an earlier step in the *same* method call are simply discarded when the session is later closed without a commit. This matches the pattern already used by every other service in this codebase (`RepositoryService.upload_package`, `InventoryService`, etc.), so no new transaction-management pattern was introduced.
- **Duplicate-client rejection at two layers:** `DeploymentCreateRequest`'s Pydantic validator rejects a request listing the same client id twice (422, before the service is even invoked); `DeploymentService._validate_clients` additionally de-duplicates defensively, since the service layer is this project's authoritative validation boundary and must not assume every caller goes through the schema layer.
- **Response shape:** `DeploymentResponse.id` doubles as the PRS's "Batch ID" (per the existing design note in `backend/models/deployment.py`, `Deployment.id` already serves this grouping purpose — no separate `batch_id` column exists on the model). `target_count` is a derived convenience field (not a stored column) so API consumers do not need to count `len(targets)` themselves.

**Manual/Scripted Verification (via `TestClient` against a full FastAPI app + real SQLite database):**

- ✅ Successful creation targeting 2 clients: `201 Created`; response contains the batch id, the correct `repository_id`/`created_by_admin_id`, and exactly 2 targets, each `status: "Pending"`
- ✅ Unauthenticated request (no administrator session): rejected `401 Unauthorized`
- ✅ Missing/invalid CSRF token: rejected `403 Forbidden`
- ✅ Duplicate client id within the same request: rejected `422` at the schema validation layer, before the service is invoked
- ✅ Nonexistent repository package id: rejected `404 Not Found` (`RepositoryPackageNotFoundError`, reused unmodified from REP-002)
- ✅ Repository package that exists but is `Inactive` (deactivated): rejected `400 Bad Request` (`DeploymentPackageUnavailableError`)
- ✅ Nonexistent target client id: rejected `404 Not Found` (`DeploymentClientNotFoundError`), naming the missing id
- ✅ Target client that already has an active (`Pending`) deployment target from a prior successful request: rejected `409 Conflict` (`DeploymentClientActiveError`), naming the conflicting client id
- ✅ Empty `client_ids` list: rejected `422` (schema `min_length=1` constraint)
- ✅ **Atomicity verified directly against the database:** after exercising every rejection scenario above, exactly one `Deployment` row and exactly two `DeploymentTarget` rows exist in total — confirming no partial batch, orphaned deployment, or orphaned target was ever left behind by a rejected request
- ✅ **Audit logging verified directly against the database:** exactly one `DEPLOYMENT_CREATED` audit log entry exists (recorded only for the single successful creation; no entry was written for any of the rejected attempts, consistent with nothing committing on a validation failure)
- ✅ Full application import and OpenAPI schema generation confirmed `POST /api/admin/deployments` registers correctly alongside all existing routes
- ✅ `pyflakes` reports no warnings across all new/modified files
- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, CLIENT-002, INV-001, INV-002, REP-001, or REP-002 — `RepositoryService`, `RepositoryPackageRepository`, `VersionComparisonService`, `ClientRepository`, and every existing endpoint were not behaviorally modified beyond the additive `DeploymentServiceDependency` in `backend/api/dependencies.py` and the additive router registration in `backend/main.py`

**Important Note:** No database schema or migration changes were required — `Deployment` and `DeploymentTarget` (defined by CORE-002) already had every column this ticket needed (including the `uq_deployment_target_deployment_client` unique constraint and `ix_deployment_targets_client_status` index). Deployment *execution* — installer download/checksum verification (DEPLOY-003), silent installation and status reporting (DEPLOY-003/DEPLOY-004), and deployment cancellation (a later ticket per the Backlog) — remains unimplemented as of this ticket; agent polling was subsequently implemented by DEPLOY-002 (below).

---

### DEPLOY-002 — Agent Polling

| Status | ✅ Production Ready |

**Objective:** Implement Client Agent deployment polling (Backlog DEPLOY-002, FR-009 Deployment Job Retrieval / Client Polling): allow the authenticated Client Agent to periodically ask the CPMS Server whether it has a pending deployment assigned to it, scoped strictly to the authenticated client's own identity, building on the deployment batch/target persistence already implemented by DEPLOY-001.

**Features Implemented:**

- `DeploymentRepository` (introduced by DEPLOY-001) extended with:
  - `get_pending_target_for_client(db, client_id)` — a strictly client-scoped, read-only query returning the requesting client's oldest `Pending` `DeploymentTarget`, or `None`. Deliberately filters on `DeploymentStatus.PENDING` only (not the broader `ACTIVE_DEPLOYMENT_STATUSES` set used by DEPLOY-001's Business-Rule-9 check), since `Downloading`/`Installing` represent a deployment the client has already claimed and moved past the "not yet retrieved" state FR-009 describes. `.limit(1)` + `created_at` ascending is a defensive safeguard — Business Rule 9 (enforced since DEPLOY-001) already guarantees at most one non-terminal target per client.
- `DeploymentService` (introduced by DEPLOY-001) extended with:
  - `poll_pending_deployment(db, *, client)` — accepts the *already-authenticated* `Client` object (never a client id from request input) and delegates to `DeploymentRepository.get_pending_target_for_client(db, client.id)`. Purely read-only: no `db.add`/`flush`/`commit` occurs, and `DeploymentTarget.status` is never mutated by this method (see Design Decisions below). Not audit-logged (routine, frequent traffic — only the application logger records each poll), mirroring `HeartbeatService.record_heartbeat`'s established rationale.
- `backend/schemas/deployment.py` extended with three new response-only DTOs (no new request schema — the poll takes no input beyond the authenticated identity):
  - `DeploymentPollPackageDetail` — the associated repository package's Client-Agent-relevant fields (`software_name`, `version`, `installer_type`, `installer_filename`, `silent_command`, `checksum`, `file_size`); deliberately omits administrator-only fields (`approval_status`, timestamps) that `RepositoryPackageResponse` exposes to the dashboard
  - `DeploymentPollTargetResponse` — `target_id` (this client's `DeploymentTarget.id`), `deployment_id` (the batch id), `status`, `created_at`, and the nested `package`
  - `DeploymentPollResponse` — `has_deployment: bool` + `deployment: Optional[DeploymentPollTargetResponse]`
- New Client-Agent-facing, read-only endpoint: `GET /api/agent/deployments/poll` (Backlog DEPLOY-002 "Polling endpoint" deliverable), added directly to the existing `backend/api/routers/agent.py` router — **no new router was created**, since this router's `dependencies=[Depends(require_client_api_key)]` already protects every route declared on it (the same pattern already used for `/heartbeat` and `/inventory/upload`)
  - Uses `CurrentClient` (resolved by the existing `require_client_api_key`/AUTH-002 dependency) as the *sole* source of polling identity — no client id is ever accepted from the request body, query string, or path
  - Returns `200 OK` with `has_deployment: false` (not `404`) when nothing is pending — a routine, expected polling outcome, not an error
  - Returns `200 OK` with `has_deployment: true` and the full `DeploymentPollTargetResponse` (including nested package metadata: checksum, silent command, installer filename/type, file size) when a `Pending` target exists
  - Router handler stays thin: authenticates (via the router-wide dependency + `CurrentClient`), delegates to `DeploymentService.poll_pending_deployment`, shapes the response — no business logic in the router

**No new files, no `main.py` changes, no model changes, no migration changes** — `backend/api/routers/agent.py` (existing router) was extended with one endpoint; `backend/repositories/deployment_repository.py`, `backend/services/deployment_service.py`, and `backend/schemas/deployment.py` (all introduced by DEPLOY-001) were extended, not replaced. `agent_router` was already registered in `backend/main.py` prior to this ticket, so no router-registration change was needed.

**Design Decisions (Documented):**

- **No status transition on poll (`Pending` stays `Pending`):** FR-009's own functional behavior (steps 1–6) describes searching for and returning a pending deployment; it does not describe a status change. FR-012's Deployment Status Values table ties the `Pending → Downloading` transition to the Client Agent *beginning the installer download* (FR-010) and *reporting* that transition (FR-012 step 1) — both explicitly DEPLOY-003/DEPLOY-004 scope, out of bounds for this ticket ("DEPLOY-002 IS POLLING ONLY... DO NOT IMPLEMENT... Installation status reporting"). Mutating `DeploymentTarget.status` on poll would perform DEPLOY-004's work prematurely and would let a client claim a target without ever downloading it. This resolves the ambiguity flagged in CURRENT_STATE v1.1's "Key Decision for DEPLOY-002 (Upcoming)" note in favor of "poll is a pure read."
- **Client Isolation enforced at the query layer, not just the handler:** `get_pending_target_for_client` filters on `client_id` inside the SQL `WHERE` clause itself — there is no code path anywhere in the poll flow that accepts a client id from request input; the authenticated `CurrentClient.id` is the only identity ever passed down from the router to the service to the repository.
- **`Pending`-only match, not the full active-status set:** Reusing `get_active_target_for_client`/`get_active_targets_for_clients` (DEPLOY-001, matches `Pending`/`Downloading`/`Installing`) would have let a client "re-poll" a deployment it has already moved into `Downloading`/`Installing`. A new, narrower query (`get_pending_target_for_client`, `Pending` only) was added instead, keeping the DEPLOY-001 methods and their Business-Rule-9 semantics completely unchanged.
- **No audit log entry for a poll:** Mirrors `HeartbeatService.record_heartbeat`'s already-documented rationale — polling is routine, frequent, non-security-relevant traffic, not a rare higher-value event like registration or key issuance. FR-009 itself says polling activity "may be recorded," not "shall be recorded in the audit log" (unlike FR-016's explicit audit-logged-events list, which does not mention polling).
- **`200 OK` with `has_deployment: false`, not `404`, when nothing is pending:** "No work to do right now" is an expected, routine outcome of polling for a Client Agent (FR-009 Alternative Flow: "the server returns a 'No Pending Deployment' response"), not an error condition — modeling it as a `404` would make ordinary polling traffic register as constant client-side/observability errors.
- **Endpoint placed on the existing `agent.py` router, at `/api/agent/deployments/poll`:** PRS Appendix B documents the literal path `/api/deployments/poll`, but — consistent with the precedent already set by `/api/agent/heartbeat` (CLIENT-002) and `/api/agent/inventory/upload` (INV-001), both of which also deviate from their PRS-literal paths for the same reason — every authenticated, already-registered-client endpoint is centralized under `/api/agent` so it automatically inherits the router-wide `require_client_api_key` dependency, rather than requiring each new agent endpoint to remember to declare authentication individually.

**Manual/Scripted Verification (via `TestClient` against a real, Alembic-migrated SQLite database):**

- ✅ Poll before any deployment exists for the client: `200 OK`, `has_deployment: false`, `deployment: null`
- ✅ Poll without an `Authorization` header: rejected `401 Unauthorized`
- ✅ Repository package upload (REP-001, unmodified) + deployment creation (DEPLOY-001, unmodified) targeting Client A only
- ✅ Poll as Client A after deployment creation: `200 OK`, `has_deployment: true`; response includes the correct `deployment_id` (matching the batch id returned by `POST /api/admin/deployments`), `target_id`, `status: "Pending"`, and the full nested `package` (software name, version, installer type, filename, silent command, checksum, file size) matching the uploaded package
- ✅ **Client Isolation verified directly:** Client B polling at the same time (with no deployment of its own) receives `has_deployment: false` — confirmed Client B never receives any part of Client A's deployment
- ✅ Repeated poll as Client A: idempotent — `target_id` and `status` (`"Pending"`) are identical across repeated calls; confirms the endpoint does not mutate `DeploymentTarget.status`
- ✅ A second deployment created (DEPLOY-001) targeting Client B only: Client B's subsequent poll returns its own deployment (`has_deployment: true`), with a `deployment_id` different from Client A's — confirmed each client only ever sees its own batch
- ✅ Full application import and OpenAPI schema generation confirmed `GET /api/agent/deployments/poll` registers correctly alongside all 14 other existing routes
- ✅ `pyflakes` reports no new warnings across all new/modified files, and no new warnings across the full `backend/` tree beyond the pre-existing, already-documented unused-import nit in `auth_service.py`
- ✅ No regressions detected in CORE-001, CORE-002, AUTH-001, AUTH-002, CLIENT-001, CLIENT-002, INV-001, INV-002, REP-001, REP-002, or DEPLOY-001 — `DeploymentService.create_deployment`, `DeploymentRepository`'s DEPLOY-001 methods, `RepositoryService`, `RepositoryPackageRepository`, `VersionComparisonService`, `ClientRepository`, and every existing endpoint (including `POST /api/admin/deployments`, exercised again in this same test run) were not behaviorally modified

**Important Note:** DEPLOY-002 is polling-only, as scoped. It does not download the installer, verify its checksum on the client side, execute it, report status, or transition `DeploymentTarget.status`. Every `DeploymentTarget` a Client Agent retrieves via this endpoint remains `Pending` until a future ticket (DEPLOY-003 for download/execution, DEPLOY-004 for status reporting) implements those steps and reports the resulting transition back to the server.

---
## Current System State

### APIs Available (Implemented)

| Method | Endpoint                                  | Description                                            | Auth                                  |
| ------ | ------------------------------------------ | -------------------------------------------------------- | -------------------------------------- |
| GET    | `/api/health`                             | Health check                                            | None                                  |
| POST   | `/api/admin/login`                        | Administrator login                                      | None                                  |
| POST   | `/api/admin/logout`                       | Administrator logout                                     | Admin session                         |
| GET    | `/api/admin/me`                           | Current administrator information                        | Admin session                         |
| POST   | `/api/admin/keys`                         | Issue client provisioning key (FR-020)                   | Admin session + CSRF                  |
| GET    | `/api/admin/clients/{client_id}/updates`  | Compare a client's inventory against the repository (FR-007) | Admin session                     |
| POST   | `/api/admin/repository/packages`          | Upload an approved installer package (FR-006)             | Admin session + CSRF                  |
| GET    | `/api/admin/repository/packages`          | List/search repository packages (FR-006, REP-002)         | Admin session                         |
| GET    | `/api/admin/repository/packages/{package_id}` | Retrieve a single repository package's details (REP-002) | Admin session                     |
| POST   | `/api/admin/repository/packages/{package_id}/deactivate` | Deactivate ("remove") a repository package (FR-017, REP-002) | Admin session + CSRF          |
| POST   | `/api/admin/deployments`                  | Create a deployment batch targeting one or more clients (FR-008, FR-009) | Admin session + CSRF  |
| POST   | `/api/register`                           | Client registration                                       | Provisioning key or existing API key  |
| GET    | `/api/agent/ping`                         | Verify client authentication                              | Client API key                        |
| POST   | `/api/agent/heartbeat`                    | Report client heartbeat                                   | Client API key                        |
| POST   | `/api/agent/inventory/upload`             | Upload complete installed software inventory (FR-005)     | Client API key                        |
| GET    | `/api/agent/deployments/poll`             | Poll for the authenticated client's own pending deployment (FR-009, DEPLOY-002) | Client API key   |

### Database Status

- SQLite database initialized with all migrations applied
- Tables: `administrators`, `administrator_sessions`, `clients`, `client_provisioning_keys`, `software_inventories`, `repository_packages`, `deployments`, `deployment_targets`, `audit_logs`, `alembic_version`
- All models use UUID primary keys
- Relationships and constraints defined
- Audit logging integrated for all authentication, registration, repository upload, repository deactivation, and deployment creation events
- **No schema changes in REP-001** — `repository_packages` already had every column this ticket needed (CORE-002); no migration was added
- **No schema changes in REP-002** — the listing, detail, and deactivation operations use only existing `repository_packages` columns (including `created_at`/`updated_at`, already present via `AuditModel`); no migration was added
- **No schema changes in DEPLOY-001** — `deployments` and `deployment_targets` (CORE-002) already had every column, constraint, and index this ticket needed (`uq_deployment_target_deployment_client`, `ix_deployment_targets_client_status`); no migration was added. `deployments`/`deployment_targets` now contain real rows for the first time since CORE-002 defined them.
- **No schema changes in DEPLOY-002** — polling is a pure read against the existing `deployment_targets`/`deployments`/`repository_packages` tables via a new repository query method only; no new column, table, constraint, or migration was needed. Polling does not write to the database at all (no `INSERT`/`UPDATE` of any kind).

### Authentication Status

**Administrator:**
- Session-based (HttpOnly cookie + separate CSRF cookie)
- Double-submit CSRF protection
- Sliding inactivity expiry
- `Secure` flag configurable (`SESSION_COOKIE_SECURE`, default `False` for HTTP-only prototype — **must set `True` for HTTPS**)
- `POST /api/admin/repository/packages` (REP-001) requires both the session cookie and a valid CSRF token, consistent with every other state-changing administrator endpoint
- `POST /api/admin/repository/packages/{package_id}/deactivate` (REP-002) likewise requires both the session cookie and a valid CSRF token; `GET /api/admin/repository/packages` and `GET /api/admin/repository/packages/{package_id}` (REP-002) are read-only and require only the session cookie, consistent with `GET /api/admin/clients/{client_id}/updates` (INV-002)
- `POST /api/admin/deployments` (DEPLOY-001) likewise requires both the session cookie and a valid CSRF token, since deployment creation is state-changing

**Client:**

- `Authorization: Bearer <api_key>` header
- SHA-256 hash-at-rest validated against `Client.api_key_hash`
- Router-level protection for all `/api/agent/*` routes
- Registration endpoint uses its own credential resolution (existing `Client` OR unclaimed `ClientProvisioningKey`)
- Authenticated inventory uploads use the existing API key authentication without additional authorization requirements
- `GET /api/agent/deployments/poll` (DEPLOY-002) uses the same router-level `require_client_api_key` protection as every other `/api/agent/*` route; the authenticated `CurrentClient.id` is the only identity used to scope the deployment query — no client id is ever accepted from request input

### Repository Workflow (New — REP-001)

```text
1. Administrator authenticates
   → POST /api/admin/login

2. Administrator uploads an installer package
   → POST /api/admin/repository/packages
   (multipart/form-data: installer file + software_name, version,
    installer_type, silent_command)
   ├── Extension validated against installer_type
   ├── Duplicate (same name+version, APPROVED) rejected → 409
   ├── File streamed to repository/ under a generated UUID4 filename
   ├── SHA-256 checksum computed while streaming
   └── RepositoryPackage record persisted (status: APPROVED)

3. Administrator reviews version comparison
   → GET /api/admin/clients/{client_id}/updates
   └── Newly uploaded packages are picked up automatically —
       VersionComparisonService and this endpoint were not modified

4. Administrator browses/searches the repository (New — REP-002)
   → GET /api/admin/repository/packages[?search=...&approval_status=...]
   └── Returns packages ordered by software_name, then version

5. Administrator views a package's full details (New — REP-002)
   → GET /api/admin/repository/packages/{package_id}
   └── Returns metadata including checksum, silent_command,
       approval_status, created_at, updated_at

6. Administrator removes an obsolete package (New — REP-002)
   → POST /api/admin/repository/packages/{package_id}/deactivate
   ├── approval_status: Approved → Inactive (logical removal, FR-017)
   ├── Package row and any Deployment relationships preserved
   └── Package immediately excluded from list_approved / duplicate
       detection / version comparison (no changes required to either)
```

### Client Workflow (Unchanged from v0.8)

```text
1. Administrator issues provisioning key
   → POST /api/admin/keys

2. Client Agent presents provisioning key
   → POST /api/register
   ├── New agent_guid → Create Client (UNKNOWN status)
   └── Existing agent_guid → Update registration

3. Client Agent authenticates
   → Authorization: Bearer <API Key>

4. Client Agent reports heartbeat
   → POST /api/agent/heartbeat
   └── Client status → ONLINE
   └── last_heartbeat updated

5. Client Agent uploads software inventory
   → POST /api/agent/inventory/upload
   └── Inventory synchronized with database
      ├── New software inserted
      ├── Existing software updated
      └── Removed software deleted

6. Administrator reviews version comparison
   → GET /api/admin/clients/{client_id}/updates
   └── Each installed item classified: Up-to-Date / Update Available / Not Managed
```

### Deployment Creation Workflow (New — DEPLOY-001)

```text
1. Administrator authenticates
   → POST /api/admin/login

2. Administrator selects an approved package and one or more clients,
   then creates a deployment batch
   → POST /api/admin/deployments
   (JSON body: repository_package_id, client_ids: [...])
   ├── Repository package existence + Approved status validated
   │   (reuses RepositoryService.get_package, REP-002)
   ├── Every client_id validated against registered clients
   │   (reuses ClientRepository.get_by_id, INV-002)
   ├── Duplicate client_ids rejected (schema-level, 422)
   ├── Clients with an existing active (Pending/Downloading/Installing)
   │   deployment target rejected (Business Rule 9, PRS §2.7) → 409
   ├── One Deployment (batch) record created
   ├── One DeploymentTarget record created per validated client,
   │   status: Pending
   ├── DEPLOYMENT_CREATED audit log entry recorded
   └── All of the above committed atomically — a rejected request
       never leaves a partial Deployment/DeploymentTarget behind

3. Client Agent polls for its Pending deployment target (New — DEPLOY-002)
   → GET /api/agent/deployments/poll
   ├── Scoped strictly to the authenticated client (Authorization:
   │   Bearer <api_key> → CurrentClient.id) — never a client id from
   │   request input
   ├── Returns has_deployment: true + target_id, deployment_id (batch
   │   id), status ("Pending"), and the full package details (software
   │   name, version, installer type/filename, silent command,
   │   checksum, file_size) if a Pending target exists for this client
   ├── Returns has_deployment: false (still 200 OK) if none exists
   └── Read-only: does NOT transition DeploymentTarget.status,
       download the installer, or write an audit log entry

4. (Future — DEPLOY-003/DEPLOY-004) Client Agent downloads the
   installer, verifies its checksum, executes it silently, and
   reports the result (Downloading/Installing/Completed/Failed) back
   to the server — not yet implemented; every DeploymentTarget
   retrieved via step 3 above remains Pending indefinitely until those
   tickets are completed
```

## Deployment Workflow (Creation + Polling Implemented)

- Local Package Repository: **upload implemented (REP-001)**, **administrator listing/search/details/deactivation implemented (REP-002)**
- Deployment Creation: **implemented (DEPLOY-001)** — `POST /api/admin/deployments` creates a batch + one Pending target per targeted client; validated against package approval status, client existence, and Business Rule 9 (one active deployment per client)
- Deployment Polling: **implemented (DEPLOY-002)** — `GET /api/agent/deployments/poll` returns the authenticated client's own Pending deployment target (if any), scoped strictly to that client, with no status transition and no audit log entry
- Deployment *execution* — installer download/execution (DEPLOY-003), status reporting (DEPLOY-004), deployment cancellation, and a deployment-history dashboard remain **not yet implemented**
- Silent Installers: not yet executed by a deployment (silent command is validated and stored at upload time, and is now returned to the polling client via DEPLOY-002; execution belongs to DEPLOY-003 client-side work, already partially anticipated by the existing FR-011 direct-process-execution design)
- SHA-256 Package Validation: **upload-time computation now implemented** (REP-001, `RepositoryPackage.checksum`); the checksum is now also **returned to the polling Client Agent** (DEPLOY-002, `DeploymentPollPackageDetail.checksum`); download-time re-verification by the Client Agent (FR-010/FR-011) remains part of DEPLOY-003

### Existing Infrastructure

- **No automated test framework** configured (`pytest` not in `requirements.txt`; `tests/` directory remains an empty skeleton). All verification is currently performed through manual API testing, PowerShell scripts, direct SQLite inspection, and (for INV-002/REP-001/DEPLOY-001/DEPLOY-002) ad hoc scripted verification using FastAPI's `TestClient`.
- **No scheduler/background tasks** — client `OFFLINE` status is currently computed at read time rather than maintained by a background service. Version comparison (INV-002) follows this same "computed at read time" pattern.
- **Repository package listing/detail/deactivation implemented (REP-002)** — `GET /api/admin/repository/packages` (list/search), `GET /api/admin/repository/packages/{package_id}` (details), and `POST /api/admin/repository/packages/{package_id}/deactivate` (remove) are all available. Metadata *editing* (e.g. changing the silent install command after upload) remains unimplemented.
- **No administrator-facing inventory or client listing endpoints** — client registration and software inventory data are stored successfully and can be compared against the repository (INV-002) and now populated via real uploads (REP-001) and browsed via the repository dashboard endpoints (REP-002), but there is still no general "list clients" or "list inventory" endpoint. These capabilities remain planned for a future dashboard-facing ticket.
- **Deployment creation and polling implemented (DEPLOY-001, DEPLOY-002)** — `POST /api/admin/deployments` creates a batch + one Pending target per targeted client, and `GET /api/agent/deployments/poll` lets the targeted Client Agent retrieve its own Pending target. There is still no administrator-facing "list deployments"/"deployment history" endpoint (DASH-002/a future ticket) and no installer download/execution/status-reporting endpoint yet (DEPLOY-003/DEPLOY-004), so a created deployment currently has no way to progress beyond `Pending` (it can now be *retrieved* by its client via polling, but not yet acted upon) or be observed again by the administrator after creation except via direct database inspection.
- **Client Agent scaffolding implemented** — communication layer, inventory scanner, and application entry point exist; automated Windows Registry inventory collection and DEPLOY-002 polling consumption will be exercised through the deployed Windows Agent in future milestones.
- **No frontend UI** (Jinja2 templates not yet wired; HTMX optional and not yet implemented).
- **No CORS configuration for credentialed cross-origin clients** — `CORS_ORIGINS` currently defaults to `"*"` with `allow_credentials=True`, which browsers reject. This is acceptable for the current same-origin prototype but will require explicit origin configuration before introducing a separate frontend.

---

## Ticket History

### CORE-001 — Backend Foundation

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Establish project structure and base infrastructure |
| **Deliverables** | FastAPI app, config loader, DI, logging, startup events, Swagger |
| **Regression** | Passed (re-verified in CLIENT-001 closeout) |

---

### CORE-002 — Database Layer

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Define data models, ORM configuration, and migrations |
| **Deliverables** | All models (9 tables), Alembic setup, relationships, constraints |
| **Regression** | Passed (migration round-trip re-verified) |

---

### AUTH-001 — Administrator Authentication

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Implement admin login, session management, and CSRF protection |
| **Deliverables** | Login/logout/me endpoints, session cookie + CSRF, bcrypt hashing, audit logging, admin creation CLI |
| **Documented Deviation** | Session-based (not JWT) per FR-019/NFR-028/PRS Appendix B |
| **Regression** | Passed (re-verified in CLIENT-001 closeout) |

---

### AUTH-002 — Client Authentication

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Implement API key validation for client agents |
| **Deliverables** | API key auth, `require_client_api_key` dependency, router-level protection, `/api/agent/ping`, dev seed utility |
| **Scoping Decision** | FR-020 (key provisioning) deferred to CLIENT-001 |
| **Regression** | Passed (full test inventory re-verified) |

---

### CLIENT-001 — Client Registration

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Implement client registration (FR-001) and minimal FR-020 provisioning |
| **Deliverables** | `POST /api/register`, `POST /api/admin/keys`, `ClientProvisioningKey` model, conflict handling |
| **Conflict Resolution** | Registration cannot use `require_client_api_key` (see Architecture Notes); implemented own credential resolution on separate router |
| **Regression** | Passed (20+ new checks + full regression suite) |

---

### CLIENT-002 — Heartbeat Service

| Status | ✅ Production Ready |
|--------|---------------------|
| **Purpose** | Implement client liveness reporting (FR-003) |
| **Deliverables** | `POST /api/agent/heartbeat`, `HeartbeatService`, status transition to `ONLINE`, `last_heartbeat` persistence |
| **Regression** | Passed (manual end-to-end verification) |

---
### INV-001 — Inventory Collection

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Implement authenticated software inventory collection and synchronization (FR-005)                                                                        |
| **Deliverables** | `POST /api/agent/inventory/upload`, `InventoryService`, `SoftwareInventoryRepository`, `InventoryUploadRequest`, inventory snapshot synchronization, Client Agent inventory scaffolding |
| **Regression**   | Passed (manual end-to-end verification)                                                                                                                    |

---

### INV-002 — Version Comparison

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Compare installed software (INV-001) against the approved repository catalog and classify each item as Up-to-Date, Update Available, or Not Managed (FR-007) |
| **Deliverables** | `backend/utils/version_compare.py`, `RepositoryPackageRepository`, `VersionComparisonService`, `UpdateStatus` enum, `backend/schemas/updates.py`, `ClientRepository.get_by_id`, `GET /api/admin/clients/{client_id}/updates` |
| **Documented Limitation** | Publisher-based match disambiguation not applied against the repository catalog — `RepositoryPackage` has no `publisher` column in the existing schema; matching is name-only |
| **Regression**   | Passed (scripted unit tests for utility functions, ORM-level service tests, and `TestClient` API-level tests; no existing files behaviorally modified beyond the additive `ClientRepository.get_by_id`) |

---

### REP-001 — Repository Management

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Implement the local software package repository: installer upload, metadata validation, SHA-256 checksum computation/verification, and package storage (FR-006) |
| **Deliverables** | `backend/utils/file_storage.py`, `backend/schemas/repository.py`, `RepositoryPackageRepository.create`/`get_active_conflict`, `RepositoryService`, `POST /api/admin/repository/packages`, `Settings.MAX_INSTALLER_UPLOAD_SIZE_MB` |
| **Design Decisions** | Duplicate detection scoped to `APPROVED` packages sharing a normalized name + exact version; uploaded packages default to `APPROVED` (no separate approval workflow defined); silent command safety validated at upload time in addition to FR-011's existing execution-time control |
| **Regression**   | Passed (`TestClient`-based end-to-end verification of success, duplicate-conflict, extension-mismatch, invalid-silent-command, missing-CSRF, and unauthenticated scenarios; `pyflakes` clean; no existing files behaviorally modified beyond the additive `RepositoryPackageRepository` methods) |

---

### REP-002 — Repository Dashboard

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Provide administrator-facing management of uploaded repository packages: list/browse, search, view package details, and remove (deactivate) obsolete packages (FR-006 dashboard integration, FR-017 Repository Maintenance) |
| **Deliverables** | `RepositoryPackageRepository.list_all`/`get_by_id`/`deactivate`, `RepositoryService.list_packages`/`get_package`/`deactivate_package`, `RepositoryPackageNotFoundError`, `RepositoryPackageListResponse`, `RepositoryPackageResponse.created_at`/`updated_at`, `GET /api/admin/repository/packages`, `GET /api/admin/repository/packages/{package_id}`, `POST /api/admin/repository/packages/{package_id}/deactivate` |
| **Design Decisions** | Removal implemented as a logical `approval_status → INACTIVE` change (reusing the pre-existing status field/semantics), not a physical delete; deactivation is idempotent; listing returns packages of any status by default with an optional status filter; search is a simple case-insensitive substring match on name/version; no new database schema or migration required |
| **Regression**   | Passed (`TestClient`-based end-to-end verification of listing, search, status filtering, package details, not-found handling, missing-CSRF rejection, and successful deactivation; `pyflakes` clean; `RepositoryService.upload_package`, `VersionComparisonService`, and `RepositoryPackageRepository.list_approved`/`get_active_conflict`/`create` were not behaviorally modified) |

---

### DEPLOY-001 — Deployment Creation

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Allow an administrator to create a deployment batch targeting one or more registered clients with a single approved repository package (FR-008 Deployment Job Creation, FR-009 Deployment Job Retrieval targeting) |
| **Deliverables** | `backend/repositories/deployment_repository.py` (`DeploymentRepository`), `backend/services/deployment_service.py` (`DeploymentService` + `DeploymentPackageUnavailableError`/`DeploymentClientNotFoundError`/`DeploymentClientActiveError`), `backend/schemas/deployment.py` (`DeploymentCreateRequest`/`DeploymentTargetResponse`/`DeploymentResponse`), `backend/api/routers/deployments.py`, `POST /api/admin/deployments`, `DeploymentServiceDependency` |
| **Design Decisions** | Business Rule 9 ("one active deployment per client") enforced in the Service Layer, not the model, per the design note already present on `DeploymentTarget`; `Pending`/`Downloading`/`Installing` treated as active/non-terminal (existing `DeploymentStatus` values, no new status introduced); package validation reuses `RepositoryService.get_package` (composition, not duplication); full validation (package → clients exist → clients not active) runs before any row is created, so a rejected request never leaves a partial batch; single `db.commit()` at the end, consistent with every other service's transaction pattern |
| **Regression**   | Passed (`TestClient`-based end-to-end verification of successful creation, unauthenticated/missing-CSRF rejection, duplicate-client/empty-list schema rejection, nonexistent/inactive-package rejection, nonexistent-client rejection, active-deployment-conflict rejection; atomicity and audit-log-count verified by direct database inspection after exercising every rejection path; `pyflakes` clean; `RepositoryService`, `RepositoryPackageRepository`, `VersionComparisonService`, and `ClientRepository` were not behaviorally modified) |

---

### DEPLOY-002 — Agent Polling

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Allow the authenticated Client Agent to periodically retrieve its own pending deployment job, scoped strictly to its identity (FR-009 Deployment Job Retrieval / Client Polling) |
| **Deliverables** | `DeploymentRepository.get_pending_target_for_client` (extended), `DeploymentService.poll_pending_deployment` (extended), `backend/schemas/deployment.py` (`DeploymentPollPackageDetail`/`DeploymentPollTargetResponse`/`DeploymentPollResponse`, extended), `GET /api/agent/deployments/poll` on the existing `backend/api/routers/agent.py` |
| **Design Decisions** | No status transition on poll — `Pending → Downloading` is tied by FR-012 to the client *reporting* the start of the download (FR-010), which is DEPLOY-003/DEPLOY-004 scope, not this ticket's; client isolation enforced at the query layer (`WHERE client_id = :authenticated_client_id`), never via a request-supplied id; matches `Pending` only (not the broader active-status set used by DEPLOY-001's Business-Rule-9 check); no audit log entry for a poll (routine traffic, mirrors `HeartbeatService`); `200 OK` + `has_deployment: false` (not `404`) when nothing is pending; endpoint added to the existing `agent.py` router (no new router, no new `main.py` registration needed) |
| **Regression**   | Passed (`TestClient`-based end-to-end verification of no-pending-deployment response, unauthenticated rejection, pending-deployment retrieval with full package details, client-isolation between two distinct clients, idempotent repeated polling with no status mutation, and a second client's independent deployment; `pyflakes` clean; `DeploymentService.create_deployment`, `DeploymentRepository`'s DEPLOY-001 methods, and every existing endpoint — including `POST /api/admin/deployments`, re-exercised in the same test run — were not behaviorally modified) |

---
## Pending Backlog

| Ticket | Purpose | Dependencies | Priority |
|--------|---------|--------------|----------|
| **DEPLOY-003** | Installer Download & Execution — client-side | DEPLOY-002 (Agent Polling) ✅ | Next |
| **DEPLOY-004** | Deployment Status Reporting — client reports completion | DEPLOY-003 | - |
| **DASH-001** | Dashboard Home | AUTH-001, INV-001, REP-001 | - |
| **DASH-002** | Deployment Monitoring | DEPLOY-004 | - |
| **DASH-003** | Audit Logs | AUTH-001 | - |
| **SYS-001** | Configuration Management | - | - |
| **SYS-002** | Logging System | - | - |
| **TEST-001** | System Integration Testing | All previous | Milestone 10 |
| **TEST-002** | Documentation & Demonstration | TEST-001 | Final |

---

## Architecture Notes

### Why FastAPI
- Modern, async-capable framework with automatic OpenAPI docs
- Pydantic validation integration
- Dependency injection built-in

### Why SQLite
- Simplicity for proof-of-concept
- No external server dependencies
- SQLAlchemy dialect-portable `Uuid` type for future migration

### Repository Pattern
- All data access through repository layer
- Business logic in service layer
- Thin routers only handle validation, calling services, and responses
- Single shared DI location: `backend/api/dependencies.py`

### Authentication Flows

**Administrator:**
```
1. POST /api/admin/login → validates credentials
2. Creates AdministratorSession → sets HttpOnly cookie + CSRF cookie
3. Subsequent requests: cookie + CSRF header required
4. GET /api/admin/me → returns current admin info
5. POST /api/admin/logout → invalidates session
```

**Client:**
```
1. Admin issues provisioning key → POST /api/admin/keys (FR-020)
2. Client presents key → POST /api/register
   - Resolves against ClientProvisioningKey OR existing Client
   - Creates/updates Client → returns api_key
3. Subsequent requests: Authorization: Bearer <api_key>
4. Router-level protection: require_client_api_key on /api/agent/*
```

### Registration Endpoint Exception
- `POST /api/register` **cannot** use `require_client_api_key` because first-time clients have no `Client` row yet
- Lives on its own router (`registration.py`) — NOT `agent.py`
- Performs inline credential resolution via `ClientAuthService.resolve_registration_credential`
- Any future endpoint with same "no Client row yet" problem should follow this pattern

### API Key Strategy
- Generated with `secrets.token_urlsafe` (256 bits entropy)
- Hashed at rest with SHA-256 (same primitive as admin session tokens)
- Provisioning keys: single-use, deleted upon claim
- Plain-text value returned exactly once by `POST /api/admin/keys`
- Cannot be retrieved again after issuance

### Background Tasks
- **No scheduler infrastructure exists** — no background jobs, no periodic tasks
- Client `OFFLINE` status is **computed at read time** from `last_heartbeat` rather than updated by a background job
- Version comparison (INV-002) results are likewise **computed at read time** on every call to `GET /api/admin/clients/{client_id}/updates`, rather than persisted or cached — see `VersionComparisonService`'s module docstring for the full rationale
- Future tickets needing background processing will need to introduce a scheduler or adapt to read-time computation

### Version Comparison Strategy (INV-002)
- FR-007 matching and comparison rules are implemented as pure, database-independent functions in `backend/utils/version_compare.py` (`normalize_software_name`, `normalize_publisher`, `parse_version`, `compare_versions`), separate from `VersionComparisonService`'s orchestration logic, so the rules themselves can be unit-tested without a database session
- `RepositoryPackage` has no `publisher` column, so publisher is not used to disambiguate repository-catalog matches (installed-item publisher is still recorded and returned in the API response, since `SoftwareInventory` does carry it) — see `VersionComparisonService._select_best_match`'s docstring
- When more than one approved package shares a normalized software name, the candidate with the highest parseable version is preferred
- Results are not persisted; there is no "comparison results" database table (PRS Chapter 7's entity list does not define one) — any future need for historical comparison snapshots is new, additive scope

### Repository Upload Strategy (REP-001)
- Filesystem I/O and hashing logic (`backend/utils/file_storage.py`) is kept pure and database-independent, mirroring `version_compare.py`'s separation, so it can be unit-tested without a database session or a running FastAPI app
- Files are streamed in 1 MiB chunks rather than buffered fully in memory; the SHA-256 checksum is computed incrementally as each chunk is written, avoiding a second full read of a potentially large installer file
- The uploaded file's *extension* (not its content/magic bytes) is validated against the declared Installer Type, per FR-006's literal wording ("Only files with an extension of .exe or .msi shall be accepted, consistent with the Installer Type field"); content-based file-type sniffing was judged out of scope for this ticket
- Duplicate-entry detection (`RepositoryPackageRepository.get_active_conflict`) reuses INV-02's `normalize_software_name` rather than introducing a second name-normalization rule, keeping "does this package already exist" and "does this installed item match a package" consistent
- `RepositoryService.upload_package` orders its checks (extension → duplicate → file write) to fail cheaply before performing the most expensive operation (streaming a potentially large file to disk)

### Deployment Creation Strategy (DEPLOY-001)
- `DeploymentRepository` follows the exact same "pure data-access, no business rules" separation already established by `RepositoryPackageRepository`/`ClientRepository` — the active-deployment lookup methods (`get_active_target_for_client`/`get_active_targets_for_clients`) only *query*; the decision to reject based on their result is made entirely in `DeploymentService`
- `DeploymentService` composes a `RepositoryService` instance (constructor-injected, defaulting to `RepositoryService()`) to reuse `get_package` rather than querying `RepositoryPackageRepository` directly a second time — the same "reuse an existing service rather than duplicate its logic" approach the ticket instructions required
- Validation is strictly ordered and front-loaded: package → clients-exist → clients-not-active, all performed before any `Deployment`/`DeploymentTarget` row is created, so a request that will ultimately fail never leaves partial state behind and never has to be "undone"
- No explicit `db.rollback()` call was added anywhere: because every service method in this codebase (including this one) defers `db.commit()` until the very end of a successful operation, and `get_db()`'s `finally` block only ever calls `db.close()` (never `commit()`), an exception raised mid-method simply results in the session being closed without committing — any `flush()`-ed-but-uncommitted rows are discarded automatically. This is the same implicit pattern already relied upon by every other service.
- `ACTIVE_DEPLOYMENT_STATUSES` (`Pending`, `Downloading`, `Installing`) is defined once, at module scope in `deployment_repository.py`, rather than being duplicated as a literal tuple inside `DeploymentService` — future DEPLOY-* tickets needing the same "is this target still active" concept should import this constant rather than re-deriving it

### Deployment Polling Strategy (DEPLOY-002)
- `get_pending_target_for_client` is a **new, narrower** repository query, deliberately separate from DEPLOY-001's `get_active_target_for_client`/`get_active_targets_for_clients` (which match the broader `ACTIVE_DEPLOYMENT_STATUSES` set and exist solely to enforce Business Rule 9 at creation time). Polling only ever needs to surface `Pending` work; reusing the broader query would have let a client "re-poll" a target it had already moved into `Downloading`/`Installing`. The two DEPLOY-001 methods were left completely untouched.
- Client isolation is enforced **inside the SQL `WHERE` clause** (`DeploymentTarget.client_id == client_id`), not by filtering an already-fetched list in Python and not by trusting anything from the request body/path — `poll_pending_deployment(db, *, client: Client)` only ever receives the already-authenticated `Client` object from `require_client_api_key`/`CurrentClient` (AUTH-002), so there is no code path capable of accepting an arbitrary client id for this purpose.
- **Poll is a pure read, by design, not by omission:** no `db.add`/`db.flush`/`db.commit` call exists anywhere in `poll_pending_deployment` or `get_pending_target_for_client`. This was the resolution to the ambiguity CURRENT_STATE v1.1 flagged in its "Key Decision for DEPLOY-002 (Upcoming)" note (whether `Pending → Downloading` should transition on poll vs. on download-start): FR-009's functional behavior does not describe a status change, and FR-012 ties that transition to the client *reporting* the start of a download (FR-010) — a DEPLOY-003/DEPLOY-004-owned event this ticket must not anticipate.
- Response shaping follows the same `model_config = ConfigDict(from_attributes=True)` + `.model_validate(...)` convention already used by `DeploymentTargetResponse`/`DeploymentResponse` (DEPLOY-001) and `RepositoryPackageResponse` (REP-001/002) — `DeploymentPollPackageDetail.model_validate(target.deployment.repository_package)` builds directly from the ORM relationship chain rather than manually copying fields.
- The endpoint was added to the **existing** `backend/api/routers/agent.py` router rather than a new router, reusing that router's `dependencies=[Depends(require_client_api_key)]` router-wide protection — the same centralization pattern CLIENT-002 (`/heartbeat`) and INV-001 (`/inventory/upload`) already established, so `main.py` required no changes (`agent_router` was already registered).

### Future Migration Considerations
- SQLAlchemy dialect-portable `Uuid` type used for all primary/foreign keys (deliberate deviation from PRS's illustrative auto-increment integers — documented in `backend/models/base.py`)
- `Secure` cookie flag configurable — must be set `True` once HTTPS is deployed
- CORS with credentials requires concrete origin list (not `"*"`) for cross-origin requests

---

## Known Issues / Technical Debt

| Issue | Status | Impact |
|-------|--------|--------|
| **No automated test framework** | Tracked | All verification manual/scripted; `tests/` empty; `pytest` not in requirements |
| **Router-level agent protection not automatically inherited** | Process risk | Future routers must independently apply `dependencies=[Depends(require_client_api_key)]` unless documented exception (registration) |
| **No admin-facing listing endpoints** | Tracked | Clients, provisioning keys, and repository packages only visible via direct database inspection or (for repository packages) indirectly through the version-comparison endpoint; REP-002 added a repository package listing view, but there is still no "list clients" or "list deployments" endpoint |
| **`RepositoryPackage` has no `publisher` column** | Tracked | FR-007's optional publisher-based match disambiguation cannot be applied against the repository catalog until/unless a future ticket adds this column and a migration |
| **No approval workflow for uploaded packages** | Tracked | REP-001 persists every valid upload directly as `APPROVED`; if a future requirement calls for a distinct upload → pending-approval → approved workflow, this will need a follow-up ticket |
| **Pre-existing cosmetic nit** | Untouched | `auth.py` declares unused `logger` (not called, left per "do not modify completed tickets unless integration requires") |
| **CORS + credentialed cross-origin** | Condition | `CORS_ORIGINS="*"` + `allow_credentials=True` is invalid for browsers; needs concrete origin list for separate frontend |
| **`dev_seed_client.py` not retired** | Untouched | Still functional; retiring judged out of scope for CLIENT-001 review |
| **No expiration/revocation for provisioning keys** | Future work | Issued-but-never-claimed keys remain valid indefinitely; worth revisiting with dashboard/key-management ticket |
| **No scheduler for OFFLINE detection** | Design choice | Offline status computed at read time; background jobs not yet introduced |
| **`updated_at` serves as registration timestamp** | Implicit | No separate `last_registration` field; registration updates touch `updated_at` |
| **No client-side download-time checksum re-verification yet** | Tracked | REP-001 computes and stores the checksum at upload time (FR-006); the Client Agent's download-time re-verification (FR-010/FR-011) is DEPLOY-003 scope, not yet implemented |
| **Deployment targets have no way to progress past `Pending`** | Tracked | DEPLOY-002 lets a Client Agent *retrieve* its own `Pending` target (by design, without transitioning its status); installer download/execution (DEPLOY-003) and status reporting (DEPLOY-004) remain unimplemented, so every `DeploymentTarget` still stays `Pending` indefinitely until those tickets land |
| **No deployment cancellation or history endpoint yet** | Tracked | A created deployment can currently only be observed by an administrator via direct database inspection (though the *targeted client* can now observe its own via polling — DEPLOY-002); a future ticket (DASH-002 or a dedicated DEPLOY-* ticket) is expected to add admin-facing listing/cancellation |
| **No client-side consumption of the polling endpoint yet** | Tracked | `GET /api/agent/deployments/poll` (DEPLOY-002) is server-side complete and verified via `TestClient`; the `agent/` package's `deployment`/`installer` modules that will actually call it from a real Windows Client Agent do not exist yet (DEPLOY-003 scope, per the SAD §7.5 directory layout) |

---

## Important Context for Future Development

### Development Rules (Must Follow)
1. Respect existing architecture — do not redesign completed modules
2. Build incrementally — extend existing services/repositories, don't create replacements
3. Maintain backward compatibility
4. Keep routers thin — business logic in services, data access in repositories
5. Implement production-quality code — no TODO placeholders
6. Satisfy all acceptance criteria

### Definition of Done
- Code compiles
- Acceptance criteria satisfied
- Logging implemented
- Exceptions handled
- Tests pass (manual verification currently)
- Documentation updated if necessary
- No TODO placeholders remain
- Existing architecture preserved

### Coding Standards
- SOLID Principles
- Clean Code
- Dependency Injection
- Repository Pattern
- Service Layer Pattern
- Modular Design
- Avoid duplicate implementations

### Logging Standards
- Every important operation generates logs
- Authentication: admin successes + failures; client failures only (successes not individually audit-logged per AUTH-002 rationale)
- Registration, inventory, repository, deployment operations logged
- Version comparison (INV-002) logs at DEBUG level only (a read-only query, not a state-changing operation warranting an audit-log entry — no FR-007 examples appear in the PRS's audit-logged-events list)
- Repository package uploads (REP-001) are audit-logged at INFO (`REPOSITORY_PACKAGE_UPLOADED`) on success and WARNING (`REPOSITORY_UPLOAD_CONFLICT`) on a rejected duplicate, matching the PRS's explicit "Repository Uploads" audit-logged-events entry
- Deployment creation (DEPLOY-001) is audit-logged at INFO (`DEPLOYMENT_CREATED`) on success only, matching the PRS's explicit "Deployment Creation" audit-logged-events entry; rejected requests (unknown/inactive package, unknown client, active-deployment conflict) are not audit-logged, since nothing is committed on those paths (mirroring the "commit-time-only" logging pattern already used by `REPOSITORY_PACKAGE_UPLOADED`)
- Unexpected errors logged globally by `backend/core/exceptions.py`

### Error Handling
- Every endpoint validates inputs, handles exceptions, returns consistent responses
- `AppException` (and `AuthenticationError` subclass) is standard base for all business-rule errors
- `ClientNotFoundError` (INV-002, `backend/api/routers/updates.py`) follows this same `AppException` pattern for its 404 case
- `RepositoryPackageValidationError` (400) and `RepositoryPackageConflictError` (409) (REP-001, `backend/services/repository_service.py`) follow the same pattern for their respective cases; `RepositoryPackageMetadataError` (400, `backend/api/routers/repository.py`) adapts a Pydantic `ValidationError` raised while manually constructing `RepositoryPackageUploadMetadata` from `Form(...)` fields into the same standard envelope
- `DeploymentPackageUnavailableError` (400), `DeploymentClientNotFoundError` (404), and `DeploymentClientActiveError` (409) (DEPLOY-001, `backend/services/deployment_service.py`) follow the same `AppException` pattern for their respective cases; `RepositoryPackageNotFoundError` (404, REP-002) is reused unmodified for the "unknown package" case rather than being re-implemented
- Global handlers convert Pydantic validation errors and unhandled exceptions to standard `{"success", "message", "error"}` envelope

### Security Standards
- Passwords: bcrypt via Passlib, never plaintext
- API Keys: `secrets.token_urlsafe`, unique, SHA-256 hash-at-rest
- Session Cookies: HttpOnly, `Secure` configurable, CSRF-protected (double-submit)
- Repository Packages: SHA-256 computed and stored at upload time (REP-001); download-time re-verification by the Client Agent remains DEPLOY-003 scope
- Repository Packages: server-generated, sanitized storage filenames only — the client-supplied filename is never used for storage or path construction; uploads are size-bounded (`MAX_INSTALLER_UPLOAD_SIZE_MB`) and extension-validated against the declared installer type
- Deployments: package must be `Approved` at creation time (DEPLOY-001, enforced via `DeploymentService`/`RepositoryService.get_package`); installer-level integrity verification before *execution* remains DEPLOY-003 scope (not yet implemented)
- Version comparison endpoint: read-only, admin-session-protected, no CSRF required (NFR-028 scopes CSRF to state-changing requests)
- Repository upload endpoint: state-changing, admin-session **and** CSRF protected (NFR-028)
- Deployment creation endpoint: state-changing, admin-session **and** CSRF protected (NFR-028), same pattern as repository upload/deactivation

### Database Standards
- SQLAlchemy ORM only — no raw SQL
- Maintain normalized relationships
- Use transactions where appropriate
- Avoid duplicated data
- UUID primary keys throughout

### API Standards
- RESTful design
- All responses use Pydantic Schemas
- Standard envelope: `{"success", "message", "data"}` or `{"success", "message", "error"}`

### Important Files Likely to Be Modified
| Module | Purpose |
|--------|---------|
| `backend/api/routers/agent.py` | Add new agent-facing endpoints (protected by `require_client_api_key`); DEPLOY-002 added `GET /deployments/poll` here |
| `backend/api/routers/deployments.py` | Admin-facing only (`POST /api/admin/deployments`, DEPLOY-001); a future DASH-002/DEPLOY-* ticket may add admin-facing listing/cancellation here — DEPLOY-002 did not modify this file, since polling is client-facing and lives on `agent.py` instead |
| `backend/repositories/deployment_repository.py` | DEPLOY-003/004 will extend this further with download/status-update queries; DEPLOY-002 already added the client-scoped pending-target lookup |
| `backend/services/deployment_service.py` | DEPLOY-003/004 will extend this further with download/checksum/status-reporting business logic; DEPLOY-002 already added `poll_pending_deployment` |
| `backend/schemas/deployment.py` | DEPLOY-003/004 will likely add request/response schemas for status reporting; DEPLOY-002 already added the polling response DTOs |
| `agent/` (Client Agent package) | DEPLOY-003 will add the real download/execution logic that calls `GET /api/agent/deployments/poll` (DEPLOY-002) from a live Windows agent |
| `backend/services/` | Add business logic for new features |
| `backend/repositories/` | Extend with new data access methods |
| `backend/models/` | Add new models only when necessary |
| `backend/schemas/` | Add request/response schemas |

---

## Next Recommended Work

### DEPLOY-003 — Installer Download & Execution

**Purpose:** Allow a Client Agent that has retrieved a pending deployment via `GET /api/agent/deployments/poll` (DEPLOY-002) to download the associated installer, verify its SHA-256 checksum against the value already returned by the poll response, and execute it silently (FR-010 Installer Download, FR-011 Silent Software Installation).

**Expected Deliverables (per Backlog):**

- Installer download endpoint/mechanism (agent-facing, protected by the existing `require_client_api_key`), scoped to the authenticated client's own deployment target — same client-isolation requirement as DEPLOY-002
- Checksum validation — the Client Agent compares the downloaded file's computed SHA-256 against the `checksum` value already surfaced by DEPLOY-002's `DeploymentPollPackageDetail.checksum`
- Silent installation execution using `silent_command` (already surfaced by DEPLOY-002), invoked as a direct process execution (not through a shell) per FR-011
- Exit-code capture and retry logic per FR-010/FR-011's Error Conditions

**Notes for Implementer:**

- Reuse `DeploymentRepository`/`DeploymentService` (DEPLOY-001/002) rather than creating parallel modules; DEPLOY-002's `poll_pending_deployment` and `get_pending_target_for_client` should remain unmodified unless a defect is discovered.
- DEPLOY-002 deliberately left `DeploymentTarget.status` at `Pending` after a poll — DEPLOY-003/004 is where `Pending → Downloading → Installing → Completed/Failed` transitions and their reporting should be implemented (FR-012).
- Reuse the existing `require_client_api_key`/`CurrentClient` dependency (AUTH-002) for authentication — do not introduce a new client authentication mechanism.
- Client isolation must be preserved: a client must never be able to download or act on another client's deployment target.

---

## AI Handoff Summary

### Current Implementation Status

| Area | Status |
|------|--------|
| Backend Foundation | ✅ Production Ready |
| Database Layer | ✅ Production Ready |
| Admin Authentication | ✅ Production Ready (session-based) |
| Client Authentication | ✅ Production Ready (API key) |
| Client Registration | ✅ Production Ready (with provisioning keys) |
| Heartbeat Service | ✅ Production Ready |
| Inventory Collection | ✅ Production Ready |
| Version Comparison | ✅ Production Ready |
| Repository Management (Upload) | ✅ Production Ready (REP-001) |
| Repository Dashboard (Listing/Search/Details/Removal) | ✅ Production Ready (REP-002) |
| Deployment Creation | ✅ Production Ready (DEPLOY-001) |
| Deployment Polling | ✅ Production Ready (DEPLOY-002 — client-scoped, read-only, no status transition) |
| Client Agent | ⚠ Agent scaffolding implemented (automatic registry scanning and DEPLOY-002 polling consumption pending deployment) |
| Deployment Execution (download/install/report) | ❌ Not yet implemented (DEPLOY-003 — current next ticket) |
| Frontend Dashboard | ❌ Not yet implemented (all dashboard functionality is API-only so far) |

### Current Architecture (Summary)

- FastAPI backend with SQLAlchemy + SQLite
- Repository → Service → Router separation
- Admin: Session cookies + CSRF protection
- Client: Bearer API key (SHA-256 hash-at-rest)
- Router-level protection for authenticated `/api/agent/*` endpoints
- Software inventory snapshot synchronization implemented
- Version comparison against the approved repository catalog implemented, computed on demand (not persisted)
- Repository package upload implemented: SHA-256 checksum computed at upload time, server-generated storage filenames, duplicate-entry rejection
- Repository package dashboard implemented: administrator-facing list/search (by name/version, optional status filter), package detail retrieval, and deactivation (logical removal via `approval_status = INACTIVE`, not a physical delete)
- Deployment creation implemented: administrator creates a batch (`Deployment`) + one `DeploymentTarget` per targeted client (initial status `Pending`), validated against package approval status, client existence, and the "one active deployment per client" business rule; fully atomic (all-or-nothing) and audit-logged
- Deployment polling implemented: the authenticated Client Agent retrieves its own `Pending` deployment target (if any) via `GET /api/agent/deployments/poll`, strictly scoped to its own identity, with no status transition and no audit log entry (pure read)
- Client Agent scaffolding prepared for automated Windows Registry inventory collection

### Completed Modules (Do Not Redesign)

- CORE-001: Backend Foundation
- CORE-002: Database Layer
- AUTH-001: Administrator Authentication
- AUTH-002: Client Authentication
- CLIENT-001: Client Registration
- CLIENT-002: Heartbeat Service
- INV-001: Inventory Collection
- INV-002: Version Comparison
- REP-001: Repository Management (Upload)
- REP-002: Repository Dashboard (Listing/Search/Details/Deactivation)
- DEPLOY-001: Deployment Creation (batch + per-client target persistence)
- DEPLOY-002: Agent Polling (client-scoped `GET /api/agent/deployments/poll`, read-only, no status transition)

### Current Blockers

- No automated test framework (manual verification only)
- No scheduler/background task infrastructure
- No administrator dashboard **UI** for viewing uploaded inventory, repository packages, deployments, or comparison results (all such functionality is API-only so far — REP-002 added the repository-package API surface, DEPLOY-001 added the deployment-creation API surface, and DEPLOY-002 added the deployment-polling API surface, but no Jinja2 templates are wired yet)
- No deployment *execution* module (DEPLOY-003/DEPLOY-004 remain unimplemented) — every deployment target retrieved via DEPLOY-002 polling stays `Pending` indefinitely until those tickets land
- No admin-facing "list clients", "list inventory", or "list/history deployments" endpoints yet (planned for future dashboard-facing tickets)

### Immediate Next Task

**DEPLOY-003 — Installer Download & Execution**

- Allow a Client Agent that has retrieved a pending deployment via `GET /api/agent/deployments/poll` (DEPLOY-002, complete) to download the associated installer, verify its SHA-256 checksum against the value already returned by the poll response, and execute it silently (FR-010 Installer Download, FR-011 Silent Software Installation)
- Reuse the existing `require_client_api_key`/`CurrentClient` dependency (AUTH-002) — do not introduce a new client authentication mechanism
- Extend `DeploymentRepository`/`DeploymentService` (DEPLOY-001/002) rather than duplicating query/business logic
- Scope every operation strictly to the authenticated client's own deployment target — a client must never be able to act on another client's deployment
- Keep `DeploymentService.create_deployment` (DEPLOY-001) and `poll_pending_deployment` (DEPLOY-002) unmodified unless a defect is discovered
- Status reporting (`Downloading`/`Installing`/`Completed`/`Failed` transitions) belongs to DEPLOY-004, per DEPLOY-002's documented design decision not to transition status on poll

### Files Likely to Be Modified (DEPLOY-003)

| File | Reason |
|------|--------|
| `backend/api/routers/agent.py` | Add the installer-download endpoint (protected by `require_client_api_key`, same router as DEPLOY-002's poll endpoint) |
| `backend/repositories/deployment_repository.py` | Extend with any download-specific query needed (e.g. re-resolving the client's own target by id) |
| `backend/services/deployment_service.py` | Extend with download/checksum-verification business logic, or add a dedicated service if the ticket scope warrants it |
| `backend/schemas/deployment.py` | Extend with any new request/response schema needed for the download step |
| `backend/api/dependencies.py` | Add any new DI provider needed, following the existing per-service DI factory pattern |
| `agent/deployment/`, `agent/installer/` | Client-side download/execution logic consuming DEPLOY-002's poll endpoint |

### Key Decision for REP-002 (Completed)

Repository package listing/removal was implemented using the existing Repository → Service → Router architecture, extending `RepositoryPackageRepository` and `RepositoryService` (both introduced/extended by REP-001) rather than creating competing modules for the same table. `RepositoryService.upload_package` and `VersionComparisonService` were treated as stable, already-correct consumers/producers of `RepositoryPackageRepository` and were not modified — both the upload endpoint and the version-comparison endpoint continue to behave exactly as before REP-002.

### Key Decision for DEPLOY-001 (Completed)

Dedicated `Deployment`/`DeploymentTarget` repository (`DeploymentRepository`) and service (`DeploymentService`) modules were introduced rather than extending `RepositoryPackageRepository`/`RepositoryService` — deployment jobs are a distinct entity from repository packages (PRS §7.5.4/§7.5.5), and mixing deployment-creation logic into the repository-package service would have blurred the Single Responsibility boundary the project has maintained through every ticket so far (SAD §10.14 Service Design Principles). `DeploymentService` instead *composes* a `RepositoryService` instance to reuse `get_package` for package validation, and reuses the existing `ClientRepository` for client validation — reuse through composition, not inheritance or duplication. The "one active deployment per client" business rule (Business Rule 9, PRS §2.7) was deliberately kept out of the model layer and implemented entirely in `DeploymentService`, per the design note already present on `DeploymentTarget` since CORE-002.

### Key Decision for DEPLOY-002 (Completed)

Client-facing polling reused `DeploymentRepository`/`DeploymentService` (extended, not replaced) and the existing `CurrentClient` authentication dependency, added as one new endpoint on the existing `agent.py` router rather than a new router or new `main.py` registration. The ambiguity flagged in CURRENT_STATE v1.1 — whether `DeploymentTarget.status` should transition on poll (e.g. `Pending` → `Downloading`) or only later at actual download-start (DEPLOY-003) — was resolved in favor of **no transition on poll**: FR-009's functional behavior (steps 1–6) describes only searching for and returning a pending deployment, while FR-012 explicitly ties the `Pending → Downloading` transition to the Client Agent *reporting* the start of its installer download (FR-010), which is DEPLOY-003/DEPLOY-004 scope. A new, `Pending`-only repository query (`get_pending_target_for_client`) was added rather than reusing DEPLOY-001's broader `ACTIVE_DEPLOYMENT_STATUSES` query, keeping the two concerns (Business-Rule-9 enforcement at creation time vs. "what does this client still need to retrieve") cleanly separated. Client isolation is enforced at the SQL `WHERE` clause using only the authenticated `CurrentClient.id` — never a client id from request input.

### Key Decision for DEPLOY-003 (Upcoming)

Installer download should reuse `DeploymentRepository`/`DeploymentService` and the same `CurrentClient`-derived client-isolation pattern DEPLOY-002 established (scope every query/action to the authenticated client's own target — never accept a client id from request input as an authorization boundary). The checksum value the Client Agent will verify against is already available from DEPLOY-002's poll response (`DeploymentPollPackageDetail.checksum`), so DEPLOY-003 does not need to re-fetch or duplicate that lookup — it can be treated as already resolved by the time a client requests a download, provided the download endpoint re-validates the target still belongs to the requesting client. Whether `DeploymentTarget.status` transitions to `Downloading` at the start of the download (FR-010/FR-012) or only when the client explicitly reports it (a later status-reporting call) should be resolved against FR-012's literal wording before implementation.

---

*End of CURRENT_STATE.md*
