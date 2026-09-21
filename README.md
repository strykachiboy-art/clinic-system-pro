# Clinic System Pro v5

Clinic System Pro v5 is a modular healthcare management backend built with Flask, SQLAlchemy, PostgreSQL-compatible persistence, JWT authentication, Redis, SocketIO, Celery, Pydantic, and a versioned API architecture.

## Architecture

The backend follows an application-factory architecture:

```text
Client
  |
  | HTTP / API v1
  v
Flask Application
  |
  +-- Authentication / Authorization
  +-- Multi-Clinic Tenant Isolation
  +-- RBAC / Access Control
  +-- Validation
  +-- Audit Logging
  +-- Business Services
  +-- SocketIO Realtime
  +-- Celery Background Jobs
  |
  +-------------------+
  |                   |
  v                   v
PostgreSQL           Redis
Source of Truth      Cache / Realtime / Task Infrastructure
```

The Flutter client will operate as a client/UI layer. Local SQLite storage is reserved for cache, offline state, and synchronization control data. PostgreSQL remains the authoritative source of truth.

## API Versioning

The canonical API namespace is:

```text
/api/v1/
```

All API blueprints are registered centrally under `/api/v1`.

Examples:

```text
POST /api/v1/auth/login
POST /api/v1/auth/register

GET  /api/v1/patients
GET  /api/v1/appointments

POST /api/v1/ai/drug-interactions

GET  /api/v1/pharmacy/drugs
POST /api/v1/prescriptions

GET  /api/v1/chat/...
GET  /api/v1/reports
```

The URL path is the source of truth for API version selection.

Unsupported versions such as:

```text
/api/v2/...
/api/v99/...
```

return HTTP 404 with the error code:

```text
api_version_not_supported
```

Non-versioned paths are not interpreted as API versions.

## Core Modules

The backend currently contains:

```text
Authentication & Identity
User / Staff
Patient
Clinic
Appointment
Consultation
Laboratory
Pharmacy
Prescription
Inventory
Billing
Ward
Ambulance
HIE
AI
Reports
Notifications
Audit
Settings
Asset Control
Dashboard
Advanced Access Control
Internal Clinical Chat
Profile
```

Profile acts as an aggregation layer over user, staff, and clinic information rather than a separate database entity.

## Database and Tenant Isolation

PostgreSQL is the production source of truth.

The backend enforces clinic-level tenant isolation together with authentication and role-based authorization.

Server-side authorization determines the authenticated actor and clinic context rather than trusting client-supplied actor or tenant identifiers.

## Authentication

The authentication system supports:

* JWT access tokens
* JWT refresh tokens
* Google OAuth
* token revocation
* role claims
* token-version validation
* account activity checks

Google OAuth uses the versioned callback:

```text
/api/v1/auth/google/callback
```

## Validation and Error Handling

Request validation uses Pydantic v2.

The application distinguishes domain failures such as:

```text
400 Domain Error
402 Insufficient Credits
404 Not Found
409 Conflict
422 Validation Error
```

API version failures use:

```text
404 api_version_not_supported
```

## Realtime and Background Processing

SocketIO provides realtime communication, including internal clinical chat functionality.

Celery handles background and scheduled work.

Redis is used for:

```text
JWT revocation state
rate limiting
Celery broker / result backend
SocketIO message queue
```

## Celery

Redis must be running at the URL configured by `REDIS_URL`.

Start the worker:

```powershell
celery -A celery_worker.celery worker --loglevel=info
```

Start the scheduler in a second terminal:

```powershell
celery -A celery_worker.celery beat --loglevel=info
```

The worker handles appointment reminders, overdue invoices, and monthly AI usage resets. Beat queues the recurring tasks configured in `app/extensions.py`.

## Testing

The project maintains a large isolated test suite.

Tests create and tear down their database state per test function to prevent shared-state leakage between tests.

Run the complete suite:

```powershell
pytest -q
```

Run API infrastructure tests:

```powershell
pytest app/tests/core/api -q
```

## Load Testing

Locust workloads are stored in:

```text
load_tests/
```

The load-testing environment targets the versioned API namespace.

Example environment variables:

```text
LOCUST_EMAIL
LOCUST_PASSWORD
LOCUST_PATIENT_ID
LOCUST_DRUGS
```

The current AI workload exercises authentication and the AI drug-interaction endpoint.

Large-scale benchmarking is intended to use distributed load generators rather than relying on a single development machine.

Concurrency and throughput are measured separately.

The planned scalability benchmark progresses through controlled stages before reaching the project target of 1,000,000 concurrent simulated users.

## Production Entry Point

Development execution uses:

```text
run.py
```

The WSGI application entry point is:

```text
wsgi:app
```

Production deployment should use a production WSGI/SocketIO-compatible serving architecture rather than Flask's development server.

## Development

Install dependencies from:

```text
requirements.txt
```

Create the required environment variables for the selected deployment environment, then run the application using the appropriate development or production entry point.

## Project Direction

The planned client architecture is:

```text
Flutter
   |
   | API v1 / SocketIO
   v
Flask Backend
   |
   +---- PostgreSQL
   +---- Redis
   +---- Celery
```

Offline synchronization will use SQLite as a local cache and control store while the backend remains authoritative.

Future synchronization capabilities include:

```text
offline queue
incremental sync
sync cursors
record versions
timestamps
retry / backoff
idempotency
deduplication
conflict resolution
tombstones
last_purged_at
```

The Rust White Glove Migration remains the final backend migration phase.
