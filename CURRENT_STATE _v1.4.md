# CURRENT_STATE.md

**Version:** 1.4
**Last Updated:** August 11, 2026

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
| Client Agent | Inventory collection scaffolding implemented (server-side inventory upload complete); deployment polling, installer download, checksum verification, silent installation, and deployment **status reporting** implemented client-side (DEPLOY-003 + DEPLOY-004 — not yet wired into a scheduler) |
| Authentication | Admin: Session + CSRF cookie; Client: Bearer API Key (SHA-256) |
| Deployment | Local Package Repository (upload + administrator dashboard listing/search/details/deactivation implemented — REP-001, REP-002); deployment **creation** implemented (DEPLOY-001 — batch + per-client target persistence, initial `Pending` status); deployment **polling** implemented (DEPLOY-002 — client-scoped `GET /api/agent/deployments/poll`, read-only, no status transition); installer **download and execution** implemented (DEPLOY-003 — client-scoped `GET /api/agent/deployments/{target_id}/download`, SHA-256 verification, direct-process silent installation); deployment **status reporting and cancellation** implemented (DEPLOY-004 — client-scoped `POST /api/agent/deployments/{target_id}/status` drives `Pending → Downloading → Installing → Completed/Failed`; admin-scoped `POST /api/admin/deployments/{target_id}/cancel` cancels a still-`Pending` target — implementation complete, testing pending) |
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
│   │   │                          # deployment poll — DEPLOY-002: GET /api/agent/deployments/poll;
│   │   │                          # installer download — DEPLOY-003: GET /api/agent/deployments/{target_id}/download;
│   │   │                          # status reporting — DEPLOY-004: POST /api/agent/deployments/{target_id}/status)
│   │   ├── registration.py        # POST /api/register (CLIENT-001)
│   │   ├── updates.py             # Admin version-comparison endpoint (INV-002)
│   │   ├── repository.py          # Admin installer upload (REP-001) + list/detail/deactivate (REP-002)
│   │   └── deployments.py         # Admin deployment creation endpoint (DEPLOY-001); extended (DEPLOY-004):
│   │                              # POST /api/admin/deployments/{target_id}/cancel
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
│   ├── enums.py                   # Shared enums, incl. UpdateStatus (INV-002), DeploymentStatus (reused unmodified by DEPLOY-004)
│   ├── administrator.py
│   ├── administrator_session.py
│   ├── client.py
│   ├── client_provisioning_key.py
│   ├── software_inventory.py
│   ├── repository_package.py      # Reused unmodified by REP-001
│   ├── deployment.py
│   ├── deployment_target.py       # Reused unmodified by DEPLOY-004 — status/completion_time/exit_code/error_message
│   │                               # columns already existed since CORE-002; no migration required
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
│                                           # Extended (DEPLOY-003): get_target_for_client (client-scoped download lookup)
│                                           # Extended (DEPLOY-004): get_target_by_id (admin-scoped, unscoped lookup by id),
│                                           # update_status (persists status/completion_time/exit_code/error_message)
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
│                                           # Extended (DEPLOY-003): prepare_installer_download (FR-010, client-scoped, audit-logged)
│                                           # Extended (DEPLOY-004): STATUS_TRANSITIONS / TERMINAL_DEPLOYMENT_STATUSES,
│                                           # report_status (FR-012, client-scoped, transition-matrix-enforced, idempotent
│                                           # same-status no-op, audit-logs terminal outcomes only), cancel_deployment_target
│                                           # (FR-021, admin-scoped, Pending-only)
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
                                            # Extended (DEPLOY-004): DeploymentStatusReportRequest,
                                            # DeploymentTargetStatusResponse, DeploymentCancelResponse

agent/                                     # Client Agent (initial implementation)
├── communication/                         # Server communication helpers
│   ├── inventory_client.py                # INV-001: authenticated inventory upload
│   └── deployment_client.py               # NEW (DEPLOY-003): poll_deployment (FR-009), download_installer (FR-010)
│                                           # Extended (DEPLOY-004): report_status (FR-012)
├── installer/                             # NEW (DEPLOY-003): checksum verification + silent execution (FR-011)
│   ├── checksum.py                        # compute_sha256 / verify_checksum
│   └── executor.py                        # build_command (safe tokenization) / execute_installer (shell=False)
├── deployment/                            # NEW (DEPLOY-003): orchestration (poll -> download -> verify -> execute)
│   └── manager.py                         # run_deployment_cycle; python -m agent.deployment.manager entry point
│                                           # Extended (DEPLOY-004): STATUS_DOWNLOADING/STATUS_INSTALLING constants,
│                                           # _report_status_with_retries, _report_final_status; report calls wired in
│                                           # at the Downloading/Installing transitions and all terminal return points
├── scanner/                               # Windows Registry inventory scanner
├── config/
│   └── settings.py                        # Extended (DEPLOY-003): download/retry/execution timeout config
│                                           # Extended (DEPLOY-004): status_report_max_retries,
│                                           # status_report_retry_delay_seconds
└── main.py                                # Agent entry point (inventory cycle; unmodified by DEPLOY-003/DEPLOY-004)

repository/                                # Local package repository (REP-001 — now receives uploaded installers)

scripts/
├── create_admin.py                        # Production admin provisioning
└── dev_seed_client.py                     # Development/testing client seed

docs/

tests/                                     # Empty skeleton (no pytest configured)
```

---

## Overall Progress

| Metric                    | Status                                          |
| ------------------------- | ------------------------------------------------ |
| **Current Version**       | v1.4                                            |
| **Development Stage**     | DEPLOY-004 — Deployment Status Reporting (implementation complete; testing pending in a separate validation phase) |
| **Latest Stable Release** | DEPLOY-003 — Installer Download & Execution (DEPLOY-004 implementation complete, not yet validated) |
| **Repository Status**     | Active Development                              |
| **Architecture Status**   | Stable                                          |
| **Regression Status**     | No known regressions from completed tickets through DEPLOY-003; DEPLOY-003 and DEPLOY-004 both remain pending their own regression/validation passes (separate validation phase) |

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
| v1.2    | DEPLOY-002 — Agent Polling                             |
| v1.3    | DEPLOY-003 — Installer Download & Execution (implementation complete; testing pending) |
| v1.4    | DEPLOY-004 — Deployment Status Reporting (implementation complete; testing pending) |

### Current Ticket

**DEPLOY-004 — Deployment Status Reporting** ⚠ Implementation Complete — Testing Pending

The client-scoped status-reporting endpoint, the admin-scoped cancellation endpoint, and the Client Agent's report-status integration (wired into `agent.deployment.manager.run_deployment_cycle` at each real stage transition) have been implemented per the ticket's objective (FR-012 Deployment Status Reporting, FR-021 Deployment Cancellation) and scope. Per this project's workflow rules, testing and validation are treated as a separate phase and have not yet been performed against this ticket. Neither DEPLOY-003 nor DEPLOY-004 should be considered "Production Ready" until their validation phases complete.

### Next Ticket

**DEPLOY-003 / DEPLOY-004 Validation Phase, then DASH-001 — Dashboard Home**

Before any further deployment-lifecycle ticket work begins, DEPLOY-003 and DEPLOY-004 both need their deferred `TestClient`-based endpoint tests, a scripted end-to-end run of `agent.deployment.manager.run_deployment_cycle` (including status-report call sites), and a full regression pass. Once validated, the deployment lifecycle (creation → polling → download/execution → status reporting/cancellation) is functionally complete end-to-end, and the next logical ticket is **DASH-001 — Dashboard Home**, followed by **DASH-002 — Deployment Monitoring** (which depends on DEPLOY-004).

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

**Important Note:** No database schema or migration changes were required — `Deployment` and `DeploymentTarget` (defined by CORE-002) already had every column this ticket needed (including the `uq_deployment_target_deployment_client` unique constraint and `ix_deployment_targets_client_status` index). Deployment *execution* — installer download/checksum verification and silent installation (DEPLOY-003) — and status reporting (DEPLOY-004), and deployment cancellation, are now all implemented (see below); agent polling was implemented by DEPLOY-002, installer download/execution by DEPLOY-003, and status reporting/cancellation by DEPLOY-004.

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

**Design Decisions (Documented):**

- **No status transition on poll (`Pending` stays `Pending`):** FR-009's own functional behavior (steps 1–6) describes searching for and returning a pending deployment; it does not describe a status change. FR-012's Deployment Status Values table ties the `Pending → Downloading` transition to the Client Agent *beginning the installer download* (FR-010) and *reporting* that transition (FR-012 step 1) — this ambiguity has since been resolved by DEPLOY-004, which implements exactly that reporting step.
- **Client Isolation enforced at the query layer, not just the handler.**
- **`Pending`-only match, not the full active-status set.**
- **No audit log entry for a poll** — routine, frequent, non-security-relevant traffic.
- **`200 OK` with `has_deployment: false`, not `404`, when nothing is pending.**
- **Endpoint placed on the existing `agent.py` router, at `/api/agent/deployments/poll`** — consistent with `/api/agent/heartbeat` and `/api/agent/inventory/upload`.

**Regression Status:** Passed (re-verified again during DEPLOY-003 and unaffected by DEPLOY-004; `DeploymentService.create_deployment`/`poll_pending_deployment` were not modified by either ticket).

**Important Note:** DEPLOY-002 is polling-only, as scoped. Every `DeploymentTarget` a Client Agent retrieves via this endpoint remains `Pending` until the client downloads/executes it (DEPLOY-003) and reports the resulting transition (DEPLOY-004) — both now implemented (DEPLOY-004 pending its own validation phase).

---

### DEPLOY-003 — Installer Download & Execution

| Status | ⚠ Implementation Complete — Testing Pending (separate validation phase) |
|--------|--------|

**Objective:** Allow a Client Agent that has retrieved a pending deployment via `GET /api/agent/deployments/poll` (DEPLOY-002) to download the associated installer, verify its SHA-256 checksum against the value returned by the poll response, and execute it silently (FR-010 Installer Download, FR-011 Silent Software Installation), building on DEPLOY-002's client-scoped polling endpoint.

**Server-Side Features Implemented:**

- `DeploymentRepository` (introduced by DEPLOY-001, extended by DEPLOY-002) extended with:
  - `get_target_for_client(db, *, target_id, client_id)` — a strictly client-scoped, read-only lookup for a single `DeploymentTarget` by primary key, filtering on `client_id` inside the SQL `WHERE` clause itself so a client can never resolve — and therefore never download the installer for — another client's deployment target, even by guessing/enumerating target ids. Unlike DEPLOY-002's `get_pending_target_for_client`, this lookup is not restricted to `Pending` status (a target already `Downloading` — e.g. a client retrying an interrupted download — must still resolve).
- `DeploymentService` (introduced by DEPLOY-001, extended by DEPLOY-002) extended with:
  - `DOWNLOADABLE_STATUSES` constant (`Pending`, `Downloading`) — the per-client target states from which an installer download may be requested.
  - New exceptions: `DeploymentTargetNotFoundError` (404), `DeploymentTargetNotDownloadableError` (409), `DeploymentInstallerUnavailableError` (500).
  - `prepare_installer_download(db, *, client, target_id, repository_dir)` — resolves and authorizes the download request strictly via `client.id`, validates the target's status, verifies the installer file exists on disk, records an audit log entry for every outcome, and returns the resolved `DeploymentTarget` and the absolute installer `Path`.
- New Client-Agent-facing, read-only endpoint: `GET /api/agent/deployments/{target_id}/download`, added to the existing `backend/api/routers/agent.py` router. Streams the file back via `FileResponse` (`media_type="application/octet-stream"`).

**Client-Side Features Implemented (new `agent/` modules):**

- `agent/communication/deployment_client.py` — `poll_deployment(...)`, `download_installer(...)`, `DeploymentCommunicationError`.
- `agent/installer/checksum.py` — `compute_sha256`, `verify_checksum`.
- `agent/installer/executor.py` — `build_command`, `execute_installer` (`subprocess.run(..., shell=False)`, never a shell string).
- `agent/deployment/manager.py` — `run_deployment_cycle()` orchestrates poll → download (with retry) → checksum-verify → execute → status reporting; retries persisted status reports at the start of each communication cycle.
- `agent/deployment/status_report_store.py` — local atomic JSON persistence for undelivered DEPLOY-004 status reports.
- `agent/config/settings.py` (extended) — download/retry/execution-timeout/status-report settings.

**Design Decisions (Documented):**

- Client isolation enforced identically to DEPLOY-002; "not found" and "belongs to another client" are indistinguishable to the requester.
- No status transition performed by DEPLOY-003 itself, server- or client-side — deferred to DEPLOY-004, which has since implemented it.
- Checksum mismatch is never retried (definitive integrity/security failure); only the download step (network/communication failures) is retried.
- Direct process execution, never a shell.
- Audit logging added for installer downloads (PRS FR-016 explicitly names "Installer Downloads"), unlike DEPLOY-002's poll.
- Endpoint added to the existing `agent.py` router, at `/api/agent/deployments/{target_id}/download`.
- `DeploymentService.create_deployment` (DEPLOY-001) and `poll_pending_deployment` (DEPLOY-002) were not modified.

**Verification Status:** **Not yet performed.** No `TestClient`-based endpoint tests, no manual/scripted end-to-end verification, and no live Windows-side execution check have been run yet for DEPLOY-003 — only `ast.parse` syntax validation was possible in the implementation environment (network access disabled, dependencies not installable). Scheduled for the same separate validation phase now also covering DEPLOY-004 (see "Next Ticket" above).

**Important Note:** DEPLOY-003 implements installer download and silent execution only (FR-010, FR-011). Deployment status reporting (FR-012), deployment history (FR-013), and deployment cancellation (FR-021) were out of DEPLOY-003's scope and have since been implemented by **DEPLOY-004** (see below — also pending its own validation). The Client Agent's `agent.deployment.manager.run_deployment_cycle` remains a standalone, manually-invoked entry point (`python -m agent.deployment.manager`); it has not been wired into a Scheduler Module or into `agent/main.py`'s existing inventory cycle.

---

### DEPLOY-004 — Deployment Status Reporting

| Status | ⚠ Implementation Complete — Testing Pending (separate validation phase) |
|--------|--------|

**Objective:** Complete the deployment lifecycle by having the Client Agent report the `DeploymentExecutionResult` DEPLOY-003 already produces back to the server (FR-012 Deployment Status Reporting: `Downloading`/`Installing` transitions plus the final `Completed`/`Failed` outcome with exit code and error message), and by giving the administrator a way to cancel a still-`Pending` deployment target before it is retrieved (FR-021 Deployment Cancellation), building on DEPLOY-001's creation, DEPLOY-002's polling, and DEPLOY-003's download/execution.

**Baseline Findings (confirmed by inspection before implementation):**

- `DeploymentTarget` (CORE-002) already carried every column this ticket needed — `status`, `completion_time`, `exit_code`, `error_message` — so **no migration was required**.
- `DeploymentRepository.get_target_for_client` (DEPLOY-003) was already client-scoped and directly reusable for status-report authorization.
- `CSRFProtection`/`CurrentAdministrator` (AUTH-001) already existed and were directly reusable for the new admin-facing cancellation endpoint.

**Server-Side Features Implemented:**

- `DeploymentRepository` (introduced by DEPLOY-001, extended by DEPLOY-002/DEPLOY-003) extended with:
  - `get_target_by_id(db, target_id)` — an unscoped lookup by primary key, used only by the admin-facing cancellation path (an administrator is authorized to act on any client's target, unlike a Client Agent).
  - `update_status(db, *, target, status, completion_time=None, exit_code=None, error_message=None)` — persists a `DeploymentTarget`'s new status and, for terminal outcomes, its completion time/exit code/error message.
- `DeploymentService` (introduced by DEPLOY-001, extended by DEPLOY-002/DEPLOY-003) extended with:
  - `STATUS_TRANSITIONS` — an explicit transition matrix (`Pending → Downloading`, `Downloading → Installing`, `Installing → {Completed, Failed}`, `Downloading → Failed`, etc.) and `TERMINAL_DEPLOYMENT_STATUSES` (`Completed`, `Failed`, `Cancelled`), reused rather than re-derived from `ACTIVE_DEPLOYMENT_STATUSES`/`DOWNLOADABLE_STATUSES`.
  - New exceptions: `DeploymentStatusTransitionError` (409 — the reported status is not a legal transition from the target's current status), `DeploymentStatusReportValidationError` (400 — e.g. a terminal status reported without a required field), `DeploymentCancellationTargetNotFoundError` (404), `DeploymentCancellationNotAllowedError` (409 — target is not currently `Pending`).
  - `report_status(db, *, client, target_id, status, exit_code=None, error_message=None)` — client-scoped (via `client.id`, never a request-supplied client id), reuses `get_target_for_client` for authorization, enforces `STATUS_TRANSITIONS` (rejecting illegal transitions with `DeploymentStatusTransitionError`), treats a repeated report of the *same* status as an idempotent no-op (does not error, does not re-log), computes `completion_time` server-side for terminal outcomes rather than trusting a client-supplied timestamp, persists via `DeploymentRepository.update_status`, and audit-logs **only terminal outcomes** (`DEPLOYMENT_COMPLETED` / `DEPLOYMENT_FAILED`) — intermediate `Downloading`/`Installing` transitions are not individually audit-logged, mirroring DEPLOY-002's polling rationale (frequent, routine, not itself security-relevant).
  - `cancel_deployment_target(db, *, admin_id, target_id)` — admin-scoped, resolves the target via the new unscoped `get_target_by_id`, allows cancellation **only** from `Pending` (per FR-021: once a client has retrieved/started a job, cancellation through this function is rejected with `DeploymentCancellationNotAllowedError`), transitions the target to `Cancelled`, and audit-logs the cancellation.
- `backend/schemas/deployment.py` extended with:
  - `DeploymentStatusReportRequest` — `status` (one of `Downloading`/`Installing`/`Completed`/`Failed`), optional `exit_code`, optional `error_message`.
  - `DeploymentTargetStatusResponse` — the target's id, current status, completion time, exit code, and error message after the report is applied.
  - `DeploymentCancelResponse` — the cancelled target's id and resulting status.
- New Client-Agent-facing, state-changing endpoint: `POST /api/agent/deployments/{target_id}/status`, added to the existing `backend/api/routers/agent.py` router (same router-wide `require_client_api_key` protection as `/poll` and `/download`). Delegates entirely to `DeploymentService.report_status`; router stays thin.
- New administrator-facing, state-changing endpoint: `POST /api/admin/deployments/{target_id}/cancel`, added to the existing `backend/api/routers/deployments.py` router. Protected by `CurrentAdministrator` **and** `CSRFProtection` (state-changing, NFR-028) — the same pattern as `POST /api/admin/deployments` and the repository-package/deactivation endpoints.

**Client-Side Features Implemented:**

- `agent/communication/deployment_client.py` extended with `report_status(target_id, status, *, exit_code=None, error_message=None, server_url, api_key, timeout_seconds)` — calls the new status endpoint, following the same Bearer-auth conventions as `poll_deployment`/`download_installer`.
- `agent/config/settings.py` extended with `status_report_max_retries` and `status_report_retry_delay_seconds`, mirroring the download-retry configuration pattern already established by DEPLOY-003.
- `agent/deployment/manager.py` extended with:
  - `STATUS_DOWNLOADING`/`STATUS_INSTALLING` string constants (matching `backend.models.enums.DeploymentStatus`'s vocabulary exactly, the same alignment DEPLOY-003 already established for `"Completed"`/`"Failed"`).
  - `_send_status_report_with_retries(...)` — the bounded immediate-retry primitive for one status report.
  - `_report_status_with_retries(...)` — sends a new report and persists it to the local queue when all immediate attempts fail.
  - `_flush_pending_status_reports(...)` — retries persisted reports at the start of each communication cycle, preserving per-target ordering.
  - `_report_final_status(...)` — reports the terminal `Completed`/`Failed` outcome with `exit_code`/`error_message`.
  - Report calls wired into `_execute_pending_deployment` at the real stage transitions: **before** the download begins (`Downloading`), **after** checksum verification and **before** `execute_installer` is invoked (`Installing`), and at **all terminal return points** (`Completed`/`Failed`, including checksum-mismatch and installer-timeout/launch-failure paths). Every report call's own success/failure is independent of and never alters the `DeploymentExecutionResult` ultimately returned by `run_deployment_cycle`.
- `agent/deployment/status_report_store.py` added — atomic JSON-backed persistence for undelivered status reports, with duplicate suppression and ordered acknowledgement. The runtime queue file itself is Git-ignored.

**Design Decisions (Documented):**

- **Client isolation enforced identically to DEPLOY-002/DEPLOY-003** for `report_status`: every lookup is scoped to `CurrentClient.id`; a client can never report status for, or learn about, another client's deployment target.
- **Cancellation is intentionally administrator-only and unscoped-by-client at the repository layer**, but the *service*-layer business rule (`Pending`-only) is what actually enforces FR-021's race-condition handling — once a client has retrieved a job (moved it out of `Pending`), the administrator's cancellation request is rejected with a `409`, not silently ignored or allowed to race the client.
- **Explicit transition matrix, not a general "any non-terminal → any status" rule** — `STATUS_TRANSITIONS` codifies exactly which transitions FR-012's Deployment Status Values table permits, rejecting anything else (e.g. `Pending → Completed` skipping `Downloading`/`Installing`, or a report against an already-terminal target) with `DeploymentStatusTransitionError`.
- **Idempotent same-status reporting** — a client re-reporting a status it already successfully reported (e.g. after a retried request whose response was lost) is treated as a no-op success, not an error, avoiding spurious `409`s from the client's own retry logic.
- **Server computes `completion_time`, not the client** — consistent with this project's existing "server is the source of truth for timestamps" pattern (`registration_date`, `last_heartbeat`, `created_at`/`updated_at` are all server-set elsewhere in the codebase).
- **Only terminal outcomes are audit-logged** — `Downloading`/`Installing` reports update the row but do not individually appear in the audit log, the same "routine/frequent, not itself a security-relevant event" rationale DEPLOY-002 already established for polling; `Completed`/`Failed` (and administrator `Cancelled`) are audit-logged, consistent with PRS FR-016's explicit "Deployment Results"/"Deployment creation"-style audit-logged-events entries.
- **`DeploymentExecutionResult`'s status vocabulary was deliberately pre-aligned by DEPLOY-003** specifically so DEPLOY-004 could pass it straight through to the reporting endpoint without a translation step — no adapter/mapping layer was needed between the client-side result and the server-side request schema.
- **No new router, no new model, no migration, no changes to `DeploymentService.create_deployment`/`poll_pending_deployment`/`prepare_installer_download`** — both new endpoints were added to the two existing routers (`agent.py`, `deployments.py`) that already host their respective sibling endpoints, reusing the existing DI providers (`DeploymentServiceDependency`) and dependencies (`CurrentClient`, `CurrentAdministrator`, `CSRFProtection`) without modification.

**Verification Status:** **Implementation correction verified locally; full validation still pending.** Python compilation was verified for the modified Client Agent modules, and the new persistent queue was exercised directly for enqueue, ordered acknowledgement, duplicate suppression, and recovery after a simulated communication failure. No `TestClient`-based endpoint tests, no manual/scripted end-to-end run of the full poll → download → verify → execute → report cycle, and no regression pass against DEPLOY-001/002/003 have been performed yet. The ticket remains in the separate validation phase before it can be considered Production Ready.

**Important Note:** DEPLOY-004 completes the deployment lifecycle end-to-end at the implementation level: a deployment target created by DEPLOY-001, retrieved by DEPLOY-002, downloaded/installed by DEPLOY-003, can now (once validated) actually progress through `Pending → Downloading → Installing → Completed/Failed` in the database, or be cancelled by an administrator while still `Pending`. No admin-facing deployment *listing*/*history* dashboard (DASH-002) exists yet — an administrator can now see the *outcome* of a deployment via direct database inspection or a future listing endpoint, but there is still no dashboard UI. `CURRENT_STATE.md` itself was unavailable during DEPLOY-004's implementation turn and was updated separately afterward (this document).

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
| POST   | `/api/admin/deployments/{target_id}/cancel` | Cancel a still-Pending deployment target (FR-021, DEPLOY-004) | Admin session + CSRF            |
| POST   | `/api/register`                           | Client registration                                       | Provisioning key or existing API key  |
| GET    | `/api/agent/ping`                         | Verify client authentication                              | Client API key                        |
| POST   | `/api/agent/heartbeat`                    | Report client heartbeat                                   | Client API key                        |
| POST   | `/api/agent/inventory/upload`             | Upload complete installed software inventory (FR-005)     | Client API key                        |
| GET    | `/api/agent/deployments/poll`             | Poll for the authenticated client's own pending deployment (FR-009, DEPLOY-002) | Client API key   |
| GET    | `/api/agent/deployments/{target_id}/download` | Download the installer for the authenticated client's own deployment target (FR-010, DEPLOY-003) | Client API key |
| POST   | `/api/agent/deployments/{target_id}/status` | Report a status transition (Downloading/Installing/Completed/Failed) for the authenticated client's own deployment target (FR-012, DEPLOY-004) | Client API key |

### Database Status

- SQLite database initialized with all migrations applied
- Tables: `administrators`, `administrator_sessions`, `clients`, `client_provisioning_keys`, `software_inventories`, `repository_packages`, `deployments`, `deployment_targets`, `audit_logs`, `alembic_version`
- All models use UUID primary keys
- Relationships and constraints defined
- Audit logging integrated for all authentication, registration, repository upload, repository deactivation, deployment creation, deployment status reporting (terminal outcomes only), and deployment cancellation events
- **No schema changes in REP-001** — `repository_packages` already had every column this ticket needed (CORE-002); no migration was added
- **No schema changes in REP-002** — the listing, detail, and deactivation operations use only existing `repository_packages` columns (including `created_at`/`updated_at`, already present via `AuditModel`); no migration was added
- **No schema changes in DEPLOY-001** — `deployments` and `deployment_targets` (CORE-002) already had every column, constraint, and index this ticket needed (`uq_deployment_target_deployment_client`, `ix_deployment_targets_client_status`); no migration was added. `deployments`/`deployment_targets` now contain real rows for the first time since CORE-002 defined them.
- **No schema changes in DEPLOY-002** — polling is a pure read against the existing `deployment_targets`/`deployments`/`repository_packages` tables via a new repository query method only; no new column, table, constraint, or migration was needed. Polling does not write to the database at all (no `INSERT`/`UPDATE` of any kind).
- **No schema changes in DEPLOY-003** — installer download reuses the existing `deployment_targets`/`deployments`/`repository_packages` tables via a new client-scoped repository query method only; no new column, table, constraint, or migration was needed. Unlike polling, a download *does* write to the database — one `audit_logs` row per request (success or rejection) — but writes no new `deployment_targets`/`deployments` row and does not mutate `DeploymentTarget.status`.
- **No schema changes in DEPLOY-004** — `deployment_targets` already carried `status`, `completion_time`, `exit_code`, and `error_message` (CORE-002); status reporting and cancellation both reuse these existing columns via a new `update_status` repository method. This is the **first ticket to actually mutate `DeploymentTarget.status`** after creation — every prior ticket (DEPLOY-002, DEPLOY-003) deliberately left it untouched.

### Authentication Status

**Administrator:**
- Session-based (HttpOnly cookie + separate CSRF cookie)
- Double-submit CSRF protection
- Sliding inactivity expiry
- `Secure` flag configurable (`SESSION_COOKIE_SECURE`, default `False` for HTTP-only prototype — **must set `True` for HTTPS**)
- `POST /api/admin/repository/packages` (REP-001) requires both the session cookie and a valid CSRF token, consistent with every other state-changing administrator endpoint
- `POST /api/admin/repository/packages/{package_id}/deactivate` (REP-002) likewise requires both the session cookie and a valid CSRF token; `GET /api/admin/repository/packages` and `GET /api/admin/repository/packages/{package_id}` (REP-002) are read-only and require only the session cookie, consistent with `GET /api/admin/clients/{client_id}/updates` (INV-002)
- `POST /api/admin/deployments` (DEPLOY-001) likewise requires both the session cookie and a valid CSRF token, since deployment creation is state-changing
- `POST /api/admin/deployments/{target_id}/cancel` (DEPLOY-004) likewise requires both the session cookie and a valid CSRF token, since cancellation is state-changing

**Client:**

- `Authorization: Bearer <api_key>` header
- SHA-256 hash-at-rest validated against `Client.api_key_hash`
- Router-level protection for all `/api/agent/*` routes
- Registration endpoint uses its own credential resolution (existing `Client` OR unclaimed `ClientProvisioningKey`)
- Authenticated inventory uploads use the existing API key authentication without additional authorization requirements
- `GET /api/agent/deployments/poll` (DEPLOY-002) uses the same router-level `require_client_api_key` protection as every other `/api/agent/*` route; the authenticated `CurrentClient.id` is the only identity used to scope the deployment query — no client id is ever accepted from request input
- `GET /api/agent/deployments/{target_id}/download` (DEPLOY-003) likewise uses the same router-level `require_client_api_key` protection; the authenticated `CurrentClient.id` is the sole identity used to scope the target lookup (`DeploymentRepository.get_target_for_client`) — `target_id` alone (a value the requesting client supplies) is never trusted as an authorization boundary by itself
- `POST /api/agent/deployments/{target_id}/status` (DEPLOY-004) likewise uses the same router-level `require_client_api_key` protection; the authenticated `CurrentClient.id` is the sole identity used to authorize the status report (reuses `DeploymentRepository.get_target_for_client`) — a client can never report status for another client's target

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

### Deployment Lifecycle Workflow (Creation + Polling + Download/Execution + Status Reporting/Cancellation — DEPLOY-001 through DEPLOY-004)

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

2b. (New — DEPLOY-004) Administrator may cancel a still-Pending target
    before the client retrieves it
    → POST /api/admin/deployments/{target_id}/cancel
    ├── Allowed only while status is still Pending → 409 otherwise
    ├── DeploymentTarget.status → Cancelled
    └── Cancellation event audit-logged

3. Client Agent polls for its Pending deployment target
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

4. Client Agent downloads, verifies, installs, AND now reports status
   (DEPLOY-003 + DEPLOY-004, run as `python -m agent.deployment.manager`)
   → GET /api/agent/deployments/{target_id}/download
   ├── Scoped strictly to the authenticated client; target must exist,
   │   belong to this client, and be Pending/Downloading, or the
   │   request is rejected (404/409); installer streamed as a binary
   │   FileResponse; server records an INSTALLER_DOWNLOAD audit log entry
   → POST /api/agent/deployments/{target_id}/status  (status: "Downloading")
   │   — reported just before the download begins
   ├── Client Agent verifies the downloaded file's SHA-256 checksum
   │   against the value already returned by step 3's poll response
   │   — a mismatch is a definitive failure, never retried, reported
   │   as status "Failed"
   → POST /api/agent/deployments/{target_id}/status  (status: "Installing")
   │   — reported after checksum verification, before execution
   ├── Client Agent executes the silent_command (also from step 3)
   │   as a direct process (shell=False), captures the exit code
   → POST /api/agent/deployments/{target_id}/status
       (status: "Completed" or "Failed", exit_code, error_message)
       — reported at every terminal outcome
   ├── DeploymentService.report_status enforces the legal transition
   │   matrix, computes completion_time server-side, persists via
   │   DeploymentRepository.update_status, and audit-logs terminal
   │   outcomes only (DEPLOYMENT_COMPLETED / DEPLOYMENT_FAILED)
   └── DeploymentTarget.status in the database now actually reaches
       Completed/Failed — no longer stuck at Pending indefinitely

5. Administrator can (in a future DASH-002 ticket) review the now
   fully up-to-date DeploymentTarget rows — status reporting closes
   the loop FR-012 requires; no dashboard listing UI exists yet
```

## Deployment Lifecycle Status (Creation + Polling + Download/Execution + Status Reporting/Cancellation — All Implemented)

- Local Package Repository: **upload implemented (REP-001)**, **administrator listing/search/details/deactivation implemented (REP-002)**
- Deployment Creation: **implemented (DEPLOY-001)**
- Deployment Polling: **implemented (DEPLOY-002)**
- Deployment *execution*: **implemented (DEPLOY-003 — implementation complete, testing pending)**
- Deployment *status reporting* and *cancellation*: **implemented (DEPLOY-004 — implementation complete, testing pending)** — `POST /api/agent/deployments/{target_id}/status` drives `Pending → Downloading → Installing → Completed/Failed`; `POST /api/admin/deployments/{target_id}/cancel` allows administrator cancellation of a still-`Pending` target (FR-021)
- A deployment-history dashboard (DASH-002) remains **not yet implemented** — the underlying data is now correctly populated by DEPLOY-004, but no admin-facing listing UI/endpoint exists yet
- Silent Installers: executed client-side (DEPLOY-003); outcome now reported to the server (DEPLOY-004)
- SHA-256 Package Validation: upload-time computation (REP-001) → returned via poll (DEPLOY-002) → download-time re-verification (DEPLOY-003) → outcome reported (DEPLOY-004)

### Existing Infrastructure

- **No automated test framework** configured (`pytest` not in `requirements.txt`; `tests/` directory remains an empty skeleton). All verification is currently performed through manual API testing, PowerShell scripts, direct SQLite inspection, and (for INV-002/REP-001/DEPLOY-001/DEPLOY-002) ad hoc scripted verification using FastAPI's `TestClient`. **DEPLOY-003 and DEPLOY-004 have not yet undergone any of this verification** — see their closeout sections' "Verification Status" notes; both are scheduled for the same separate validation phase.
- **No scheduler/background tasks** — client `OFFLINE` status is currently computed at read time rather than maintained by a background service. Version comparison (INV-002) follows this same "computed at read time" pattern. DEPLOY-003/DEPLOY-004's `agent.deployment.manager` is likewise a manually-invoked entry point (`python -m agent.deployment.manager`), not yet wired into any scheduler.
- **Repository package listing/detail/deactivation implemented (REP-002)** — Metadata *editing* (e.g. changing the silent install command after upload) remains unimplemented.
- **No administrator-facing inventory or client listing endpoints** — remain planned for a future dashboard-facing ticket.
- **Deployment creation, polling, download/execution, and status reporting/cancellation all implemented (DEPLOY-001 through DEPLOY-004)** — a created deployment can now progress all the way from `Pending` to `Completed`/`Failed` (or administrator-`Cancelled`) in the database. There is still no administrator-facing "list deployments"/"deployment history" endpoint (DASH-002/a future ticket), so a deployment's outcome can currently only be observed via direct database inspection until that ticket lands.
- **Client Agent scaffolding implemented, deployment execution and status reporting added (DEPLOY-003, DEPLOY-004)** — communication layer, inventory scanner, and application entry point exist from INV-001; DEPLOY-003 added the deployment polling/download communication client, checksum verification, and silent-installer execution modules; DEPLOY-004 added status-reporting calls at each real stage transition. Automated Windows Registry inventory collection and the full deployment execution/reporting workflow will be exercised on a real deployed Windows Agent in future milestones/validation.
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
| **Regression**   | Passed |

---

### REP-001 — Repository Management

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Implement the local software package repository: installer upload, metadata validation, SHA-256 checksum computation/verification, and package storage (FR-006) |
| **Deliverables** | `backend/utils/file_storage.py`, `backend/schemas/repository.py`, `RepositoryPackageRepository.create`/`get_active_conflict`, `RepositoryService`, `POST /api/admin/repository/packages`, `Settings.MAX_INSTALLER_UPLOAD_SIZE_MB` |
| **Regression**   | Passed |

---

### REP-002 — Repository Dashboard

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Provide administrator-facing management of uploaded repository packages: list/browse, search, view package details, and remove (deactivate) obsolete packages (FR-006 dashboard integration, FR-017 Repository Maintenance) |
| **Deliverables** | `RepositoryPackageRepository.list_all`/`get_by_id`/`deactivate`, `RepositoryService.list_packages`/`get_package`/`deactivate_package`, `RepositoryPackageNotFoundError`, `RepositoryPackageListResponse`, `GET /api/admin/repository/packages`, `GET /api/admin/repository/packages/{package_id}`, `POST /api/admin/repository/packages/{package_id}/deactivate` |
| **Regression**   | Passed |

---

### DEPLOY-001 — Deployment Creation

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Allow an administrator to create a deployment batch targeting one or more registered clients with a single approved repository package (FR-008 Deployment Job Creation, FR-009 Deployment Job Retrieval targeting) |
| **Deliverables** | `backend/repositories/deployment_repository.py`, `backend/services/deployment_service.py`, `backend/schemas/deployment.py`, `backend/api/routers/deployments.py`, `POST /api/admin/deployments`, `DeploymentServiceDependency` |
| **Regression**   | Passed |

---

### DEPLOY-002 — Agent Polling

| Status           | ✅ Production Ready                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Allow the authenticated Client Agent to periodically retrieve its own pending deployment job, scoped strictly to its identity (FR-009 Deployment Job Retrieval / Client Polling) |
| **Deliverables** | `DeploymentRepository.get_pending_target_for_client`, `DeploymentService.poll_pending_deployment`, `DeploymentPollPackageDetail`/`DeploymentPollTargetResponse`/`DeploymentPollResponse`, `GET /api/agent/deployments/poll` |
| **Regression**   | Passed |

---

### DEPLOY-003 — Installer Download & Execution

| Status           | ⚠ Implementation Complete — Testing Pending (separate validation phase)                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Allow a Client Agent that has retrieved a pending deployment via polling (DEPLOY-002) to download the associated installer, verify its SHA-256 checksum, and execute it silently (FR-010 Installer Download, FR-011 Silent Software Installation) |
| **Deliverables** | `DeploymentRepository.get_target_for_client`, `DeploymentService.prepare_installer_download` + related exceptions, `GET /api/agent/deployments/{target_id}/download`; client-side `agent/communication/deployment_client.py`, `agent/installer/checksum.py` + `agent/installer/executor.py`, `agent/deployment/manager.py`, `agent/config/settings.py` (extended) |
| **Regression**   | **Not yet performed.** Scheduled for a separate validation phase (now grouped with DEPLOY-004's). |

---

### DEPLOY-004 — Deployment Status Reporting

| Status           | ⚠ Implementation Complete — Testing Pending (separate validation phase)                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**      | Complete the deployment lifecycle by having the Client Agent report deployment progress and outcome back to the server (FR-012 Deployment Status Reporting: `Downloading`/`Installing` transitions and the final `Completed`/`Failed` outcome), and by allowing an administrator to cancel a still-`Pending` deployment target (FR-021 Deployment Cancellation) |
| **Deliverables** | `DeploymentRepository.get_target_by_id`/`update_status` (extended), `DeploymentService.report_status`/`cancel_deployment_target` + `STATUS_TRANSITIONS`/`TERMINAL_DEPLOYMENT_STATUSES` + `DeploymentStatusTransitionError`/`DeploymentStatusReportValidationError`/`DeploymentCancellationTargetNotFoundError`/`DeploymentCancellationNotAllowedError` (extended), `DeploymentStatusReportRequest`/`DeploymentTargetStatusResponse`/`DeploymentCancelResponse` (extended `backend/schemas/deployment.py`), `POST /api/agent/deployments/{target_id}/status` (extended `agent.py`), `POST /api/admin/deployments/{target_id}/cancel` (extended `deployments.py`); client-side `agent/communication/deployment_client.py` (extended: `report_status`), `agent/config/settings.py` (extended: status-report retry settings), `agent/deployment/manager.py` (extended: `STATUS_DOWNLOADING`/`STATUS_INSTALLING`, `_report_status_with_retries`, `_report_final_status`, report calls wired into every real stage transition) |
| **Design Decisions** | Explicit `STATUS_TRANSITIONS` matrix (not a general "any → any" rule); client isolation identical to DEPLOY-002/DEPLOY-003 for reporting; cancellation is admin-only and allowed only from `Pending`; idempotent same-status reporting (no error on duplicate report); server computes `completion_time`; only terminal outcomes audit-logged (intermediate `Downloading`/`Installing` are not); `DeploymentExecutionResult`'s status vocabulary (set by DEPLOY-003) requires no translation to reach the new request schema; no migration, no new router, no changes to `create_deployment`/`poll_pending_deployment`/`prepare_installer_download` |
| **Regression**   | **Not yet performed.** Only `ast.parse` syntax validation across all 8 changed files and a manual cross-check of client/server string-value and field-name consistency have been done. `TestClient`-based endpoint tests, an end-to-end agent-cycle run, and a full regression pass against DEPLOY-001/002/003 remain outstanding, grouped with DEPLOY-003's deferred validation phase. |

---
## Pending Backlog

| Ticket | Purpose | Dependencies | Priority |
|--------|---------|--------------|----------|
| **DEPLOY-003 / DEPLOY-004 Validation** | `TestClient` endpoint tests, end-to-end `agent.deployment.manager` cycle run (including status reporting), and full regression pass | DEPLOY-004 (implementation complete) | Immediate next step |
| **DASH-001** | Dashboard Home | AUTH-001, INV-001, REP-001 | - |
| **DASH-002** | Deployment Monitoring | DEPLOY-004 (implementation complete; validation pending) | - |
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
- Version comparison (INV-002) results are likewise **computed at read time**
- Future tickets needing background processing will need to introduce a scheduler or adapt to read-time computation

### Version Comparison Strategy (INV-002)
- FR-007 matching/comparison rules implemented as pure, database-independent functions in `backend/utils/version_compare.py`
- `RepositoryPackage` has no `publisher` column, so publisher is not used to disambiguate repository-catalog matches
- Results are not persisted; there is no "comparison results" database table

### Repository Upload Strategy (REP-001)
- Filesystem I/O and hashing logic (`backend/utils/file_storage.py`) is kept pure and database-independent
- Files are streamed in 1 MiB chunks; SHA-256 checksum computed incrementally
- Extension (not content/magic bytes) validated against the declared Installer Type
- Duplicate-entry detection reuses INV-002's `normalize_software_name`

### Deployment Creation Strategy (DEPLOY-001)
- `DeploymentRepository` follows the "pure data-access, no business rules" separation already established by `RepositoryPackageRepository`/`ClientRepository`
- `DeploymentService` composes a `RepositoryService` instance to reuse `get_package`
- Validation is strictly ordered and front-loaded: package → clients-exist → clients-not-active, all before any row is created
- No explicit `db.rollback()` call anywhere — relies on `get_db()`'s `finally: db.close()` pattern already used by every other service
- `ACTIVE_DEPLOYMENT_STATUSES` defined once at module scope in `deployment_repository.py`

### Deployment Polling Strategy (DEPLOY-002)
- `get_pending_target_for_client` is a new, narrower query, deliberately separate from DEPLOY-001's broader active-status queries
- Client isolation enforced inside the SQL `WHERE` clause, never by filtering an already-fetched list in Python
- Poll is a pure read by design — no `db.add`/`flush`/`commit` anywhere in the poll path
- Endpoint added to the existing `agent.py` router, reusing its router-wide protection

### Installer Download & Execution Strategy (DEPLOY-003)
- `get_target_for_client` is deliberately not restricted to `Pending` status, unlike DEPLOY-002's poll query — a target already `Downloading` (interrupted download) must still resolve
- "Not found" and "belongs to another client" are made indistinguishable on purpose (both 404, same message)
- Installer downloads are audit-logged; polls are not (PRS FR-016 explicitly names "Installer Downloads")
- Checksum verification and silent execution live entirely client-side
- `build_command` tokenizes the template with `shlex.split` **before** substituting the real (backslash-containing) installer path
- Retry policy is intentionally asymmetric: only the download step retries; checksum mismatches and installer failures are immediate, definitive failures

### Deployment Status Reporting & Cancellation Strategy (DEPLOY-004)
- **`STATUS_TRANSITIONS` is an explicit, closed matrix**, not a permissive "any non-terminal → any status" rule — this was a deliberate choice to make FR-012's Deployment Status Values table directly enforceable in code and to reject nonsensical transitions (e.g. skipping `Downloading`/`Installing`, or reporting against an already-terminal target) with a clear `409` rather than silently accepting them.
- **`report_status` reuses DEPLOY-003's `get_target_for_client`** for client-scoped authorization rather than introducing a parallel lookup — the same "not found" vs. "belongs to another client" indistinguishability DEPLOY-003 established applies here too.
- **Cancellation uses a new, deliberately unscoped `get_target_by_id`** (rather than `get_target_for_client`) because the actor is an *administrator*, who is authorized to act on any client's target — the client-scoping pattern used everywhere else in the Deployment domain is specific to Client-Agent-facing endpoints and does not apply to admin-facing ones.
- **Idempotent same-status reporting** avoids the client's own retry logic (`_report_status_with_retries`) from generating spurious `409`s if an earlier successful report's response was lost before the client saw it.
- **`completion_time` is computed server-side**, not trusted from the client, consistent with every other server-authoritative timestamp already in this codebase (`registration_date`, `last_heartbeat`, `created_at`/`updated_at`).
- **Only terminal outcomes are audit-logged** — intermediate `Downloading`/`Installing` reports update the row without a corresponding audit-log entry, mirroring DEPLOY-002's "routine traffic, not itself security-relevant" rationale for polling; this keeps the audit log focused on higher-value events (registration, key issuance, uploads, deployment creation/completion/cancellation) rather than every intermediate progress tick.
- **DEPLOY-003 pre-aligned `DeploymentExecutionResult`'s status vocabulary with `DeploymentStatus`** specifically so DEPLOY-004 would need no translation/adapter layer between "what the client computed locally" and "what the server's request schema expects" — this alignment was called out as a deliberate anticipatory design choice in DEPLOY-003's own closeout notes and paid off directly here.
- **No new router, model, or migration** — both new endpoints live on the two existing routers that already host their sibling Deployment endpoints (`agent.py` for client-facing, `deployments.py` for admin-facing), reusing existing DI providers and dependencies without modification.

### Future Migration Considerations
- SQLAlchemy dialect-portable `Uuid` type used for all primary/foreign keys
- `Secure` cookie flag configurable — must be set `True` once HTTPS is deployed
- CORS with credentials requires concrete origin list for cross-origin requests

---

## Known Issues / Technical Debt

| Issue | Status | Impact |
|-------|--------|--------|
| **No automated test framework** | Tracked | All verification manual/scripted; `tests/` empty; `pytest` not in requirements |
| **Router-level agent protection not automatically inherited** | Process risk | Future routers must independently apply `dependencies=[Depends(require_client_api_key)]` unless documented exception (registration) |
| **No admin-facing listing endpoints** | Tracked | Clients, provisioning keys, and repository packages only visible via direct database inspection or (for repository packages) indirectly through the version-comparison endpoint; REP-002 added a repository package listing view; there is still no "list clients" or "list deployments"/"deployment history" endpoint (DASH-002) even though DEPLOY-004 now populates real terminal statuses |
| **`RepositoryPackage` has no `publisher` column** | Tracked | FR-007's optional publisher-based match disambiguation cannot be applied against the repository catalog until/unless a future ticket adds this column and a migration |
| **No approval workflow for uploaded packages** | Tracked | REP-001 persists every valid upload directly as `APPROVED` |
| **Pre-existing cosmetic nit** | Untouched | `auth.py` declares unused `logger` |
| **CORS + credentialed cross-origin** | Condition | `CORS_ORIGINS="*"` + `allow_credentials=True` is invalid for browsers; needs concrete origin list for separate frontend |
| **`dev_seed_client.py` not retired** | Untouched | Still functional |
| **No expiration/revocation for provisioning keys** | Future work | Issued-but-never-claimed keys remain valid indefinitely |
| **No scheduler for OFFLINE detection** | Design choice | Offline status computed at read time |
| **`updated_at` serves as registration timestamp** | Implicit | No separate `last_registration` field |
| **DEPLOY-003 has not been tested yet** | Tracked | Implementation complete and syntax-validated only; scheduled for a separate validation phase, now grouped with DEPLOY-004's |
| **DEPLOY-004 has not been tested yet** | Tracked | Implementation complete and syntax-validated only (`ast.parse` on all 8 files, plus a manual client/server interface cross-check); no `TestClient` endpoint tests, no end-to-end agent-cycle run, no regression pass yet performed; scheduled for the same separate validation phase as DEPLOY-003 |
| **`agent.deployment.manager` not wired into a scheduler** | Tracked | The client-side workflow (poll → download → verify → execute → report) is a manually-invoked entry point (`python -m agent.deployment.manager`); no Scheduler Module exists yet to run it automatically alongside `agent.main`'s inventory cycle |
| **No deployment history/listing dashboard yet** | Tracked | A created deployment can now progress fully to `Completed`/`Failed`/`Cancelled` in the database (DEPLOY-004), but can currently only be observed via direct database inspection — DASH-002 (Deployment Monitoring) remains unimplemented |
| **`CURRENT_STATE.md` availability during DEPLOY-004 implementation** | Resolved by this update | `CURRENT_STATE.md` was unavailable inside the implementation sandbox during DEPLOY-004's own turn and was therefore not updated at that time; this v1.4 document is that deferred update, produced from the DEPLOY-004 implementation transcript and the previous v1.3 baseline |

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
- Authentication: admin successes + failures; client failures only
- Registration, inventory, repository, deployment operations logged
- Version comparison (INV-002) logs at DEBUG level only
- Repository package uploads (REP-001) are audit-logged at INFO on success and WARNING on a rejected duplicate
- Deployment creation (DEPLOY-001) is audit-logged at INFO on success only; rejected requests are not audit-logged
- **Deployment status reporting (DEPLOY-004) is audit-logged only for terminal outcomes** (`DEPLOYMENT_COMPLETED`/`DEPLOYMENT_FAILED`); intermediate `Downloading`/`Installing` reports are not individually audit-logged (mirrors the polling rationale)
- **Deployment cancellation (DEPLOY-004) is audit-logged** on every successful cancellation
- Unexpected errors logged globally by `backend/core/exceptions.py`

### Error Handling
- Every endpoint validates inputs, handles exceptions, returns consistent responses
- `AppException` (and `AuthenticationError` subclass) is standard base for all business-rule errors
- `DeploymentPackageUnavailableError` (400), `DeploymentClientNotFoundError` (404), `DeploymentClientActiveError` (409) (DEPLOY-001) follow the same `AppException` pattern
- `DeploymentTargetNotFoundError` (404), `DeploymentTargetNotDownloadableError` (409), `DeploymentInstallerUnavailableError` (500) (DEPLOY-003) likewise follow the same pattern
- `DeploymentStatusTransitionError` (409), `DeploymentStatusReportValidationError` (400), `DeploymentCancellationTargetNotFoundError` (404), `DeploymentCancellationNotAllowedError` (409) (DEPLOY-004) likewise follow the same pattern
- Global handlers convert Pydantic validation errors and unhandled exceptions to standard `{"success", "message", "error"}` envelope

### Security Standards
- Passwords: bcrypt via Passlib, never plaintext
- API Keys: `secrets.token_urlsafe`, unique, SHA-256 hash-at-rest
- Session Cookies: HttpOnly, `Secure` configurable, CSRF-protected (double-submit)
- Repository Packages: SHA-256 computed and stored at upload time (REP-001); download-time re-verification by the Client Agent implemented (DEPLOY-003) — a mismatch is a definitive, non-retried failure, now reported to the server as `"Failed"` (DEPLOY-004)
- Repository Packages: server-generated, sanitized storage filenames only; uploads size-bounded and extension-validated
- Deployments: package must be `Approved` at creation time (DEPLOY-001); installer-level integrity verification before execution (DEPLOY-003)
- Silent installation: `subprocess.run(..., shell=False)` with a pre-tokenized argument list (DEPLOY-003); outcome reported to server (DEPLOY-004)
- Installer download endpoint: client-scoped, audit-logged on every outcome (DEPLOY-003)
- **Status report endpoint (DEPLOY-004): client-scoped via `CurrentClient.id` only, enforces an explicit legal-transition matrix, idempotent on duplicate same-status reports, terminal outcomes audit-logged**
- **Deployment cancellation endpoint (DEPLOY-004): admin-session + CSRF protected, allowed only from `Pending`, audit-logged**
- Version comparison endpoint: read-only, admin-session-protected, no CSRF required (NFR-028 scopes CSRF to state-changing requests)
- Repository upload / deployment creation / deployment cancellation endpoints: state-changing, admin-session **and** CSRF protected (NFR-028)

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
| `backend/api/routers/agent.py` | Add new agent-facing endpoints; DEPLOY-002/003/004 all added their respective endpoints here |
| `backend/api/routers/deployments.py` | Admin-facing only; DEPLOY-001 added creation, DEPLOY-004 added cancellation; a future DASH-002 ticket may add admin-facing listing here |
| `backend/repositories/deployment_repository.py` | DEPLOY-002 added the pending-target lookup, DEPLOY-003 added the download-target lookup, DEPLOY-004 added `get_target_by_id`/`update_status` — a future DASH-002 ticket will likely add listing/filter queries |
| `backend/services/deployment_service.py` | DEPLOY-002 added `poll_pending_deployment`, DEPLOY-003 added `prepare_installer_download`, DEPLOY-004 added `report_status`/`cancel_deployment_target` — a future DASH-002 ticket will likely add listing/summary logic |
| `backend/schemas/deployment.py` | DEPLOY-002 added the polling DTOs, DEPLOY-004 added the status-report/cancel DTOs — a future DASH-002 ticket will likely add listing response DTOs |
| `agent/deployment/manager.py` | DEPLOY-003 introduced the poll → download → verify → execute orchestration; DEPLOY-004 wired in status-report calls at every stage transition |
| `agent/communication/deployment_client.py` | DEPLOY-003 added `poll_deployment`/`download_installer`; DEPLOY-004 added `report_status` |
| `backend/services/` | Add business logic for new features |
| `backend/repositories/` | Extend with new data access methods |
| `backend/models/` | Add new models only when necessary |
| `backend/schemas/` | Add request/response schemas |

---

## Next Recommended Work

### DEPLOY-003 / DEPLOY-004 — Joint Validation Phase (Immediate Next Step)

Both DEPLOY-003 and DEPLOY-004's implementations are complete (see their closeout sections above), but per this project's workflow rules, testing is a separate phase from implementation and has not yet been performed for either ticket. Before DASH-001/DASH-002 begins, the following should be carried out:

- `TestClient`-based endpoint tests for `GET /api/agent/deployments/{target_id}/download` (DEPLOY-003): successful download, unauthenticated rejection, unknown/foreign `target_id` rejection (404, identical response either way), non-downloadable-status rejection (409), and expected audit log entries.
- `TestClient`-based endpoint tests for `POST /api/agent/deployments/{target_id}/status` (DEPLOY-004): each legal transition (`Pending→Downloading`, `Downloading→Installing`, `Installing→Completed`, `Installing→Failed`, etc.), illegal-transition rejection (409), idempotent same-status re-report (200, no duplicate audit entry), client-isolation (a client cannot report against another client's target), and terminal-outcome audit log verification.
- `TestClient`-based endpoint tests for `POST /api/admin/deployments/{target_id}/cancel` (DEPLOY-004): successful cancellation from `Pending`, rejection (409) once a target has moved past `Pending`, unauthenticated/missing-CSRF rejection, and audit log verification.
- A scripted or manual end-to-end run of `agent.deployment.manager.run_deployment_cycle` against a running server: verify the poll → download → checksum-verify → execute → report sequence completes and that the server's `DeploymentTarget.status` correctly reaches `Completed`/`Failed` in the database; verify a deliberately corrupted download is rejected and reported as `Failed` without executing anything; verify a non-zero installer exit code is correctly reported as `Failed` with the exit code populated.
- `pyflakes`/import-check across all new/modified files with the project's actual dependencies installed (not possible in either implementation sandbox, which had no network access).
- Regression pass confirming `DeploymentService.create_deployment` (DEPLOY-001), `poll_pending_deployment` (DEPLOY-002), and `prepare_installer_download` (DEPLOY-003) remain behaviorally unmodified by DEPLOY-004.

### DASH-001 — Dashboard Home, then DASH-002 — Deployment Monitoring (After Validation)

Once DEPLOY-003/DEPLOY-004 are validated, the deployment lifecycle is functionally complete end-to-end. The next logical tickets are the dashboard-facing ones: **DASH-001** (system overview) and **DASH-002** (deployment listing/monitoring, which specifically depends on DEPLOY-004's now-populated status data).

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
| Deployment Download & Silent Execution | ⚠ Implementation Complete — Testing Pending (DEPLOY-003) |
| Deployment Status Reporting & Cancellation | ⚠ Implementation Complete — Testing Pending (DEPLOY-004 — client-scoped status reporting drives `Pending→Downloading→Installing→Completed/Failed`; admin-scoped cancellation from `Pending`) |
| Client Agent | ⚠ Deployment polling, download, checksum verification, silent execution, and status reporting all implemented (DEPLOY-003/004); automatic registry scanning (INV-001 scaffolding) still pending full deployment; not yet wired into a scheduler |
| Deployment History / Monitoring Dashboard | ❌ Not yet implemented (DASH-002 — depends on DEPLOY-004, now implementation-complete) |
| Frontend Dashboard | ❌ Not yet implemented (all dashboard functionality is API-only so far) |

### Current Architecture (Summary)

- FastAPI backend with SQLAlchemy + SQLite
- Repository → Service → Router separation
- Admin: Session cookies + CSRF protection
- Client: Bearer API key (SHA-256 hash-at-rest)
- Router-level protection for authenticated `/api/agent/*` endpoints
- Software inventory snapshot synchronization implemented
- Version comparison against the approved repository catalog implemented, computed on demand (not persisted)
- Repository package upload and dashboard (list/search/detail/deactivate) implemented
- Deployment creation implemented: administrator creates a batch + one `DeploymentTarget` per targeted client (initial status `Pending`); fully atomic and audit-logged
- Deployment polling implemented: authenticated Client Agent retrieves its own `Pending` target, strictly scoped, no status transition, no audit log entry
- Deployment download and silent execution implemented (DEPLOY-003 — implementation complete, testing pending): client downloads its own target's installer (client-scoped, audit-logged), verifies SHA-256 checksum client-side, executes the administrator-defined silent command as a direct process
- **Deployment status reporting and cancellation implemented (DEPLOY-004 — implementation complete, testing pending):** the authenticated Client Agent now reports `Downloading`/`Installing` transitions and the final `Completed`/`Failed` outcome (with exit code/error message) via `POST /api/agent/deployments/{target_id}/status`, enforced against an explicit legal-transition matrix and persisted server-side; an administrator can cancel a still-`Pending` target via `POST /api/admin/deployments/{target_id}/cancel`. `DeploymentTarget.status` in the database can now, for the first time, actually reach a terminal state after creation.
- Client Agent scaffolding prepared for automated Windows Registry inventory collection; deployment-execution and status-reporting modules (`agent.communication.deployment_client`, `agent.installer`, `agent.deployment.manager`) added by DEPLOY-003/DEPLOY-004, not yet wired into a scheduler

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
- DEPLOY-003: Installer Download & Execution (client-scoped `GET /api/agent/deployments/{target_id}/download`; client-side checksum verification and direct-process silent execution) — **implementation complete; do not redesign, but note this ticket has not yet passed its own validation phase**
- DEPLOY-004: Deployment Status Reporting & Cancellation (client-scoped `POST /api/agent/deployments/{target_id}/status`; admin-scoped `POST /api/admin/deployments/{target_id}/cancel`) — **implementation complete; do not redesign, but note this ticket has not yet passed its own validation phase**

### Current Blockers

- No automated test framework (manual verification only)
- **DEPLOY-003 and DEPLOY-004 have not yet been tested/validated** — implementation and syntax-checking only; scheduled for a joint separate validation phase before DASH-001/DASH-002 begins
- No scheduler/background task infrastructure — `agent.deployment.manager` is a manually-invoked entry point, not yet automated
- No administrator dashboard **UI** for viewing uploaded inventory, repository packages, deployments, or comparison results (all such functionality is API-only so far)
- No admin-facing "list clients", "list inventory", or "list/history deployments" endpoints yet (planned for future dashboard-facing tickets — DASH-002 specifically depends on DEPLOY-004's now-implemented status data)

### Immediate Next Task

**DEPLOY-003 / DEPLOY-004 Joint Validation Phase, then DASH-001 — Dashboard Home**

Before starting any dashboard ticket, both DEPLOY-003 and DEPLOY-004's implementations (server endpoints + client-side poll/download/verify/execute/report workflow) should go through the separate validation phase described in "Next Recommended Work" above — `TestClient`-based endpoint tests for every new endpoint, a scripted end-to-end run of `agent.deployment.manager.run_deployment_cycle`, and a full regression pass. Once validated, **DASH-001** (system overview) should be started, followed by **DASH-002** (deployment monitoring/history), which depends directly on DEPLOY-004's now-implemented status data.

### Files Likely to Be Modified (DASH-001 / DASH-002)

| File | Reason |
|------|--------|
| `backend/api/routers/deployments.py` | DASH-002 will likely add a `GET /api/admin/deployments` listing/history endpoint here, alongside DEPLOY-001's creation and DEPLOY-004's cancellation endpoints |
| `backend/repositories/deployment_repository.py` | DASH-002 will likely add listing/filter/summary query methods |
| `backend/services/deployment_service.py` | DASH-002 will likely add listing/summary business logic, reusing `TERMINAL_DEPLOYMENT_STATUSES` (DEPLOY-004) where relevant |
| `backend/schemas/deployment.py` | DASH-002 will likely add listing response DTOs |
| `backend/api/routers/repository.py`, `backend/api/routers/updates.py` | DASH-001 will likely aggregate summary statistics from these existing endpoints/services rather than duplicating their logic |
| `backend/templates/`, `backend/static/` | DASH-001/DASH-002 will be the first tickets to actually wire Jinja2 templates, if the dashboard is implemented server-rendered rather than API-only |

### Key Decision for DEPLOY-004 (Completed)

Status reporting reused `DeploymentRepository`/`DeploymentService` (DEPLOY-001/002/003) and the same `CurrentClient`-derived client-isolation pattern already established — every status-report request is scoped to the authenticated client's own deployment target, never a client-supplied id used as an authorization boundary. `agent.deployment.manager.DeploymentExecutionResult`'s `status` field, deliberately pre-aligned with `backend.models.enums.DeploymentStatus`'s vocabulary since DEPLOY-003, required no translation step to reach the new reporting endpoint's request body — this anticipatory alignment was a deliberate DEPLOY-003 design choice that paid off directly in DEPLOY-004. Intermediate `Downloading`/`Installing` transitions are reported as separate calls (matching FR-012's step-by-step wording), with only the terminal outcome (`Completed`/`Failed`) additionally audit-logged; a single combined final report was not chosen, since FR-012 explicitly describes each transition being reported as it happens, and the intermediate transitions give the (not-yet-built) DASH-002 dashboard real-time-ish visibility into in-progress deployments once implemented. Cancellation was scoped strictly to the `Pending` state per FR-021's literal handling of the retrieval race condition, using a new, deliberately administrator-only unscoped lookup (`get_target_by_id`) rather than the client-scoped pattern used everywhere else in the Deployment domain.

### Key Decision for DASH-002 (Upcoming)

A future deployment-listing/history endpoint should reuse `DeploymentRepository`/`DeploymentService` rather than introducing parallel query modules, and should be able to filter/group by the `TERMINAL_DEPLOYMENT_STATUSES` set DEPLOY-004 already defines (`Completed`, `Failed`, `Cancelled`) versus the `ACTIVE_DEPLOYMENT_STATUSES` set DEPLOY-001 already defines (`Pending`, `Downloading`, `Installing`), rather than re-deriving either set. Whether history should be exposed per-batch (`Deployment`) or per-target (`DeploymentTarget`) — or both — should be resolved against the PRS's Deployment History Interface (§5.2.8) wording before implementation begins.

---

*End of CURRENT_STATE.md*
