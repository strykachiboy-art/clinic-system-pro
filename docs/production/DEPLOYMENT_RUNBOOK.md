# Deployment Runbook

## Purpose

This document defines the production deployment contract for Clinic
System Pro v5.

It describes the required deployment behavior without claiming that
production deployment has already occurred.

## Application

The production WSGI entry point is:

`backend/wsgi.py`

`backend/wsgi.py` passes `FLASK_ENV` to the application factory and uses
`production` when that environment variable is absent.

Production configuration fails closed when required production settings
are missing.

## Background Workers

Celery uses:

`backend/celery_worker.py`

The worker requires the production environment configuration when deployed
for production operation.

The worker uses the configured Redis broker and result backend and runs
tasks inside the Flask application context.

## Redis

Redis provides application infrastructure including:

- token revocation
- rate-limit storage
- Celery broker/result transport
- Socket.IO message queue

Redis availability must therefore be verified before accepting production
traffic.

## PostgreSQL

PostgreSQL is the production application datastore and authoritative
source of truth.

Production startup requires a PostgreSQL database URL.

Migration readiness must be verified before release.

## Socket.IO

Flask-SocketIO is part of the backend runtime.

Production deployment must preserve the configured Redis message queue and
same-origin/CORS security policy.

Socket.IO connectivity must be validated in the production-like
environment.

## Network and TLS

TLS termination and reverse-proxy behavior are deployment-environment
responsibilities.

The approved TLS procedure is documented in:

`docs/security/SECURITY_OPERATIONS.md`

Production deployment must verify:

- HTTPS
- certificate validity
- hostname coverage
- certificate chain
- reverse-proxy/application connectivity
- health endpoints
- Socket.IO connectivity where applicable

## Startup

Before accepting traffic:

1. Load the approved production configuration.
2. Verify required secrets are available through approved secret
   management.
3. Start the application runtime.
4. Start required background workers.
5. Verify database connectivity.
6. Verify Redis connectivity.
7. Verify readiness.
8. Verify observability.
9. Execute deployment smoke tests.

## Shutdown

Production shutdown must be graceful.

The deployment environment must provide a controlled mechanism for:

- stopping new traffic
- allowing or terminating in-flight requests according to the approved
  policy
- stopping background workers safely
- allowing queued work to remain recoverable
- releasing application resources

Actual shutdown behavior must be verified in the production-like
environment.

## Deployment Order

A controlled deployment should establish:

1. approved release artifact
2. approved configuration and secrets
3. infrastructure/dependency availability
4. database migration state
5. application runtime
6. Celery workers
7. Socket.IO connectivity
8. health/readiness
9. smoke tests
10. traffic acceptance

## Rollback

Use:

`docs/production/ROLLBACK_PROCEDURE.md`

Rollback must be based on an identifiable known-good release and must
consider database compatibility.

## Evidence

Record:

- release identifier
- source revision
- artifact identity
- migration revision
- deployment timestamp
- environment
- configuration verification
- health/readiness results
- smoke-test results
- rollback status if applicable

Never record secret values.

## Environment-Dependent Gate

Actual deployment execution, reverse-proxy/TLS validation, startup and
shutdown execution, and post-deployment validation remain pending the
Phase 6 production-like environment.
