# CURRENT_STATE.md

**Version:** 0.8  
**Last Updated:** August 7, 2026

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
| Deployment | Local Package Repository (not yet implemented) |

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
│   │   ├── agent.py               # Protected agent endpoints (ping, heartbeat, inventory upload)
│   │   ├── registration.py        # POST /api/register (CLIENT-001)
│   │   └── updates.py             # Admin version-comparison endpoint (INV-002)
│   └── dependencies.py            # DI providers (admin + client + services)
├── core/
│   ├── config.py
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
│   ├── repository_package.py
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
│   └── repository_package_repository.py   # INV-002 read-only repository catalog access
├── services/
│   ├── auth_service.py
│   ├── client_auth_service.py
│   ├── client_service.py
│   ├── heartbeat_service.py
│   ├── inventory_service.py               # Inventory synchronization service
│   └── version_comparison_service.py      # FR-007 version comparison business logic (INV-002)
├── utils/
│   └── version_compare.py                 # FR-007 name/version matching + comparison rules (INV-002)
└── schemas/
    ├── auth.py
    ├── client.py
    ├── inventory.py                       # Inventory upload request schemas
    └── updates.py                         # Version comparison response schemas (INV-002)

agent/                                     # Client Agent (initial implementation)
├── communication/                         # Server communication helpers
├── scanner/                               # Windows Registry inventory scanner
└── main.py                                # Agent entry point

repository/                                # Local package repository (not yet implemented)

scripts/
├── create_admin.py                        # Production admin provisioning
└── dev_seed_client.py                     # Development/testing client seed

docs/

tests/                                     # Empty skeleton (no pytest configured)

---

## Overall Progress

| Metric                    | Status                                          |
| ------------------------- | ------------------------------------------------ |
| **Current Version**       | v0.8                                            |
| **Development Stage**     | REP-001 — Repository Management (not yet started)|
| **Latest Stable Release** | INV-002 — Version Comparison                    |
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

### Current Ticket

**REP-001 — Repository Management** (not yet started)

### Next Ticket

**REP-001 — Repository Management**

**Purpose:** Implement the local software package repository, including installer upload, metadata validation, SHA-256 checksum verification, and package storage.

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
- `RepositoryPackageRepository` (new) — minimal read-only slice (`list_approved`) needed for comparison; excludes `INACTIVE` packages (FR-017 "removal" mechanism). Package upload/maintenance remains out of scope, deferred to REP-001.
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

**Important Note:** No database schema or migration changes were required — `UpdateStatus` is a Python-level enum used only for in-memory classification and API response shaping, not a database column. Repository package data will typically be empty until REP-001 (Repository Management) is implemented; the endpoint is fully functional and will simply report every inventory item as Not Managed until approved packages exist.

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
| POST   | `/api/register`                           | Client registration                                       | Provisioning key or existing API key  |
| GET    | `/api/agent/ping`                         | Verify client authentication                              | Client API key                        |
| POST   | `/api/agent/heartbeat`                    | Report client heartbeat                                   | Client API key                        |
| POST   | `/api/agent/inventory/upload`             | Upload complete installed software inventory (FR-005)     | Client API key                        |

### Database Status

- SQLite database initialized with all migrations applied
- Tables: `administrators`, `administrator_sessions`, `clients`, `client_provisioning_keys`, `software_inventories`, `repository_packages`, `deployments`, `deployment_targets`, `audit_logs`, `alembic_version`
- All models use UUID primary keys
- Relationships and constraints defined
- Audit logging integrated for all authentication and registration events
- **No schema changes in INV-002** — version comparison is computed on demand from existing `software_inventory` and `repository_packages` tables; no migration was added

### Authentication Status

**Administrator:**
- Session-based (HttpOnly cookie + separate CSRF cookie)
- Double-submit CSRF protection
- Sliding inactivity expiry
- `Secure` flag configurable (`SESSION_COOKIE_SECURE`, default `False` for HTTP-only prototype — **must set `True` for HTTPS**)

**Client:**

- `Authorization: Bearer <api_key>` header
- SHA-256 hash-at-rest validated against `Client.api_key_hash`
- Router-level protection for all `/api/agent/*` routes
- Registration endpoint uses its own credential resolution (existing `Client` OR unclaimed `ClientProvisioningKey`)
- Authenticated inventory uploads use the existing API key authentication without additional authorization requirements

### Client Workflow (Current)

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

## Deployment Workflow (Not Yet Implemented)

- Local Package Repository: not yet implemented (upload/maintenance — REP-001)
- Silent Installers: not yet implemented
- SHA-256 Package Validation: schema exists (`RepositoryPackage.checksum`) but upload-time computation logic not implemented

### Existing Infrastructure

- **No automated test framework** configured (`pytest` not in `requirements.txt`; `tests/` directory remains an empty skeleton). All verification is currently performed through manual API testing, PowerShell scripts, direct SQLite inspection, and (for INV-002) ad hoc scripted verification using FastAPI's `TestClient`.
- **No scheduler/background tasks** — client `OFFLINE` status is currently computed at read time rather than maintained by a background service. Version comparison (INV-002) follows this same "computed at read time" pattern.
- **No repository package upload endpoint** — `repository_packages` can only currently be populated by direct database access; `GET /api/admin/clients/{client_id}/updates` will report every inventory item as Not Managed until REP-001 introduces upload.
- **No administrator-facing inventory or client listing endpoints** — client registration and software inventory data are stored successfully and can now be compared against the repository (INV-002), but there is still no general "list clients" or "list inventory" endpoint. These capabilities remain planned for a future dashboard-facing ticket.
- **Client Agent scaffolding implemented** — communication layer, inventory scanner, and application entry point exist; automated Windows Registry inventory collection will be exercised through the deployed Windows Agent in future milestones.
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
## Pending Backlog

| Ticket | Purpose | Dependencies | Priority |
|--------|---------|--------------|----------|
| **REP-001** | Repository Management — upload packages, SHA-256 validation | CORE-002 | Next |
| **REP-002** | Repository Dashboard — manage repository packages | REP-001 | - |
| **DEPLOY-001** | Deployment Creation — create deployment tasks | INV-002 (Version Comparison) | - |
| **DEPLOY-002** | Agent Polling — clients poll for deployments | DEPLOY-001 | - |
| **DEPLOY-003** | Installer Download & Execution — client-side | DEPLOY-002 | - |
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
| **No admin-facing listing endpoints** | Tracked | Clients, provisioning keys only visible via direct database inspection; INV-002 added a per-client comparison view, but no general "list all clients" endpoint yet |
| **`RepositoryPackage` has no `publisher` column** | Tracked | FR-007's optional publisher-based match disambiguation cannot be applied against the repository catalog until/unless a future ticket adds this column and a migration |
| **Repository catalog empty until REP-001** | Tracked | `GET /api/admin/clients/{client_id}/updates` is fully functional but will classify every item as Not Managed until REP-001 introduces package upload |
| **Pre-existing cosmetic nit** | Untouched | `auth.py` declares unused `logger` (not called, left per "do not modify completed tickets unless integration requires") |
| **CORS + credentialed cross-origin** | Condition | `CORS_ORIGINS="*"` + `allow_credentials=True` is invalid for browsers; needs concrete origin list for separate frontend |
| **`dev_seed_client.py` not retired** | Untouched | Still functional; retiring judged out of scope for CLIENT-001 review |
| **No expiration/revocation for provisioning keys** | Future work | Issued-but-never-claimed keys remain valid indefinitely; worth revisiting with dashboard/key-management ticket |
| **No scheduler for OFFLINE detection** | Design choice | Offline status computed at read time; background jobs not yet introduced |
| **`updated_at` serves as registration timestamp** | Implicit | No separate `last_registration` field; registration updates touch `updated_at` |

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
- Unexpected errors logged globally by `backend/core/exceptions.py`

### Error Handling
- Every endpoint validates inputs, handles exceptions, returns consistent responses
- `AppException` (and `AuthenticationError` subclass) is standard base for all business-rule errors
- `ClientNotFoundError` (INV-002, `backend/api/routers/updates.py`) follows this same `AppException` pattern for its 404 case
- Global handlers convert Pydantic validation errors and unhandled exceptions to standard `{"success", "message", "error"}` envelope

### Security Standards
- Passwords: bcrypt via Passlib, never plaintext
- API Keys: `secrets.token_urlsafe`, unique, SHA-256 hash-at-rest
- Session Cookies: HttpOnly, `Secure` configurable, CSRF-protected (double-submit)
- Repository Packages: SHA-256 verification (schema in place; logic not yet implemented)
- Deployments: Validate package integrity before execution (not yet implemented)
- Version comparison endpoint: read-only, admin-session-protected, no CSRF required (NFR-028 scopes CSRF to state-changing requests)

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
| `backend/api/routers/agent.py` | Add new agent-facing endpoints (protected by `require_client_api_key`) |
| `backend/repositories/repository_package_repository.py` | REP-001 will extend this with write operations (upload, metadata update, deactivate) |
| `backend/services/` | Add business logic for new features |
| `backend/repositories/` | Extend with new data access methods |
| `backend/models/` | Add new models only when necessary |
| `backend/schemas/` | Add request/response schemas |

---

## Next Recommended Work

### REP-001 — Repository Management

**Purpose:** Implement the local software package repository: installer upload, metadata validation, SHA-256 checksum computation/verification, and package storage (FR-006).

**Expected Deliverables:**

- Installer upload endpoint (administrator-facing, session + CSRF protected)
- Metadata validation (software name, version, installer type, silent install command)
- SHA-256 checksum computation on upload, stored on `RepositoryPackage.checksum`
- Package file storage (outside the web-server-accessible directory, per PRS FR-006 Upload Validation Rules)
- Extend `RepositoryPackageRepository` (introduced by INV-002) with write operations: `create`, `update`, `deactivate`

**Notes for Implementer:**

- Reuse the existing `RepositoryPackageRepository` (`backend/repositories/repository_package_repository.py`); extend it with write methods rather than creating a second, competing repository.
- `VersionComparisonService.list_approved` (via the repository) already reads by `ApprovalStatus.APPROVED` — REP-001's "removal" (FR-017) should continue to be a status change to `INACTIVE`, not a row deletion, to preserve `VersionComparisonService`'s existing exclusion behavior and any future deployment history integrity.
- Do **not** modify `VersionComparisonService` or `GET /api/admin/clients/{client_id}/updates` unless a defect is discovered — once packages exist, comparison results will populate automatically with no code changes required.
- Follow the existing Repository → Service → Router architecture.
- No scheduler or background services are required.

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
| Client Agent | ⚠ Agent scaffolding implemented (automatic registry scanning pending deployment) |
| Repository Management | ❌ Not yet implemented (REP-001 — current next ticket) |
| Deployment | ❌ Not yet implemented |
| Frontend Dashboard | ❌ Not yet implemented |

### Current Architecture (Summary)

- FastAPI backend with SQLAlchemy + SQLite
- Repository → Service → Router separation
- Admin: Session cookies + CSRF protection
- Client: Bearer API key (SHA-256 hash-at-rest)
- Router-level protection for authenticated `/api/agent/*` endpoints
- Software inventory snapshot synchronization implemented
- Version comparison against the approved repository catalog implemented, computed on demand (not persisted)
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

### Current Blockers

- No automated test framework (manual verification only)
- No scheduler/background task infrastructure
- No administrator dashboard for viewing uploaded inventory or comparison results (API-only so far)
- No repository management module (no way to populate `repository_packages` other than direct DB access, so version comparison currently has nothing to match against in a fresh environment)
- No deployment management module

### Immediate Next Task

**REP-001 — Repository Management**

- Implement installer upload, metadata validation, and SHA-256 checksum computation (FR-006)
- Extend the existing `RepositoryPackageRepository` (introduced by INV-002) with write operations
- Store installer files outside the web-server-accessible directory
- Keep `VersionComparisonService` and its endpoint unmodified — they will pick up newly approved packages automatically

### Files Likely to Be Modified

| File | Reason |
|------|--------|
| `backend/api/routers/` | Add administrator repository-upload endpoints |
| `backend/repositories/repository_package_repository.py` | Add write operations (create/update/deactivate) |
| `backend/services/` | Add `RepositoryService` for FR-006 business logic |
| `backend/schemas/` | Add repository upload request/response schemas |

### Key Decision for REP-001

Implement repository package management using the existing Repository → Service → Router architecture, extending `RepositoryPackageRepository` (introduced by INV-002) rather than creating a second repository for the same table.

**Recommendation:** Treat `VersionComparisonService` as a stable consumer of `RepositoryPackageRepository.list_approved` — REP-001 should not need to modify INV-002's files at all; once approved packages exist in the database, comparison results populate automatically.
---

*End of CURRENT_STATE.md*
