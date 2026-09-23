# Clinic System Pro v5

Clinic System Pro v5 is a modular, production-oriented healthcare management backend built with Flask, SQLAlchemy, PostgreSQL-compatible persistence, JWT authentication, Redis, Socket.IO, Celery, Pydantic, and a versioned API architecture.

The project is designed around strong tenant isolation, explicit authorization, transactional service boundaries, auditability, validation, observability, controlled performance testing, and a future Flutter client layer.

## Current Project Status

As of September 23, 2026, the project has completed its major backend hardening and core feature implementation phases.

Completed and hardened areas include:

* Application factory architecture
* Authentication and identity
* JWT access/refresh tokens
* Google OAuth
* Token revocation and token-version invalidation
* Role-based access control
* Multi-clinic tenant isolation
* IDOR protection
* Request and query validation with Pydantic v2
* Strict request typing and contract enforcement
* Centralized domain error handling
* Transactional service boundaries
* Pagination and deterministic ordering
* Lifecycle and state validation
* Historical-read semantics
* Audit logging
* Modern SQLAlchemy 2.x usage
* Migration cleanup and database hardening
* Route/schema integration hardening
* Service and route test hardening
* Configuration and integration hardening
* Internal clinical chat foundation
* Chat policy and rule-engine controls
* Request, database, Redis, Celery, Socket.IO, and system observability
* Controlled Locust performance/load-testing infrastructure

The current engineering focus has moved from performance/load benchmarking to resilience and recovery engineering.

The resilience and backup packages are currently scaffolded and intentionally contain structure only. Their implementation is a separate engineering phase.

## Architecture

The backend follows an application-factory architecture:

```text
                           Clients
                    ┌──────────┴──────────┐
                    │                     │
                HTTP / API v1         Socket.IO
                    │                     │
                    └──────────┬──────────┘
                               │
                        Flask Application
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        │                      │                      │
 Authentication &         Business Modules       Cross-Cutting Core
 Authorization                                    Services
        │                      │                      │
        ├─ JWT                 ├─ Patient              ├─ Validation
        ├─ OAuth               ├─ Appointment          ├─ Audit
        ├─ RBAC                ├─ Consultation         ├─ Error handling
        └─ Tenant isolation    ├─ Laboratory           ├─ Security
                               ├─ Pharmacy             ├─ Observability
                               ├─ Billing              ├─ Storage
                               ├─ Chat                 ├─ Notifications
                               ├─ Dashboard            └─ Backup
                               └─ ...

                    ┌───────────────┴────────────────┐
                    │                                │
                    ▼                                ▼
              PostgreSQL                          Redis
          Authoritative data             Cache / revocation /
                                         rate limiting / realtime /
                                         Celery infrastructure

                    ▲
                    │
              Future Flutter Client
                    │
                 SQLite
          Local cache / offline /
          synchronization control
```

### Source-of-Truth Model

PostgreSQL is the authoritative application data store.

Redis is infrastructure for ephemeral or coordination-oriented workloads such as:

```text
JWT revocation state
Rate limiting
Celery broker/result backend
Socket.IO message queue
Observability aggregates
```

Flutter SQLite is reserved for client-side cache, offline state, and synchronization control data. It is not the authoritative medical-record database.

## Core Technology Stack

```text
Python
Flask
Flask-SQLAlchemy
SQLAlchemy 2.x
Flask-Migrate / Alembic
PostgreSQL
Redis
Celery
Flask-SocketIO
Flask-JWT-Extended
Flask-CORS
Flask-Limiter
Pydantic v2
Werkzeug
Requests
Pillow
QR Code utilities
OpenAI integration
Stripe integration
Pytest
Locust
psutil
```

## Core Platform Services

The current core layer includes:

```text
app/core/
├── api
├── audit
├── auth
├── backup
├── cache
├── compliance
├── enums
├── files
├── integrations
├── notifications
├── observability
├── security
├── storage
├── utils
├── error_handlers.py
├── exceptions.py
└── web_routes.py
```

The core layer contains reusable infrastructure and cross-cutting controls rather than module-specific business workflows.

## Application Modules

The current application modules are:

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
Settings
Asset Control
Dashboard
Advanced Access Control
Internal Clinical Chat
Profile
```

Profile is an aggregation layer over user, staff, and clinic information and is not a separate database entity.

## Authentication and Authorization

Authentication supports:

```text
JWT access tokens
JWT refresh tokens
Google OAuth
Token revocation
Token-version invalidation
Role claims
Account activity checks
```

The standard JWT lifetime configuration is:

```text
Access token   : 1 hour
Refresh token  : 30 days
```

The application does not trust client-supplied tenant or actor identifiers for protected workflows. Authenticated user and staff context is resolved server-side.

## Role-Based Access Control

The role model is authoritative through the role enum and the persisted user role.

Current role values include:

```text
doctor
nurse
patient
pharmacist
lab_technician
receptionist
admin
accountant
paramedic
other
driver
emt
ambulance_dispatcher
ambulance_coordinator
```

Administrative authority is explicitly bounded.

Regular administrators are restricted from managing higher-authority administrator accounts or assigning privileges outside their authority.

Super administrators have broader cross-clinic authority but cannot modify another super administrator or assign super-administrator privileges.

## Multi-Clinic Tenant Isolation

Clinic scope is enforced server-side.

Protected operations resolve clinic context from the authenticated user/staff relationship rather than accepting arbitrary clinic identifiers from the client.

Tenant isolation is applied across services, routes, and data access paths.

## API Versioning

The canonical public API namespace is:

```text
/api/v1/
```

The URL path is the source of truth for API version selection.

Supported version:

```text
v1
```

Unsupported versions such as:

```text
/api/v2/...
/api/v99/...
```

return HTTP 404 with:

```text
api_version_not_supported
```

The API version is not selected through JWT claims or client-controlled version overrides.

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
GET  /api/v1/dashboard/...
```

## Validation and Error Handling

Request validation uses Pydantic v2 with strict typing in hardened request contracts.

The core domain error model distinguishes:

```text
400  Domain Error
402  Insufficient Credits
404  Not Found
409  Conflict
422  Validation Error
```

The application returns structured error responses instead of exposing arbitrary internal exception details through normal domain failures.

## Database Integrity

Database access follows SQLAlchemy 2.x patterns.

The project uses:

```text
db.select(...)
db.session.execute(...)
db.session.get(...)
Transactional commit/rollback boundaries
Deterministic ordering
Pagination
State/lifecycle checks
Historical-read semantics
Database-aware locking where required
```

PostgreSQL is the production source of truth.

Alembic/Flask-Migrate manages schema evolution.

## Auditability and Security

The platform is designed to protect sensitive healthcare workflows through multiple independent controls:

```text
Authentication
Authorization
Role boundaries
Tenant isolation
IDOR protection
Input validation
Transactional integrity
Audit logging
Token revocation
Token-version invalidation
Rate limiting
Security service checks
Observability
```

Audit logging is an accountability mechanism and is intentionally separate from database backup and disaster recovery.

## Data Storage and Files

The application database stores authoritative structured healthcare data in PostgreSQL.

Uploaded files are handled by the storage layer. The current storage implementation supports a configurable filesystem root through:

```text
STORAGE_ROOT
STORAGE_PUBLIC_BASE_URL
```

Profile images are persisted as files, while database records retain internal storage references.

This creates two distinct recovery domains that must eventually be protected:

```text
1. PostgreSQL database data
2. Filesystem/object-backed application files
```

## Backup and Disaster Recovery

A dedicated backup package now exists under:

```text
app/core/backup/
```

Current scaffold:

```text
app/core/backup/
├── __init__.py
├── backup_service.py
├── database_backup.py
├── file_backup.py
├── backup_storage.py
├── backup_retention.py
├── restore_service.py
├── backup_verification.py
└── backup_tasks.py
```

The current files are structural placeholders. Backup execution has not yet been implemented.

The intended backup architecture will separate:

```text
Database backup
File/storage backup
Backup destination
Retention policy
Restore orchestration
Backup verification
Scheduled backup execution
```

Future production backup capabilities are expected to include automated PostgreSQL backups, durable off-site storage, retention policy, integrity verification, restore testing, and disaster-recovery procedures.

No production backup, point-in-time recovery, recovery-time objective, or recovery-point objective should be inferred from the current scaffold until those capabilities are implemented and verified.

## Realtime Communication and Clinical Chat

Socket.IO provides realtime communication.

Internal Clinical Chat is clinic-scoped and built around authenticated staff/user context.

The current chat foundation includes:

```text
Conversations
Conversation participants
Messages
Attachments
Mentions
Pins
Reactions
Read receipts
Message revisions
Chat outbox/events
Chat usage
Socket.IO realtime communication
Retention controls
Policy/security enforcement
```

Chat policy is resolved through a layered rule system with hard limits, feature flags, and clinic-specific settings.

Current policy controls include:

```text
Maximum message length
Maximum group participants
Maximum attachment size
Allowed attachment types
Direct messaging
Message edit window
Message delete window
Retention period
Reactions
Mentions
Voice messages
Conversation creation
Department restrictions
Feature availability
```

Hard ceilings are enforced independently of clinic-level configuration.

## Background Processing

Celery handles background and scheduled work.

Redis is currently used as the broker/result backend.

Current application scheduling includes workflows such as:

```text
Appointment reminders
Overdue invoice processing
Monthly AI usage resets
```

Start a worker:

```powershell
celery -A celery_worker.celery worker --loglevel=info
```

Start Beat:

```powershell
celery -A celery_worker.celery beat --loglevel=info
```

Backup scheduling is not yet connected to Celery; the backup task module is currently scaffolded for the future implementation.

## Observability

The application contains a dedicated observability layer covering:

```text
Request metrics
PostgreSQL/database metrics
Redis metrics
Celery metrics
Socket.IO metrics
System metrics
Aggregated performance metrics
```

These metrics are intended to provide visibility into both application behavior and supporting infrastructure.

Focused observability verification currently covers request, database, Redis, Celery, Socket.IO, and system metric components.

## Testing

The project maintains a large isolated Pytest suite.

Test applications use the testing configuration with:

```text
Isolated SQLite database
Dedicated test Redis
Application-factory setup
Database creation/teardown
Module-specific fixtures
```

Run the complete suite:

```powershell
pytest -q
```

Run core API tests:

```powershell
pytest app/tests/core/api -q
```

Module-level suites can be executed directly from their respective test directories.

## Performance and Load Testing

Performance testing is separated from resilience testing.

The performance framework is located under:

```text
load_tests/
```

It uses Locust plus project-specific helpers and result validation.

The framework is designed to measure:

```text
API latency
Throughput
Database query behavior
Database query count
Redis behavior
Service-level performance
Module-level workloads
System-wide mixed workloads
Performance regressions
```

The repository contains module-oriented scenarios across the major application domains together with a system-mixed workload.

Benchmark artifacts include structured JSON results and Locust CSV result files.

Load-test validity is treated as a data-integrity problem as well as a performance problem. Result validation uses run identifiers, server logs, workload filtering, zero-failure checks, successful Locust termination, and result-artifact validation.

### Current Load-Test Phase

The dedicated performance/load-testing phase is considered complete for the current engineering cycle.

Future large-scale capacity testing is a separate activity and should use distributed load generators rather than relying on a development workstation.

Concurrency testing and record/data-volume testing are distinct concerns.

No large-scale production-capacity claim is derived from the current local development environment.

## Resilience Testing

A dedicated resilience framework has been scaffolded under:

```text
load_tests/resilience/
├── README.md
├── common/
│   ├── network.py
│   ├── socketio.py
│   ├── assertions.py
│   └── results.py
├── profiles/
│   ├── slow_2g.py
│   ├── slow_3g.py
│   ├── high_latency.py
│   ├── jitter.py
│   ├── packet_loss.py
│   ├── bandwidth_limited.py
│   └── intermittent.py
├── scenarios/
│   ├── http_resilience.py
│   ├── socketio_resilience.py
│   ├── auth_resilience.py
│   ├── chat_resilience.py
│   └── sync_resilience.py
├── runners/
│   ├── resilience.py
│   └── resilience_report.py
└── results/
```

The resilience package is currently a scaffold only. Scenario and network-degradation behavior has not yet been implemented.

The intended resilience phase will cover:

```text
Slow internet
High latency
Jitter
Packet loss
Bandwidth limitation
Intermittent connectivity
HTTP interruption
Authentication interruption
Socket.IO disconnect/reconnect
Chat recovery
Offline Flutter behavior
SQLite synchronization
Redis degradation
Celery degradation
Recovery behavior
Duplicate protection
Data-integrity protection
```

Performance testing and resilience testing remain separate so that degraded-network behavior does not contaminate clean performance baselines.

## Flutter and Offline Architecture

Flutter is the planned client/UI layer.

The backend remains authoritative:

```text
Flutter
   |
   | API v1 / Socket.IO
   v
Flask Backend
   |
   +---- PostgreSQL
   +---- Redis
   +---- Celery
```

Local SQLite is intended for:

```text
Cache
Offline state
Synchronization control data
Pending offline operations
```

The eventual synchronization design is expected to include:

```text
Offline queue
Incremental synchronization
Sync cursors
Record versions
Timestamps
Retry/backoff
Idempotency
Deduplication
Conflict resolution
Tombstones
last_purged_at
```

There is currently no claim that full offline synchronization has been implemented.

## AI Integration

The AI module exposes provider-backed clinical utility functionality, including:

```text
POST /api/v1/ai/drug-interactions
```

The application isolates provider credentials/configuration from request payloads.

AI workloads in the load-testing framework are treated separately from ordinary application performance because external provider availability, rate limits, and billing/quota conditions can affect benchmark results.

## Configuration

Configuration is environment-driven.

Important infrastructure configuration includes:

```text
DATABASE_URL
REDIS_URL
SECRET_KEY
JWT_SECRET_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
STORAGE_ROOT
STORAGE_PUBLIC_BASE_URL
INTEGRATION_ENCRYPTION_KEY
```

Provider-specific credentials must be supplied through the deployment environment and must not be committed to source control.

The repository has previously undergone secret-cleanup hardening after a credential was detected in source history. Credentials should be treated as compromised whenever they are exposed and must be rotated or revoked outside the repository.

## Production Entry Points

Development execution uses:

```text
run.py
```

The WSGI application entry point is:

```text
wsgi:app
```

Production deployment should use an appropriate production WSGI/Socket.IO-compatible serving architecture rather than Flask's development server.

## Development

Install dependencies from:

```text
requirements.txt
```

Create the required environment variables for the selected environment.

Development execution:

```powershell
python run.py
```

Testing:

```powershell
pytest -q
```

The project also provides the Celery worker and Beat entry points described above.

## Repository Structure

The current repository is organized around:

```text
clinic-system-pro/
├── app/
│   ├── core/
│   └── modules/
├── load_tests/
│   ├── common/
│   ├── scenarios/
│   └── resilience/
├── migrations/
├── generated_reports/
├── training/
├── requirements.txt
├── run.py
├── wsgi.py
├── celery_worker.py
├── README.md
└── verify_benchmark_dataset.py
```

## Engineering Principles

The project is developed around the following principles:

```text
Server-side authority
Explicit authorization
Strict tenant isolation
Validated inputs
Transactional business operations
Auditable state changes
Deterministic data access
Modern SQLAlchemy
Separate source of truth from cache
Performance testing before optimization
Resilience testing separate from performance testing
Recovery mechanisms verified independently
Infrastructure-aware production design
```

## Current Roadmap

The engineering roadmap is intentionally staged.

### Current Focus

```text
Resilience and recovery engineering
```

### Next Major Capabilities

```text
1. Implement resilience testing
2. Implement backup execution
3. Implement restore and backup verification
4. Define operational retention and recovery policy
5. Production readiness review
6. Future distributed scalability validation
7. Flutter offline/synchronization implementation
8. Final Rust White Glove Migration
```

The Rust White Glove Migration is intentionally the final backend migration phase and is not a substitute for application-level recovery or resilience controls.

## Important Status Boundary

The project distinguishes between:

```text
Implemented
Hardened
Verified
Scaffolded
Planned
```

A scaffolded directory or module is not treated as a completed production capability.

In particular, the following are currently scaffolded rather than fully implemented:

```text
Backup execution
Backup storage integration
Backup retention automation
Restore orchestration
Backup verification
Resilience network profiles
Resilience scenarios
Offline synchronization
```

That distinction is maintained intentionally so the repository documentation does not overstate the operational maturity of unfinished components.
