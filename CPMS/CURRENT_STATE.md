# CPMS Current State
Version: v0.5
Last Updated: August 2026

---

# Project Summary

## Project

**Centralized Patch Management System (CPMS)**

A proof-of-concept centralized software patch management system for Windows computers within a Local Area Network (LAN).

The system is designed as an OJT/Capstone project to demonstrate centralized software inventory collection, version comparison, repository management, and remote software deployment. It is **not intended to replace enterprise solutions such as Microsoft SCCM or Microsoft Intune.**

---

# Current Implementation Status

## Current Development Stage

Current Ticket
: CLIENT-002 — Heartbeat Service (not yet started)

Current Version
: v0.5

Latest Stable Release
: Client Registration Complete

Repository Status
: Active Development

Architecture Status
: Stable

Regression Status
: No known regressions from completed tickets. Full regression suite (CORE-001, CORE-002, AUTH-001, AUTH-002) re-verified together in this closeout pass, plus new CLIENT-001 scenarios (new registration, idempotent re-registration, invalid payload, invalid API key, missing Authorization header, both registration-conflict cases, and an `/api/agent/ping` cross-check confirming AUTH-002's client authentication still works against a client created via real registration rather than `dev_seed_client.py`) — see CLIENT-001 completion notes below. Migration round-trip re-verified: fresh `upgrade head` → `downgrade base` → `upgrade head` → `alembic check` all clean.

Known Issues
: None blocking. See "Known Gaps / Technical Debt" below for tracked, non-blocking items.

Current Branch
: main

---

# Technology Stack

## Backend

- FastAPI
- SQLAlchemy ORM (2.x style)
- Alembic
- SQLite
- Pydantic / Pydantic-Settings

## Frontend

- Bootstrap 5
- Jinja2 Templates (not yet wired up — no templates implemented)
- HTMX (optional, not yet used)

## Client Agent

- Not yet implemented (CLIENT-002+ tickets). CLIENT-001 implemented server-side registration only; no Python Client Agent process exists yet.

## Authentication

Administrator
- Session Authentication (HttpOnly + `Secure`-configurable cookie, double-submit-cookie CSRF, sliding inactivity expiry)

Client
- API Key Authentication (`Authorization: Bearer <key>`, SHA-256 hash-at-rest, validated against `Client.api_key_hash`)
- Client Provisioning Keys (FR-020, minimal slice — CLIENT-001): administrator-issued, not-yet-claimed keys (`ClientProvisioningKey.key_hash`), claimed (and deleted) at first successful `POST /api/register`

## Deployment

- Local Package Repository (not yet implemented)
- Silent Installers (not yet implemented)
- SHA-256 Package Validation (not yet implemented — schema exists on `RepositoryPackage.checksum`)

---

# Completed Tickets

---

## CORE-001 — Backend Foundation

### Status

✅ Production Ready

### Completed Features

- FastAPI Application Initialization
- Project Structure
- Configuration Loader
- Dependency Injection
- Logging Configuration
- Startup Events
- Environment Loading
- Swagger/OpenAPI
- Requirements Management

### Regression Status

Passed (re-verified in this closeout pass)

---

## CORE-002 — Database Layer

### Status

✅ Production Ready

### Completed Features

- SQLAlchemy Configuration (2.x declarative style, `Uuid` PKs)
- Session Management
- Declarative Base
- BaseModel / AuditModel abstract mixins
- Administrator Model
- Client Model
- Software Inventory Model
- Repository Package Model
- Deployment Model
- Deployment Target Model
- Audit Log Model
- Alembic Integration (migrations under `backend/database/migrations/`)
- Relationships
- Constraints (FK `ondelete` semantics deliberately chosen per relationship — see model docstrings)
- Database Initialization

### Regression Status

Passed (re-verified in this closeout pass: fresh `upgrade head` → `downgrade base` → `upgrade head` → `alembic check` all clean)

---

## AUTH-001 — Administrator Authentication

### Status

✅ Production Ready

### Completed Features

- Administrator Login (`POST /api/admin/login`)
- Administrator Logout (`POST /api/admin/logout`)
- Password Hashing (Passlib/bcrypt, `bcrypt` pinned to `4.0.1` for `passlib==1.7.4` compatibility)
- `AdministratorSession` DB-backed session model (addition beyond the PRS/SAD data dictionary — documented in the model's docstring)
- Session Cookie Middleware/Dependency (`require_administrator` / `CurrentAdministrator`)
- CSRF Protection (double-submit cookie: `verify_csrf_token` / `CSRFProtection`)
- Current Administrator Provider (`GET /api/admin/me`)
- Authentication Logging (audit log: `ADMIN_LOGIN_SUCCESS`, `ADMIN_LOGIN_FAILURE`, `ADMIN_LOGOUT`)
- `scripts/create_admin.py` bootstrap CLI (FR-019's documented out-of-band provisioning step)

### Known, Documented Deviation

Ticket text requested "JWT authentication"; implemented session-cookie authentication instead, per FR-019/NFR-028/PRS Appendix B, which explicitly specify session cookies. Documented in `backend/services/auth_service.py`.

### Regression Status

Passed (re-verified in this closeout pass)

---

## AUTH-002 — Client Authentication

### Status

✅ Production Ready

### Completed Features

- API Key Validation (`ClientAuthService.authenticate`, hashes the presented key with the same SHA-256 primitive used for admin sessions and compares against `Client.api_key_hash`)
- `ClientRepository` (`get_by_api_key_hash` — minimal, scoped to this ticket's need; CLIENT-001 will extend it)
- Client Authentication Dependency (`require_client_api_key` / `CurrentClient`), extracting `Authorization: Bearer <key>` per PRS Appendix B
- Client Authentication "Middleware" — realized as a router-level dependency (`dependencies=[Depends(require_client_api_key)]` on the new `agent` router) so every current and future route added to that router is automatically protected, satisfying "all agent endpoints protected" without relying on each new endpoint remembering to declare the dependency individually
- `GET /api/agent/ping` — demonstration/verification endpoint (not PRS-documented, analogous to `/api/health` and `/api/admin/me`)
- Authentication failure logging (audit log: `CLIENT_AUTH_FAILURE`; successes intentionally not logged individually — see rationale in `backend/services/client_auth_service.py`)
- `scripts/dev_seed_client.py` — development/testing-only utility to create a `Client` row with a known API key, pending CLIENT-001's real registration flow

### Known, Documented Scoping Decision

The Backlog lists FR-020 (Client API Key *Provisioning*, i.e. an admin-facing `POST /api/admin/keys` issuance endpoint) as this ticket's "Related Requirement," but AUTH-002's own literal deliverables ("API Key validation, Client authentication middleware, Authentication dependency") and acceptance criteria describe FR-002 (Client Authentication) instead. FR-020's "pending, not-yet-claimed key" workflow is chronologically and structurally coupled to FR-001 Client Registration (CLIENT-001, not yet implemented) and was deliberately **not** implemented in this ticket to avoid either (a) inventing a new provisioning table whose "claiming" logic only makes sense once CLIENT-001 exists, or (b) relaxing `Client`'s existing `NOT NULL` columns to allow "shell" rows before registration. **`POST /api/admin/keys` (FR-020) remains unimplemented and should be built together with CLIENT-001**, where issuance and registration/claiming naturally belong together. Full reasoning documented in `backend/services/client_auth_service.py`.

### Bugfix (carried from AUTH-001, applied during this ticket's development)

`backend/core/exceptions.py`'s `handle_validation_error` now passes Pydantic's error list through `jsonable_encoder` before returning it — a raw exception object inside a `field_validator`'s error `ctx` was not JSON-serializable and crashed the 422 handler into an unhandled 500. Latent since CORE-001; surfaced and fixed during AUTH-001, unaffected by AUTH-002.

### Regression Status

Passed — see AUTH-002 completion report (this session) for full test inventory, including CORE-001/CORE-002/AUTH-001 re-verification and two new cross-mechanism isolation checks (admin session cookie does not authenticate agent routes and vice versa).

---

## CLIENT-001 — Client Registration

### Status

✅ Production Ready

### Completed Features

- Registration endpoint (`POST /api/register`) implementing FR-001's create-or-update workflow, matched on `agent_guid` (never hostname/IP)
- `ClientService.register` (`backend/services/client_service.py`) — the FR-001 business logic: looks up the Agent GUID, creates a new `Client` when unknown, or refreshes `hostname`/`ip_address`/`operating_system`/`agent_version` on an existing one (idempotent re-registration; `updated_at` serves as the "last registration timestamp")
- `ClientRepository` extended with `get_by_agent_guid`, `create`, and `update_registration` (AUTH-002's own note: "add methods here, not a second repository")
- `ClientRegistrationRequest` schema (`backend/schemas/client.py`) — validates `agent_guid`, `hostname`, `ip_address` (real IPv4/IPv6 via `ipaddress`), `operating_system`, `agent_version`, with lengths capped to match the `clients` table's column widths
- Audit logging: `CLIENT_REGISTERED`, `CLIENT_REGISTRATION_UPDATED`, `CLIENT_REGISTRATION_CONFLICT`, `CLIENT_AUTH_FAILURE` (reused from AUTH-002), `CLIENT_KEY_PROVISIONED`
- Dashboard integration: registered clients are ordinary rows in the existing `clients` table (via `ClientRepository`), so a future dashboard/listing ticket needs no schema or repository changes — no listing endpoint or UI was built in this ticket (none was required)

### Known, Documented Conflict — and its resolution

The ticket brief said the registration endpoint "should be obtained through the existing authentication dependency" (`require_client_api_key`/`CurrentClient`). That dependency, however, **only** ever resolves a key that already matches an existing `Client.api_key_hash` — which is structurally impossible to satisfy for a brand-new agent's very first registration request (no `Client` row exists yet to match against). Per this project's standing instruction ("If implementation conflicts with documentation: identify the conflict, explain it, do not invent a new design"), this was flagged rather than silently worked around, and resolved exactly along the path `CURRENT_STATE.md`'s own "Notes for CLIENT-001's implementer" (previous version of this document) had already anticipated: implementing the minimal slice of **FR-020 Client API Key Provisioning** needed to unblock FR-001, since AUTH-002 had explicitly deferred FR-020 "to be built together with CLIENT-001."

This added:

- `ClientProvisioningKey` model + migration (`96d9bed20171_add_client_provisioning_keys_table`) — an administrator-issued, not-yet-claimed API key. Existence = unclaimed; claiming (at first successful registration) creates the `Client` row using the key's hash and deletes the provisioning row. Documented in full in the model's own docstring (following the same "DESIGN NOTE" convention already used by `AdministratorSession` and `Deployment`).
- `ClientProvisioningKeyRepository` (`create`, `get_by_key_hash`, `delete`).
- `POST /api/admin/keys` (FR-020, PRS Appendix B) added to the existing `backend/api/routers/auth.py` (admin session + CSRF protected) — generates and returns a plain-text key exactly once.
- `ClientAuthService.resolve_registration_credential` — resolves a presented registration key against *either* an existing `Client` (re-registration) *or* an unclaimed `ClientProvisioningKey` (first-time registration); raises `AuthenticationError` (401) otherwise. `ClientAuthService.provision_key` implements the FR-020 issuance step itself.
- `POST /api/register` lives on its **own new router** (`backend/api/routers/registration.py`), not on `agent.py` — `agent.py`'s router-wide `dependencies=[Depends(require_client_api_key)]` guarantee (AUTH-002) was deliberately left untouched rather than weakened. `agent.py` and `require_client_api_key` are byte-for-byte unmodified except for one renamed-but-behavior-identical helper (see below).
- `backend.api.dependencies._extract_bearer_token` was renamed to the public `extract_bearer_token` (logic unchanged) so the new registration router can reuse it instead of duplicating header-parsing logic. This was the only change to `dependencies.py` beyond additive DI providers.

Two conflict scenarios are explicitly guarded against (both verified — see Regression Status below): an already-claimed key cannot register a second, different Agent GUID (409), and a fresh/different key cannot "hijack" an Agent GUID that already belongs to another client (409).

### Regression Status

Passed. Full regression suite (CORE-001 health check; AUTH-001 login/session/CSRF/logout/protected-route rejection; AUTH-002 `dev_seed_client.py`-issued key still authenticates on `/api/agent/ping`, invalid key still rejected) re-verified alongside 20 new CLIENT-001-specific checks (new registration, idempotent re-registration with no duplicate row, invalid payload, invalid API key, missing `Authorization` header, both conflict scenarios, provisioning-key issuance auth/CSRF gating, and direct SQLite/audit-log inspection). Migration round-trip re-verified: fresh `upgrade head` → `downgrade base` → `upgrade head` → `alembic check` all clean. `python -m pyflakes backend/ scripts/` reports no new warnings (the one pre-existing warning, an unused import in AUTH-001's `auth_service.py`, predates this ticket and was left untouched).

---

# Stable Modules

The following modules are considered production-ready.

Unless required for integration, these modules should **NOT** be redesigned or refactored.

- Backend Foundation
- Database Layer
- Administrator Authentication
- Client Authentication
- Client Registration

Existing architecture must be preserved.

---

# Current Architecture

```
Presentation Layer

Frontend
      │
      ▼
FastAPI Routers
      │
      ▼
Service Layer
      │
      ▼
Repository Layer
      │
      ▼
SQLAlchemy ORM
      │
      ▼
SQLite Database
```

---

# Project Structure

```
backend/

    api/
        routers/
            health.py
            auth.py
            agent.py
            registration.py      (CLIENT-001 — POST /api/register)
        dependencies.py

    core/
        config.py
        security.py
        logging.py
        exceptions.py

    database/
        base.py
        database.py
        session.py
        migrations/

    models/
        base.py
        enums.py
        administrator.py
        administrator_session.py
        client.py
        client_provisioning_key.py   (CLIENT-001 — minimal FR-020 slice)
        software_inventory.py
        repository_package.py
        deployment.py
        deployment_target.py
        audit_log.py

    repositories/
        administrator_repository.py
        administrator_session_repository.py
        audit_log_repository.py
        client_repository.py                    (extended by CLIENT-001)
        client_provisioning_key_repository.py    (CLIENT-001)

    services/
        auth_service.py
        client_auth_service.py    (extended by CLIENT-001 — FR-020 resolution/issuance)
        client_service.py         (CLIENT-001 — FR-001 registration logic)

    schemas/
        auth.py
        client.py         (CLIENT-001)

agent/            (empty — no Python Client Agent process yet; CLIENT-002+ tickets)

repository/       (empty — REP-* tickets)

scripts/
    create_admin.py
    dev_seed_client.py    (still functional; real registration now exists via POST /api/register,
                            so this dev-only scaffold is optional going forward — not yet retired)

docs/

tests/            (empty — no test framework configured yet; TEST-001 introduces one)
```

---

# Important Files

## Backend Entry

```
backend/main.py
```

## Configuration

```
backend/core/config.py
```

## Database

```
backend/database/database.py
backend/database/session.py
backend/database/base.py
```

## Security Primitives

```
backend/core/security.py
```

## Dependencies (DI providers)

```
backend/api/dependencies.py
```

## Authentication Routers

```
backend/api/routers/auth.py           (administrator: login/logout/me/keys[FR-020])
backend/api/routers/agent.py          (client agent: ping; future authenticated agent endpoints go here)
backend/api/routers/registration.py   (client agent: POST /api/register — CLIENT-001; deliberately its own
                                        router, NOT agent.py — see CLIENT-001 completion notes above)
```

## Database Models

```
backend/models/
```

## Repository Layer

```
backend/repositories/
```

## Service Layer

```
backend/services/
```

## Alembic

```
alembic.ini
backend/database/migrations/
```

## Operational Scripts

```
scripts/create_admin.py       (production: FR-019-documented admin provisioning)
scripts/dev_seed_client.py    (development/testing only — see AUTH-002 notes above)
```

---

# Architectural Decisions

The following architectural decisions have already been established.

## Backend

- FastAPI remains the backend framework.
- SQLAlchemy ORM (2.x declarative style) is mandatory.
- SQLite remains the project database; SQLAlchemy's dialect-portable `Uuid` type is used for all primary/foreign keys.
- Dependency Injection is used throughout the application (`backend/api/dependencies.py` is the single shared location for all DI providers, admin and client alike).

## Architecture

- Repository Pattern
- Service Layer Pattern
- Thin Routers
- Clean Architecture
- Modular Components

Business logic must never be placed inside API routers.

Routers are responsible only for:

- Input Validation
- Calling Services
- Returning Responses

## Authentication

- Administrator authentication: session cookie (HttpOnly) + separate CSRF cookie (double-submit pattern), NOT JWT — see AUTH-001 notes.
- Client authentication: `Authorization: Bearer <api_key>`, hashed at rest (SHA-256), validated against `Client.api_key_hash` — see AUTH-002 notes.
- Both mechanisms share `backend/core/security.py`'s token/hash primitives and the common `AuthenticationError` (401) exception type, but are implemented as two separate service classes (`AuthService`, `ClientAuthService`) per the Single Responsibility principle, even though the SAD describes them as one conceptual "Authentication Module."
- **Router-level dependency injection** (`APIRouter(dependencies=[...])`) is this project's established pattern for "protect every route under this prefix automatically," used for `/api/agent/*`. Any future router carrying agent-facing endpoints must either add its routes to the existing `agent` router or replicate this same `dependencies=[Depends(require_client_api_key)]` pattern — it is not automatic across unrelated router instances.
- **Registration is the one deliberate exception to `require_client_api_key`** (CLIENT-001): `POST /api/register` cannot depend on a mechanism that only resolves *already-registered* clients, so it performs its own inline resolution via `ClientAuthService.resolve_registration_credential` (existing `Client` OR unclaimed `ClientProvisioningKey`) and lives on its own router (`registration.py`), never on `agent.py`. Any future endpoint with the same "no `Client` row yet" problem should follow this same pattern rather than weakening `agent.py`'s router-wide guarantee.
- **FR-020 (`POST /api/admin/keys`) is implemented** (CLIENT-001, resolving AUTH-002's deferred scoping note): administrator-issued, single-use-until-claimed provisioning keys (`ClientProvisioningKey`), hashed at rest with the same `hash_token` primitive as every other credential in this codebase.

---

# Coding Standards

Every implementation must follow:

- SOLID Principles
- Clean Code
- Dependency Injection
- Repository Pattern
- Service Layer Pattern
- Modular Design

Avoid duplicate implementations whenever possible.

Favor extending existing modules over creating replacements.

---

# Logging Standards

Every important operation should generate logs.

Examples include:

- Authentication (administrator: success + failure; client: failure only — see AUTH-002 rationale for why client successes are not individually audit-logged)
- Client Registration (not yet implemented)
- Inventory Upload (not yet implemented)
- Repository Upload (not yet implemented)
- Deployment (not yet implemented)
- Configuration Changes (not yet implemented)
- System Errors (handled globally by `backend/core/exceptions.py`)

Logging should remain structured and consistent.

Avoid excessive debug logging.

---

# Error Handling Standards

Every endpoint must:

- Validate Inputs
- Handle Exceptions
- Return Consistent Responses
- Log Unexpected Errors

Avoid generic exception handling unless logging or rethrowing.

`AppException` (and its `AuthenticationError` subclass) is the standard base for all business-rule errors; the global handlers in `backend/core/exceptions.py` convert these — and Pydantic validation errors, and any unhandled exception — into the standard `{"success", "message", "error"}` response envelope.

---

# Security Standards

Passwords

- Always hashed (bcrypt via Passlib)
- Never stored in plaintext

API Keys

- Securely generated (`secrets.token_urlsafe`, 256 bits of entropy)
- Unique
- Compared using secure methods (SHA-256 hash-at-rest; hash comparison, never plaintext storage)
- Provisioning keys (FR-020, CLIENT-001) follow the identical generation/hashing scheme; the plain-text value is returned exactly once by `POST /api/admin/keys` and cannot be retrieved again

Session Cookies

- HttpOnly
- `Secure` flag configurable (`SESSION_COOKIE_SECURE`, defaults to `False` for this HTTP-only prototype deployment — **must be set `True` once HTTPS is deployed**)
- CSRF-protected via double-submit cookie pattern

Repository Packages

- SHA-256 Verification (schema in place; upload/verification logic not yet implemented — REP-001)

Deployments

- Validate package integrity before execution (not yet implemented — DEPLOY-003)

---

# Database Standards

- SQLAlchemy ORM only.
- Avoid raw SQL.
- Maintain normalized relationships.
- Use transactions where appropriate.
- Avoid duplicated data.
- UUID primary keys throughout (deliberate deviation from the PRS's illustrative auto-increment integers — documented in `backend/models/base.py`).

---

# API Standards

RESTful API Design.

Examples (implemented so far)

```
GET     /api/health

POST    /api/admin/login
POST    /api/admin/logout
GET     /api/admin/me
POST    /api/admin/keys        (CLIENT-001 — FR-020)

GET     /api/agent/ping

POST    /api/register          (CLIENT-001 — FR-001)
```

All responses must use Pydantic Schemas for request validation and the standard `{"success", "message", "data"}` / `{"success", "message", "error"}` envelope for responses.

---

# Development Rules

Every future ticket must:

1. Respect existing architecture.
2. Preserve completed modules.
3. Build incrementally.
4. Maintain backward compatibility.
5. Reuse existing services.
6. Keep routers thin.
7. Follow Repository → Service → Router separation.
8. Implement production-quality code.
9. Avoid placeholder implementations.
10. Satisfy all acceptance criteria.

---

# Definition of Done

A ticket is considered complete only when:

- Code compiles successfully.
- Acceptance criteria are satisfied.
- Logging is implemented.
- Exceptions are handled.
- Tests pass (manual verification against a real SQLite database — no automated test framework exists yet; see "Known Gaps" below).
- Documentation is updated if necessary.
- No TODO placeholders remain.
- Existing architecture is preserved.

---

# Known Gaps / Technical Debt

These are tracked, non-blocking items — none prevent CLIENT-001 from being considered complete, but future tickets should be aware of them.

1. ~~FR-020 (Client API Key Provisioning / `POST /api/admin/keys`) is not implemented.~~ **Resolved by CLIENT-001** (minimal slice — key generation and claim-on-registration only; see below).
2. **No automated test framework is configured.** `pytest` is not in `requirements.txt`; the `tests/` directory remains an empty skeleton. All verification to date has been manual/scripted against a real SQLite database. TEST-001 (Backlog Milestone 10) is the ticket that introduces one.
3. **Router-level agent-route protection is not automatically inherited across separate router instances.** If a future ticket creates a new `APIRouter` for agent-facing endpoints instead of adding routes to the existing `agent` router, it must independently apply `dependencies=[Depends(require_client_api_key)]`. `registration.py` (CLIENT-001) is a deliberate, documented exception to this pattern (see "Architectural Decisions" above), not an oversight. This remains a process risk for other future routers, not a code defect.
4. **No admin-facing "list clients," "revoke API key," or "list outstanding provisioning keys" endpoints exist yet.** `ClientProvisioningKey` rows are currently only visible via direct database inspection; a dashboard/management ticket is expected to add read/listing endpoints. The underlying data (both `clients` and `client_provisioning_keys`) already fully supports this — no repository or schema changes should be needed when that ticket arrives.
5. **Minor pre-existing cosmetic nit (not fixed, not required for CLIENT-001):** `backend/api/routers/auth.py` (AUTH-001) declares a module-level `logger` that is never called (still true after CLIENT-001's new `/keys` endpoint was added to the same file, which also does not call it). Left untouched per "do not modify completed tickets unless integration requires it."
6. **CORS + credentialed cross-origin requests**: `CORS_ORIGINS` defaults to `"*"` with `allow_credentials=True`; browsers reject this combination for actual cross-origin cookie-bearing requests. Not currently an issue (server-rendered, same-origin dashboard per the SAD), but will need a concrete origin list if a separate frontend origin is ever introduced.
7. **`scripts/dev_seed_client.py` has not been retired**, despite the previous version of this document's note that it "should be retired once real registration exists." It remains harmless, unmodified, and still functional (re-verified in this ticket's regression pass); retiring it was judged out of scope for a review pass ("fix only genuine issues," not perform unrelated cleanup). A future ticket may remove it once the dashboard/CLIENT Agent tooling make it clearly redundant.
8. **No expiration or revocation for outstanding `ClientProvisioningKey` rows.** An issued-but-never-claimed key remains valid indefinitely. Not required by FR-020 as documented, but worth revisiting alongside a future dashboard/key-management ticket.

---

# Remaining Development Roadmap

```
CLIENT-002
Heartbeat Service

↓

INV-001
Inventory Collection

↓

INV-002
Inventory Dashboard

↓

REP-001
Repository Management

↓

REP-002
Repository Dashboard

↓

UPDATE-001
Version Comparison

↓

DEPLOY-001
Deployment Creation

↓

DEPLOY-002
Agent Polling

↓

DEPLOY-003
Installer Download & Execution

↓

DEPLOY-004
Deployment Status Reporting

↓

DASH-001
Dashboard Home

↓

DASH-002
Deployment Monitoring

↓

DASH-003
Audit Logs

↓

SYS-001
Configuration Management

↓

SYS-002
Logging System

↓

TEST-001
System Integration Testing

↓

TEST-002
Documentation & Demonstration
```

---

# Version History

## v0.1

Completed

- CORE-001 Backend Foundation

---

## v0.2

Completed

- CORE-002 Database Layer

---

## v0.3

Completed

- AUTH-001 Administrator Authentication

---

## v0.4

Completed

- AUTH-002 Client Authentication

---

## v0.5

Completed

- CLIENT-001 Client Registration (including the minimal FR-020 Client API Key Provisioning slice required to unblock it — see the CLIENT-001 completion notes above)

---

# Next Ticket

## CLIENT-002

**Title**

Heartbeat Service

## Objective

Track client availability (FR-003), so the dashboard can distinguish Online/Offline/Unknown clients instead of every registered client sitting at `status=UNKNOWN` forever (CLIENT-001 initializes new clients to `UNKNOWN` and never updates `status` or `last_heartbeat`).

## Expected Deliverables (per Backlog)

- Heartbeat endpoint
- Agent heartbeat
- Last seen updates
- Online/offline status

## Related Requirements

FR-002, FR-003

## Dependencies

CLIENT-001 (complete)

## Notes for CLIENT-002's implementer

- The `agent` router (`backend/api/routers/agent.py`, `prefix="/api/agent"`) already exists with `require_client_api_key` applied router-wide — unlike registration, heartbeat is a routine authenticated request from an *already-registered* client, so it belongs on this existing router (add a route, do not create a new one) and should declare `CurrentClient` to obtain the authenticated `Client` directly.
- `Client.status` (`ClientStatus` enum: `ONLINE`/`OFFLINE`/`UNKNOWN`) and `Client.last_heartbeat` (nullable `DateTime`) already exist on the model (CORE-002) and are currently never written to outside of `Client`'s default (`UNKNOWN`) — this ticket is what should start populating them.
- FR-003 requires clients to be marked `OFFLINE` after a configurable timeout with **no** heartbeat received — since there is no scheduler/background task infrastructure yet, this likely means computing "effective status" from `last_heartbeat` at *read* time (dashboard/listing) rather than requiring a running background job, unless a scheduler is judged in-scope for this ticket. Flag this design choice explicitly if it isn't already resolved by the PRS/SAD.
- `ClientRepository` should be extended with whatever heartbeat-specific update method is needed (e.g. `update_heartbeat`), following the same pattern CLIENT-001 used for `update_registration` — do not create a second Client repository.
- No dashboard UI is required unless integration demands it (same scoping pattern CLIENT-001 followed for its own "Dashboard Integration" deliverable).

---

# AI Development Workflow

For every new ticket:

1. Read **CURRENT_STATE.md**
2. Read the assigned ticket.
3. Inspect existing implementation.
4. Identify integration points.
5. Extend existing architecture.
6. Avoid redesigning completed modules.
7. Implement production-ready code.
8. Execute or update tests if applicable.
9. Produce implementation summary.
10. Update **CURRENT_STATE.md** for the next development session.

---

# Project Goal

By completion of **TEST-002**, the system should successfully demonstrate the complete proof-of-concept workflow:

```
Administrator Login

        │
        ▼

Client Registration

        │
        ▼

Heartbeat

        │
        ▼

Inventory Upload

        │
        ▼

Repository Upload

        │
        ▼

Version Comparison

        │
        ▼

Deployment Creation

        │
        ▼

Agent Polling

        │
        ▼

Installer Download

        │
        ▼

Silent Installation

        │
        ▼

Deployment Status Reporting

        │
        ▼

Dashboard Monitoring

        │
        ▼

Audit Logging

        │
        ▼

Successful End-to-End Demonstration
```

This represents the final proof-of-concept deliverable for the Centralized Patch Management System (CPMS) OJT project.
