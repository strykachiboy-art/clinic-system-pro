# Clinic System Pro v5

Clinic System Pro v5 is a modular, multi-clinic healthcare management backend built with Flask, SQLAlchemy 2.x, PostgreSQL, Redis, Celery, Flask-SocketIO, JWT authentication, Pydantic v2, and a versioned API architecture.

The platform is designed around server-side authorization, strict tenant isolation, transactional business services, auditability, clinical safety, emergency access controls, observability, backup and recovery, resilience testing, and a future Flutter client layer.

---

## Current Project Status

**Status date:** September 25, 2026

The project has completed its major backend architecture, security hardening, core feature, resilience, and recovery engineering milestones.

### Completed and hardened

```text
Application factory architecture
Authentication and identity
JWT access and refresh tokens
Google OAuth
Token revocation
Token-version invalidation
Role-based access control
Multi-clinic tenant isolation
IDOR protection
Strict request validation
Pydantic v2 contracts
Transactional service boundaries
Centralized domain error handling
Pagination
Deterministic ordering
Lifecycle/state validation
Historical-read semantics
Audit logging
Modern SQLAlchemy 2.x usage
Migration cleanup
Database hardening
Route/schema integration hardening
Service and route test hardening
Configuration and integration hardening

Settings
Asset Control / Asset Management
Dashboard
Advanced Access Control
Internal Clinical Chat

Emergency Clinical Access
Consent Guard / Break-Glass controls

Clinical Safety
Clinical Rule Engine
Medication Safety Evaluation
Clinical Alerts
Alert acknowledgement and override controls

Database backup
File backup
Backup storage handling
Backup retention
Backup verification
Database restore
File restore
Restore orchestration
Controlled restore drill

Request observability
Database observability
Redis observability
Celery observability
Socket.IO observability
System observability

Controlled Locust load-testing infrastructure
Resilience testing infrastructure
Network degradation profiles
HTTP resilience testing
Authentication resilience testing
Socket.IO resilience testing
Chat resilience testing
Redis/Celery resilience testing
```

### Current verified checkpoints

```text
Clinical Safety suite:
134 passed

Recorded resilience all-scenario run:
47 passed
0 failed
0 skipped

Recorded restore drill:
success = true
post-restore verification = true
authentication invalidation = true
outbox recovery = true
```

The repository currently contains **no Feedback feature implementation**. Feedback is the next planned application feature.

---

# Architecture

Clinic System Pro follows an application-factory architecture with a separation between:

```text
Client interfaces
API / realtime transport
Authentication and authorization
Business modules
Cross-cutting infrastructure
Persistence
Background processing
Observability
Recovery
```

```text
                              Clients
                       ┌─────────┴─────────┐
                       │                   │
                  HTTP / API v1        Socket.IO
                       │                   │
                       └─────────┬─────────┘
                                 │
                         Flask Application
                                 │
       ┌─────────────────────────┼─────────────────────────┐
       │                         │                         │
 Authentication &          Business Modules        Cross-Cutting Core
 Authorization                                       Infrastructure
       │                         │                         │
       ├─ JWT                    ├─ Patient             ├─ Validation
       ├─ OAuth                  ├─ Appointment         ├─ Audit
       ├─ RBAC                   ├─ Consultation        ├─ Security
       ├─ Tenant isolation       ├─ Laboratory          ├─ Observability
       └─ Access controls        ├─ Pharmacy            ├─ Notifications
                                 ├─ Prescription        ├─ Storage
                                 ├─ Billing             ├─ Backup
                                 ├─ Chat                ├─ Emergency Access
                                 ├─ Dashboard           └─ Clinical Safety
                                 ├─ Reports
                                 └─ ...
                                    │
                                    ▼
                             PostgreSQL
                         Authoritative data
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                        Redis              Celery
                  Cache / revocation   Background tasks /
                  rate limiting        scheduled work
                  Socket.IO support

                                 ▲
                                 │
                          Future Flutter Client
                                 │
                              SQLite
                     Local cache / offline /
                    synchronization control
```

---

# Source-of-Truth Model

PostgreSQL is the authoritative application data store.

Redis is infrastructure for ephemeral or coordination-oriented workloads such as:

```text
JWT revocation state
Rate limiting
Caching
Celery broker/result infrastructure
Socket.IO coordination
Realtime support
```

Flutter SQLite is intended for client-side state only.

SQLite is not the authoritative medical-record database.

The backend remains authoritative for:

```text
Authentication
Authorization
Tenant isolation
Validation
Business rules
Clinical safety
Audit logging
Persistence
Conflict handling
```

---

# Core Technology Stack

```text
Python
Flask
Flask-SQLAlchemy
SQLAlchemy 2.x
Flask-Migrate
Alembic
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
QRCode utilities
OpenAI integration
Stripe integration
Pytest
Locust
psutil
```

The primary dependency manifest is:

```text
requirements.txt
```

---

# Core Platform Structure

The repository currently contains the following major core packages:

```text
app/core/
├── api
├── audit
├── auth
├── backup
├── cache
├── clinical_safety
├── compliance
├── emergency_access
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

The core layer contains infrastructure and cross-cutting controls rather than ordinary domain workflows.

---

# Application Modules

The current application modules are:

```text
app/modules/
├── access_control
├── ai
├── ambulance
├── appointment
├── asset_control
├── billing
├── chat
├── clinic
├── consultation
├── dashboard
├── hie
├── inventory
├── lab
├── patient
├── pharmacy
├── prescription
├── profile
├── reports
├── settings
├── staff
└── ward
```

The major application domains therefore include:

```text
Authentication / Identity
User
Staff
Clinic
Patient
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
Settings
Asset Control
Dashboard
Advanced Access Control
Internal Clinical Chat
Profile
```

Profile is an aggregation layer over User, Staff, and Clinic information.

Profile is not a standalone database entity.

---

# Authentication

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

Standard token lifetimes are configured around:

```text
Access token  : approximately 1 hour
Refresh token : approximately 30 days
```

Protected requests resolve the authenticated user from the server-side JWT identity.

Client requests are not trusted to provide arbitrary actor identities for protected workflows.

---

# Authorization and RBAC

The persisted user role and application role enum are authoritative for access control.

Current roles include:

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

A super-administrator authority exists separately from normal administrator authority.

Administrative rules include:

```text
Regular administrators cannot elevate another user to administrator authority without satisfying the access-control rules.

Regular administrators cannot modify higher-authority administrator accounts.

Super administrators have cross-clinic authority where explicitly permitted.

A super administrator cannot modify another super administrator.

A super administrator cannot assign super-administrator privileges.
```

The access-control layer is implemented under:

```text
app/modules/access_control/
```

---

# Multi-Clinic Tenant Isolation

Clinic scope is resolved server-side.

Protected business workflows derive clinic context from the authenticated user/staff relationship instead of trusting a client-supplied clinic identifier.

Tenant isolation is enforced throughout:

```text
Routes
Services
Database access
Authorization
Clinical workflows
Chat
Emergency access
Clinical safety
Reporting
```

Cross-clinic resource access is rejected.

---

# API Versioning

The canonical API namespace is:

```text
/api/v1/
```

The URL path is the source of truth for API version selection.

Current supported version:

```text
v1
```

Unsupported versions are rejected through the API version boundary.

Example:

```text
/api/v2/...
/api/v99/...
```

are not treated as valid supported API versions.

API version selection is not controlled through JWT claims or arbitrary client version overrides.

Example API paths:

```text
POST /api/v1/auth/login
POST /api/v1/auth/register

GET  /api/v1/patients
GET  /api/v1/appointments

GET  /api/v1/pharmacy/drugs
POST /api/v1/prescriptions

GET  /api/v1/reports
GET  /api/v1/dashboard/...

GET  /api/v1/chat/...

GET  /api/v1/clinical-safety/rules
GET  /api/v1/clinical-safety/alerts
```

---

# Validation and Error Handling

Request validation uses Pydantic v2.

Hardened request contracts use strict types where appropriate and reject unexpected fields.

The core domain error model distinguishes:

```text
400  Domain Error
402  Insufficient Credits
404  Not Found
409  Conflict
422  Validation Error
```

The application uses centralized error handling so ordinary domain failures are returned as structured API responses instead of exposing arbitrary internal exceptions.

---

# Database Architecture

Database access follows SQLAlchemy 2.x patterns.

The project consistently uses modern patterns including:

```python
db.select(...)
db.session.execute(...)
db.session.get(...)
```

Database hardening includes:

```text
Transactions
Commit/rollback boundaries
Deterministic ordering
Pagination
Lifecycle validation
Historical-read semantics
Tenant scoping
Database-aware locking where required
```

PostgreSQL is the production persistence source of truth.

Alembic / Flask-Migrate manages schema evolution.

---

# Auditability

Audit logging is implemented as a dedicated cross-cutting subsystem.

Sensitive operations are designed to preserve accountability through:

```text
Authenticated actor identity
Tenant context
Action/event recording
Resource identification
Change tracking
Administrative accountability
Clinical accountability
```

Audit logging is distinct from:

```text
Backup
Restore
Recovery
Observability
```

These concerns complement each other but are not interchangeable.

---

# Security Model

The platform uses multiple independent security controls:

```text
Authentication
Authorization
RBAC
Tenant isolation
IDOR protection
Input validation
Transactional boundaries
Audit logging
Token revocation
Token-version invalidation
Rate limiting
Security services
Clinical safety controls
Emergency access controls
Observability
```

Sensitive healthcare workflows are deliberately protected by layered controls rather than relying on a single security mechanism.

---

# Emergency Clinical Access

Emergency access is implemented under:

```text
app/core/emergency_access/
```

The current emergency-access layer includes:

```text
Emergency access records
Consent Guard
Emergency access service
Consent Guard service
Protected routes
Request schemas
Audit-aware emergency access workflows
```

Emergency access provides a controlled **Break-Glass** mechanism for exceptional access to protected clinical information.

The design separates:

```text
Authorization to access protected information
```

from:

```text
Whether a clinical action is medically or operationally safe
```

Emergency access does not bypass Clinical Safety rules.

---

# Clinical Safety

Clinical Safety is implemented under:

```text
app/core/clinical_safety/
```

The subsystem includes:

```text
Clinical rules
Clinical rule versions
Rule evaluation
Rule resolution
Medication safety
Clinical alerts
Alert acknowledgement
Alert override handling
Alert resolution
Clinical safety routes
```

Current clinical rule types include:

```text
DRUG_INTERACTION
ALLERGY_CONFLICT
CONTRAINDICATION
MAX_DOSE
MIN_DOSE
AGE_RESTRICTION
WEIGHT_RESTRICTION
PREGNANCY_RESTRICTION
DUPLICATE_THERAPY
THERAPEUTIC_DUPLICATION
LAB_CONFLICT
RENAL_FUNCTION
HEPATIC_FUNCTION
DIAGNOSIS_CONFLICT
FREQUENCY_LIMIT
DURATION_LIMIT
PATIENT_SPECIFIC_RESTRICTION
```

Rule severities include:

```text
INFO
LOW
MODERATE
HIGH
CRITICAL
```

Rule actions include:

```text
INFORM
ALERT
REQUIRE_ACKNOWLEDGEMENT
REQUIRE_JUSTIFICATION
BLOCK
```

Evaluation outcomes include:

```text
SAFE
INFORMATION
WARNING
ACKNOWLEDGEMENT_REQUIRED
JUSTIFICATION_REQUIRED
BLOCKED
```

---

## Clinical Safety Rule Hierarchy

Rules are resolved through layered scope and effective-version logic.

The architecture supports:

```text
Global rules
Clinic rules
Department rules
Patient-specific context
```

System hard-safety rules form an immutable safety floor.

Hard rules:

```text
Are global
Cannot be weakened
Are controlled at super-admin level
Must use BLOCK behavior
Cannot be bypassed through ordinary acknowledgement
```

Rule versions become immutable once used in clinical evaluation.

Updating a rule creates a new version rather than mutating the historical rule definition.

---

# Medication Safety

Medication safety reuses the existing prescription and drug domain rather than introducing duplicate medication models.

Existing medication interaction data is reused through the existing prescription/drug infrastructure.

Medication safety evaluation combines:

```text
Drug interaction checks
Clinical rule evaluation
Existing prescription context
Patient/clinical context where available
```

The resulting safety outcome is aggregated deterministically.

---

# Clinical Alerts

Clinical alerts persist actual safety events.

Alerts support:

```text
Deduplication
Open state
Acknowledgement
Override
Resolution
Expiration
Auditability
Source/context tracking
```

Critical hard-rule alerts cannot be overridden.

Acknowledgement is not equivalent to permission to proceed.

---

# Internal Clinical Chat

Internal Clinical Chat is implemented under:

```text
app/modules/chat/
```

The chat subsystem includes:

```text
Conversations
Conversation participants
Messages
Message attachments
Mentions
Pins
Reactions
Read receipts
Message revisions
Reply support
Chat outbox
Chat usage
Message search
Retention
Policy enforcement
Security enforcement
Socket.IO realtime communication
Celery/outbox processing
```

The chat architecture supports:

```text
Direct messages
Group conversations
Clinic-scoped staff communication
Department-aware controls
Unread/read state
Message lifecycle controls
Realtime updates
```

---

# Chat Policy and Rule Engine

Chat configuration is resolved through layered policy rules.

The design supports:

```text
Hard limits
Feature flags
Clinic settings
Default configuration
```

Current controls include:

```text
Maximum message length
Maximum group participants
Maximum attachment size
Attachment type restrictions
Direct messaging
Message edit window
Message deletion window
Retention period
Reactions
Mentions
Voice messages
Conversation creation
Department restrictions
Feature availability
```

Hard ceilings cannot be weakened by ordinary clinic configuration.

---

# Background Processing

Celery is used for background and scheduled workloads.

Redis provides the broker/result infrastructure.

Current application background workflows include areas such as:

```text
Appointment reminders
Overdue invoice processing
AI usage resets
Chat outbox processing
Notification/background processing
```

Worker startup:

```powershell
celery -A celery_worker.celery worker --loglevel=info
```

Beat startup:

```powershell
celery -A celery_worker.celery beat --loglevel=info
```

---

# Notifications

Notifications are implemented as a cross-cutting core subsystem.

The notification layer integrates with application workflows and background processing.

Notification infrastructure supports the platform's asynchronous and user-facing event workflows without coupling individual business modules directly to transport details.

---

# Dashboard

The Dashboard module provides role-aware aggregation and reporting views for areas such as:

```text
Clinical operations
Finance
Management
Operations
Patients
Super administration
Dashboard widgets
```

The dashboard is implemented under:

```text
app/modules/dashboard/
```

---

# Reports

Reports are implemented under:

```text
app/modules/reports/
```

The reporting layer supports application-level reporting workflows and structured report schemas.

Reporting remains separate from raw database access so authorization, tenant isolation, and business semantics can remain centralized.

---

# Settings

Settings are implemented under:

```text
app/modules/settings/
```

Current settings infrastructure covers clinic settings and integration/provider configuration.

Provider configuration includes areas such as:

```text
Paystack
Flutterwave
Email
SMS-related configuration
Push notifications
```

Sensitive integration configuration is designed to avoid plaintext exposure in logs and normal API responses.

---

# Asset Control

Asset Control is implemented under:

```text
app/modules/asset_control/
```

Current asset areas include:

```text
Assets
Assignments
Maintenance
History
Lifecycle tracking
```

Asset operations are tenant-scoped and use authenticated server-side context.

---

# AI Integration

AI functionality is implemented under:

```text
app/modules/ai/
```

The AI subsystem provides provider-backed clinical utility workflows.

A current example endpoint is:

```text
POST /api/v1/ai/drug-interactions
```

AI provider credentials are configuration concerns and are not intended to be supplied as arbitrary request data.

AI workloads are separated from ordinary local performance benchmarks because external provider latency, quotas, rate limits, and availability can influence measurements.

---

# Billing and Payments

Billing is implemented under:

```text
app/modules/billing/
```

Payment-provider integration includes gateway abstractions for:

```text
Paystack
Flutterwave
Stripe
```

The billing layer separates provider-specific gateway logic from core billing workflows.

---

# Pharmacy and Prescription

Pharmacy and Prescription are separate application domains:

```text
app/modules/pharmacy/
app/modules/prescription/
```

Prescription workflows integrate with existing:

```text
Drugs
Drug interactions
Medication orders
Prescription items
Clinical safety checks
```

The Clinical Safety subsystem reuses these domains rather than creating duplicate drug models.

---

# Laboratory

Laboratory functionality is implemented under:

```text
app/modules/lab/
```

The module contains:

```text
Lab models
Schemas
Services
Routes
```

Clinical safety can consume laboratory-related context through relevant rule types such as:

```text
LAB_CONFLICT
RENAL_FUNCTION
HEPATIC_FUNCTION
```

---

# Consultation

Consultation workflows are implemented under:

```text
app/modules/consultation/
```

Consultation access is tenant-scoped and integrates with authenticated clinical participants and appointment context where applicable.

---

# Appointment

Appointment workflows are implemented under:

```text
app/modules/appointment/
```

The system applies lifecycle validation and server-side authorization to appointment state changes.

Appointment reminders are handled through background processing.

---

# Ambulance

Ambulance functionality is implemented under:

```text
app/modules/ambulance/
```

The current structure includes:

```text
Ambulance trips
Ambulance vehicles
Vehicle routes
Trip routes
```

---

# HIE

Health Information Exchange functionality is implemented under:

```text
app/modules/hie/
```

The current HIE structure includes provider integration support, including the existing Malaffi provider integration.

---

# Patient

Patient management is implemented under:

```text
app/modules/patient/
```

Patient records are tenant-scoped and protected by authorization and clinical-data access rules.

---

# Ward

Ward functionality is implemented under:

```text
app/modules/ward/
```

The ward domain is part of the broader inpatient/clinical workflow architecture.

---

# Profile

Profile is implemented under:

```text
app/modules/profile/
```

Profile is an aggregation layer combining information from existing entities rather than introducing a new primary profile database model.

---

# Storage and Files

Application file handling is separated from structured PostgreSQL data.

Storage configuration includes:

```text
STORAGE_ROOT
STORAGE_PUBLIC_BASE_URL
```

Profile images and other uploaded artifacts are handled through the storage subsystem.

The system therefore has two important persistence domains:

```text
1. PostgreSQL structured application data
2. Application-managed files/storage
```

Both domains are considered in backup and disaster-recovery workflows.

---

# Backup and Disaster Recovery

Backup and recovery are implemented under:

```text
app/core/backup/
```

Current components include:

```text
backup_service.py
database_backup.py
file_backup.py
backup_storage.py
backup_retention.py
backup_verification.py
restore_service.py
restore_drill.py
backup_tasks.py
```

The backup subsystem is not merely a directory scaffold.

Implemented responsibilities include:

```text
PostgreSQL backup creation
Database backup integrity checks
File backup
Backup storage management
Retention handling
Backup metadata
Checksum verification
Backup verification
Database restore
File restore
Full restore orchestration
Controlled restore drills
Post-restore verification
Authentication invalidation verification
Chat outbox recovery verification
```

---

## Restore Drill Verification

A recorded restore drill exists in:

```text
generated_reports/restore-drill-report.json
```

The recorded drill reports:

```text
success = true
post_restore_verification_completed = true
authentication_invalidated = true
outbox_recovery_completed = true
```

The restored verification environment also recorded:

```text
clinics
users
audit events
chat outbox entries
migration revision
```

The existence of a successful restore drill does not, by itself, establish a contractual production RPO/RTO.

Those values remain deployment and operational policy decisions.

---

# Backup Retention

Backup retention is implemented as a separate responsibility rather than embedding retention assumptions directly into backup creation.

This separation supports:

```text
Retention rules
Controlled cleanup
Backup inventory
Storage management
Operational policy changes
```

---

# Resilience Testing

The repository now contains an implemented resilience-testing framework under:

```text
load_tests/resilience/
```

Current areas include:

```text
Network profiles
HTTP resilience
Authentication resilience
Socket.IO resilience
Chat resilience
Redis/Celery resilience
Synchronization-related resilience
Result reporting
Automated resilience tests
```

Network conditions represented by the framework include:

```text
Slow 2G
Slow 3G
High latency
Jitter
Packet loss
Bandwidth limitation
Intermittent connectivity
```

---

## Recorded Resilience Run

The repository contains:

```text
load_tests/resilience/results/resilience-all-20260923.json
load_tests/resilience/results/resilience-all-20260923.junit.xml
```

Recorded run:

```text
Run ID:
resilience-all-20260923

Passed:
47

Failed:
0

Skipped:
0

Total:
47
```

The recorded scenarios include areas such as:

```text
HTTP recovery
HTTP network degradation
HTTP pagination consistency
Socket.IO reconnect
Socket.IO authorization restoration
Revoked-token rejection after reconnect
Authentication recovery
Login under degraded networks
Token revocation recovery
Chat recovery
Chat outbox retry behavior
Cross-clinic chat isolation
Redis recovery
Celery broker recovery
Duplicate-state protection
```

Resilience testing is intentionally separated from clean performance benchmarking.

---

# Performance and Load Testing

Controlled load-testing infrastructure is implemented under:

```text
load_tests/
```

The performance framework uses Locust and project-specific validation helpers.

The framework is designed to measure:

```text
API latency
Throughput
Database query behavior
Database query counts
Redis behavior
Service performance
Module workloads
System-mixed workloads
Performance regressions
```

The repository contains:

```text
Baseline tooling
Scenario runners
Result validation
Structured benchmark output
Locust CSV results
Database/query tracing utilities
System-mixed workloads
```

Load-test validity is treated as a correctness issue as well as a performance issue.

Validation concerns include:

```text
Run identifiers
Server-side logs
Expected workload filters
Failure counts
Successful Locust termination
Result artifact validity
```

Large-scale production capacity claims are not inferred from development-machine benchmarks.

Distributed capacity testing is a separate future operational exercise.

---

# Observability

The observability layer covers:

```text
HTTP request metrics
Database metrics
Redis metrics
Celery metrics
Socket.IO metrics
System metrics
Aggregated performance metrics
```

Observability exists to make system behavior measurable across both application and supporting infrastructure.

---

# Testing

The project maintains a large Pytest-based test suite.

Tests are organized under:

```text
app/tests/core/
app/tests/modules/
```

Current test coverage includes dedicated suites for:

```text
Authentication
API versioning
Audit
Backup
Clinical Safety
Emergency Access
Notifications
Observability

Access Control
AI
Ambulance
Appointments
Asset Control
Billing
Chat
Clinic
Consultation
Dashboard
HIE
Inventory
Laboratory
Patient
Pharmacy
Prescription
Profile
Reports
Settings
Staff
Ward
```

Run the full test suite:

```powershell
pytest -q
```

Run a focused core suite:

```powershell
pytest app/tests/core/clinical_safety -q
```

Run backup tests:

```powershell
pytest app/tests/core/backup -q
```

Run emergency-access tests:

```powershell
pytest app/tests/core/emergency_access -q
```

Run chat tests:

```powershell
pytest app/tests/modules/chat -q
```

Run dashboard tests:

```powershell
pytest app/tests/modules/dashboard -q
```

Module-specific suites can be executed directly from their respective test directories.

---

# Flutter Client Architecture

Flutter is the planned client/UI layer for web-adjacent mobile workflows.

The backend remains the authoritative system:

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
Pending operations
Synchronization control
Local client state
```

The backend continues to own:

```text
Authentication
RBAC
Tenant isolation
Clinical safety
Validation
Business rules
Audit
Persistence
```

---

# Planned Offline Synchronization

The future Flutter synchronization model is expected to include:

```text
Offline operation queue
Incremental synchronization
Sync cursors
Record versions
Timestamps
Retry and backoff
Idempotency
Deduplication
Conflict resolution
Tombstones
last_purged_at
```

Full offline synchronization should not be considered implemented until the synchronization layer and its recovery behavior are fully developed and verified.

---

# Configuration

Configuration is environment-driven.

Important configuration areas include:

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

Provider-specific credentials must remain outside committed source code.

Secrets should be rotated immediately if they are exposed.

---

# Production Entry Points

Development execution:

```powershell
python run.py
```

WSGI entry point:

```text
wsgi:app
```

The Flask development server is not intended as the production serving architecture.

Production deployment should use an appropriate production WSGI/Socket.IO-compatible deployment model.

---

# Database Migrations

Database schema changes are managed through:

```text
migrations/
```

with Alembic / Flask-Migrate.

The repository contains migration history for the application's evolving schema, including areas such as:

```text
Authentication
Appointments
Chat
Emergency Access
Clinical Safety
Assets
Billing
Notifications
```

Migration integrity is treated as part of deployment safety.

---

# Repository Structure

The current repository is broadly organized as:

```text
clinic-system-pro/
├── app/
│   ├── core/
│   ├── modules/
│   └── tests/
├── generated_reports/
├── load_tests/
│   ├── common/
│   ├── scenarios/
│   └── resilience/
├── migrations/
├── training/
├── requirements.txt
├── run.py
├── wsgi.py
├── celery_worker.py
├── verify_benchmark_dataset.py
└── README.md
```

---

# Engineering Principles

The project is developed around the following principles:

```text
Server-side authority
Explicit authorization
Strict tenant isolation
Least-authority access control
Validated inputs
Transactional business operations
Auditable state changes
Deterministic data access
Modern SQLAlchemy
Source-of-truth separation
Clinical safety before workflow execution
Emergency access without clinical-safety bypass
Performance testing before optimization
Resilience testing separate from performance testing
Backup and restore verification
Recovery-aware architecture
Infrastructure-aware production design
```

---

# Implementation Status Model

Clinic System Pro distinguishes between:

```text
Implemented
Hardened
Verified
Scaffolded
Planned
```

A directory existing in the repository does not automatically mean that a feature is production-ready.

A capability is treated as completed only when its:

```text
Implementation
Integration
Validation
Authorization
Tenant isolation
Error behavior
Audit behavior
Tests
```

are sufficiently verified for its current engineering phase.

---

# Current Milestone

The current completed engineering milestone is:

```text
Clinical Safety + Emergency Access + Backup/Recovery +
Resilience Verification
```

The Clinical Safety suite currently reports:

```text
134 passed
```

The recorded resilience run reports:

```text
47 passed
0 failed
```

The recorded restore drill reports successful post-restore verification.

---

# Next Planned Feature

The next planned application feature is:

```text
Feedback
```

The current repository does not yet contain a Feedback module.

Feedback will therefore be designed as a new first-class capability rather than being retrofitted into an unrelated existing module.

The feature design will follow the same project standards:

```text
Tenant isolation
Authenticated actor context
Strict request schemas
RBAC
Audit logging
Transactional services
Deterministic queries
Pagination
Validation
Route/service separation
Test coverage
API versioning
```

---

# Long-Term Roadmap

The remaining roadmap is intentionally evolutionary.

```text
Current:
Feedback feature

Then:
Feedback hardening and integration

Then:
Reports / Notifications polish where still required

Then:
Performance optimization and regression verification

Then:
Additional distributed capacity validation

Then:
Production readiness review

Then:
Flutter offline/synchronization implementation

Final backend migration:
Rust White Glove Migration
```

The Rust White Glove Migration remains the final backend migration phase.

It is not a replacement for:

```text
Security
Clinical safety
Backup
Recovery
Resilience
Observability
Testing
```

---

# Important Project Boundary

Clinic System Pro is designed as a production-oriented healthcare backend, but repository implementation status must always be distinguished from deployment-specific operational guarantees.

The repository can contain:

```text
Implemented code
Passing tests
Benchmark evidence
Resilience evidence
Restore-drill evidence
```

without automatically establishing:

```text
A production SLA
A contractual RPO
A contractual RTO
Regulatory certification
Production hosting availability
Production-scale capacity
Third-party provider availability
```

Those depend on deployment architecture, operational procedures, infrastructure, contracts, monitoring, security operations, and regulatory requirements.

---

# Development

Install dependencies:

```powershell
pip install -r requirements.txt
```

Set the environment configuration required for the selected environment.

Run the application:

```powershell
python run.py
```

Run tests:

```powershell
pytest -q
```

Run Celery worker:

```powershell
celery -A celery_worker.celery worker --loglevel=info
```

Run Celery Beat:

```powershell
celery -A celery_worker.celery beat --loglevel=info
```

---

# Project Philosophy

Clinic System Pro is being built as an engineering system rather than a collection of CRUD endpoints.

The architecture prioritizes:

```text
Security
Correctness
Tenant isolation
Clinical safety
Auditability
Recoverability
Resilience
Observability
Testability
Performance
Extensibility
```

The intended result is a backend that can support:

```text
Web clients
Flutter/mobile clients
Realtime clinical communication
Multi-clinic deployments
Clinical workflows
Administrative workflows
Financial workflows
Healthcare interoperability
AI-assisted workflows
Offline-capable clients
Enterprise operational controls
```

while preserving server-side authority over sensitive healthcare data and workflows.
