# Migration Readiness

## Purpose

This document defines the production migration-readiness contract for
Clinic System Pro v5.

## Historical Phase 6 Repository State

The current Git revision is:

`5957367208670df64cc2116eb0dd48620021e9c0`

The current database migration revision is:

`4d205e66d288`

The repository currently reports a single migration head:

`4d205e66d288`

Migration management uses Flask-Migrate and Alembic.

The latest verified migration state also reports:

`flask db check` → `No new upgrade operations detected`

## Phase 6 Migration Bootstrap Verification

The production-like backend environment executed a clean migration bootstrap
from an empty PostgreSQL database to the current migration head:

- starting revision: empty database
- resulting migration revision: `4d205e66d288`
- migration heads: single head
- public tables: 75
- legacy `messages` table: absent
- live application database state remained isolated from the disposable drill
- migration bootstrap evidence is retained in
  `artifacts/production-readiness/phase6/migration-bootstrap-be32576.txt`

This verifies the repository migration chain and production-like bootstrap
path against the immutable Phase 6 application image. It does not constitute
an actual production database migration.

## Production Requirements

Production uses PostgreSQL.

Production migrations must be executed through the repository's
Flask-Migrate/Alembic workflow.

The application database remains the authoritative source of truth.

## Pre-Migration Verification

Before a production migration:

1. Identify the exact application release.
2. Verify the migration revision and migration heads.
3. Verify the target database is PostgreSQL.
4. Confirm a current recoverable backup exists.
5. Review migration SQL and expected locking behavior.
6. Verify application compatibility with the target revision.
7. Confirm the deployment and rollback plan.
8. Record the approved change and operator evidence.

## Migration Execution

Migrations must be executed using the approved deployment environment.

Migration output must be retained as deployment evidence.

Concurrent or conflicting migration execution must be prevented.

A migration must not be considered successful merely because the command
returns successfully. The resulting revision and application health must
also be verified.

## Failure Handling

If a migration fails:

- preserve the migration error evidence
- determine whether the database transaction rolled back
- do not manually modify migration history to hide a failure
- assess whether application rollback is safe
- use the approved recovery or restore procedure when data state cannot
  safely be rolled back

Application rollback and database restoration are separate recovery actions.

## Post-Migration Verification

Verify:

- expected migration revision
- application startup
- readiness endpoint
- database connectivity
- Redis connectivity
- authentication
- authorization
- critical clinical workflows
- audit behavior
- background processing where applicable

## Environment-Dependent Gate

The Phase 6 production-like migration bootstrap has been executed and passed.

Actual production database migration remains unexecuted and requires the
approved production deployment process, release artifact, recoverable backup,
operator evidence, and post-migration verification.

This document therefore establishes the migration-readiness contract and
records the completed production-like bootstrap without claiming that a
production migration has been executed.

## Current Migration State

The earlier Phase 6 migration bootstrap is historical evidence.

The current Alembic head is:

``c8e4f1a9d2b7``

This head is the encryption key-version migration:
``backend/migrations/versions/c8e4f1a9d2b7_add_encryption_key_version.py``

Verified migration sequence:

- previous head: ``d7f4a6b91c22``
- upgrade to: ``c8e4f1a9d2b7``
- downgrade: verified
- re-upgrade: verified
- Alembic head count: single head

The current migration chain is part of the encryption/security hardening state.
Actual production migration remains an infrastructure-dependent release operation.
