# Rollback Procedure

## Purpose

This procedure defines controlled application and deployment rollback.

Rollback is distinct from database restoration.

## Rollback Triggers

Consider rollback when a deployment causes a verified release-blocking
failure such as:

- application startup failure
- readiness failure
- authentication failure
- authorization regression
- tenant-isolation regression
- critical clinical workflow failure
- sustained infrastructure incompatibility
- severe error-rate or dependency failure

Rollback decisions require the applicable change/deployment authority.

## Required Release Identification

Record:

- deployed application revision
- replacement application revision
- deployment timestamp
- migration revision
- configuration version
- dependency/runtime version information
- relevant incident/change reference

Secret values must never be recorded.

## Application Rollback

Application rollback restores the previously approved application
artifact/version.

Before rollback:

1. Stop further rollout.
2. Preserve logs and deployment evidence.
3. Confirm the target rollback artifact.
4. Determine whether the database schema is compatible with that artifact.
5. Confirm whether configuration changes must also be reversed.
6. Obtain the required rollback approval.

After rollback verify:

- application startup
- readiness
- authentication
- authorization
- tenant isolation
- critical clinical workflows
- background processing
- audit behavior
- observability

## Configuration Rollback

Configuration changes must be reversed only to an approved known-good
configuration.

Secret values must remain in the approved secret-management system.

## Dependency Rollback

Dependency rollback must use a previously verified compatible dependency
set.

The rollback must preserve authentication, transactions, migrations,
Celery, Redis, and Socket.IO behavior.

## Migration Boundary

A database migration must not be assumed reversible merely because the
application version is reversible.

If the previous application version is incompatible with the current
schema, use the approved migration recovery strategy or database restore
procedure.

## Data Restoration

Database restoration is a recovery operation, not an ordinary application
rollback.

Use the approved backup/restore procedure when rollback cannot safely
return the database to the required state.

## Evidence

Record:

- reason for rollback
- approved change reference
- affected release
- rollback release
- migration revision
- verification results
- remaining impact
- incident reference

Never record secrets.

## Environment-Dependent Gate

Rollback execution remains pending the Phase 6 production-like
environment and requires two identifiable release states for meaningful
execution.
