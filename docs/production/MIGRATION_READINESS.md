# Migration Readiness

## Purpose

This document defines the production migration-readiness contract for
Clinic System Pro v5.

## Current Repository State

The current Git revision is:

`0ee5756ccb39ef18fe41dca3052de0727f5a7192`

The current database migration revision is:

`4d205e66d288`

The repository currently reports a single migration head:

`4d205e66d288`

Migration management uses Flask-Migrate and Alembic.

The latest verified migration state also reports:

`flask db check` → `No new upgrade operations detected`

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

Actual production-like migration execution remains pending the Phase 6
environment.

This document therefore establishes the readiness contract; it does not
claim that a production migration has been executed.
