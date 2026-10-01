# Clinic System Pro v5 — Production Evidence Pack

This directory contains the Phase 5 production-readiness evidence pack.

Phase 5 establishes the production-readiness contract and records the
evidence available from the verified backend and controlled operational
checks.

It does not claim that production deployment has occurred.

## Authoritative Existing Evidence

The following documents remain authoritative for areas already covered:

- `docs/security/SECURITY_OPERATIONS.md`
- `docs/security/DEPENDENCY_UPGRADE_POLICY.md`
- `docs/security/BACKUP_RESTORE_DRILL.md`
- `docs/security/COST_RESOURCE_BASELINE.md`
- `docs/security/THREAT_MODEL.md`
- `docs/security/EXTERNAL_SECURITY_REVIEW.md`
- `docs/runbooks/database-degradation.md`
- `docs/runbooks/redis-degradation.md`
- `docs/runbooks/celery-degradation.md`
- `docs/runbooks/observability-incident.md`
- `docs/runbooks/README.md`

## Phase 5 Evidence

- `MIGRATION_READINESS.md`
- `ROLLBACK_PROCEDURE.md`
- `DEPLOYMENT_RUNBOOK.md`
- `PRODUCTION_READINESS_EXIT_REVIEW.md`

## Current Verified Backend State

- Git revision: `bec0b92d429d42d4d59aa8346cb03ba2175fa675`
- migration head: `4d205e66d288`
- migration heads: single head
- migration autogenerate check: clean
- full regression: 7,397 passed, 0 failed, 0 errors, 2 skipped
- full regression date: 2026-10-01
- full regression duration: 8,078.52 seconds (2:14:38)
- dashboard integration: 4 passed

The current regression result is time-specific evidence. It does not by
itself establish production deployment readiness.

## Environment-Dependent Validation

The following require the Phase 6 production-like backend environment or
later release gates:

- actual deployment execution
- Linux production serving path
- reverse proxy and TLS execution
- staging restore
- rollback execution
- production artifact provenance/SBOM/signing execution
- startup/shutdown execution
- post-deployment smoke testing
- measured production resource baseline
- independent external security testing

These must not be represented as completed until independently executed
and evidenced.

## Open Evidence Gates

The following remain tracked before final release-candidate freeze:

- deterministic dependency/release artifact reproducibility
- software supply-chain artifact generation and provenance/signing
- review of open dependency-update pull requests
- Celery Beat schedule naming/interval consistency
- current-head production-like restore execution
- production-like deployment and operational validation

## Final Regression

The latest full application regression completed with:

- 7,397 passed
- 0 failed
- 0 errors
- 2 skipped

The run completed on 2026-10-01 in 8,078.52 seconds (2:14:38) and is
treated as time-specific evidence.
