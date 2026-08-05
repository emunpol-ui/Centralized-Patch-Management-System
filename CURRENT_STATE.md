# CPMS Current State
Version: v0.4
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
: CLIENT-001 — Client Registration (not yet started)

Current Version
: v0.4

Latest Stable Release
: Client Authentication Complete

Repository Status
: Active Development

Architecture Status
: Stable

Regression Status
: No known regressions from completed tickets. Full regression suite (CORE-001, CORE-002, AUTH-001, AUTH-002) re-verified together in this closeout pass — see AUTH-002 completion report for details.

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

- Not yet implemented (CLIENT-* tickets)

## Authentication

Administrator
- Session Authentication (HttpOnly + `Secure`-configurable cookie, double-submit-cookie CSRF, sliding inactivity expiry)

Client
- API Key Authentication (`Authorization: Bearer <key>`, SHA-256 hash-at-rest, validated against `Client.api_key_hash`)

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

# Stable Modules

The following modules are considered production-ready.

Unless required for integration, these modules should **NOT** be redesigned or refactored.

- Backend Foundation
- Database Layer
- Administrator Authentication
- Client Authentication

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
        software_inventory.py
        repository_package.py
        deployment.py
        deployment_target.py
        audit_log.py

    repositories/
        administrator_repository.py
        administrator_session_repository.py
        audit_log_repository.py
        client_repository.py

    services/
        auth_service.py
        client_auth_service.py

    schemas/
        auth.py

agent/            (empty — CLIENT-* tickets)

repository/       (empty — REP-* tickets)

scripts/
    create_admin.py
    dev_seed_client.py

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
backend/api/routers/auth.py      (administrator: login/logout/me)
backend/api/routers/agent.py     (client agent: ping; future agent endpoints go here)
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

GET     /api/agent/ping
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

These are tracked, non-blocking items — none prevent AUTH-002 from being considered complete, but future tickets should be aware of them.

1. **FR-020 (Client API Key Provisioning / `POST /api/admin/keys`) is not implemented.** Should be built together with CLIENT-001, per the scoping note in `backend/services/client_auth_service.py`.
2. **No automated test framework is configured.** `pytest` is not in `requirements.txt`; the `tests/` directory remains an empty skeleton. All verification to date has been manual/scripted against a real SQLite database. TEST-001 (Backlog Milestone 10) is the ticket that introduces one.
3. **Router-level agent-route protection is not automatically inherited across separate router instances.** If a future ticket creates a new `APIRouter` for agent-facing endpoints instead of adding routes to the existing `agent` router, it must independently apply `dependencies=[Depends(require_client_api_key)]`. This is a process risk, not a code defect.
4. **`AuthService` (admin) and `ClientAuthService` (client) are not the *authorized administrator* dashboard endpoints.** No admin-facing "list clients," "revoke API key," or similar management endpoints exist yet — deferred to CLIENT-001 and/or a dashboard ticket.
5. **Minor pre-existing cosmetic nit (not fixed, not required for AUTH-002):** `backend/api/routers/auth.py` (AUTH-001) declares a module-level `logger` that is never called. Left untouched per "do not modify completed tickets unless integration requires it" — noted here for whichever ticket next touches that file.
6. **CORS + credentialed cross-origin requests**: `CORS_ORIGINS` defaults to `"*"` with `allow_credentials=True`; browsers reject this combination for actual cross-origin cookie-bearing requests. Not currently an issue (server-rendered, same-origin dashboard per the SAD), but will need a concrete origin list if a separate frontend origin is ever introduced.

---

# Remaining Development Roadmap

```
CLIENT-001
Client Registration

↓

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

# Next Ticket

## CLIENT-001

**Title**

Client Registration

## Objective

Implement client registration (FR-001), so real `Client` rows can be created by an actual Client Agent over the network instead of `scripts/dev_seed_client.py`.

## Expected Deliverables (per Backlog)

- Registration endpoint
- Agent registration
- Client database creation
- Dashboard client listing

## Related Requirement

FR-001

## Notes for CLIENT-001's implementer

- `ClientRepository` (in `backend/repositories/client_repository.py`) already exists with `get_by_api_key_hash` — extend it with creation/lookup-by-`agent_guid`/update methods rather than creating a second Client repository.
- The `agent` router (`backend/api/routers/agent.py`) already exists with `require_client_api_key` applied at the router level. Registration itself is a special case: per FR-001, a NEW client authenticates for the *first* time using a key that has no `Client` row yet — this means registration cannot go through `require_client_api_key` as currently written (it looks up an existing `Client.api_key_hash`). CLIENT-001 will need to resolve this, most likely together with implementing FR-020's provisioning endpoint (see AUTH-002's documented scoping note in `backend/services/client_auth_service.py`), since the two are chronologically coupled.
- `scripts/dev_seed_client.py` should be retired once real registration exists.

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
