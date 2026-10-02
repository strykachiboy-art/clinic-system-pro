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

- Git revision: `0ee5756ccb39ef18fe41dca3052de0727f5a7192`
- migration head: `4d205e66d288`
- migration heads: single head
- migration autogenerate check: clean
- full regression: 7,397 passed, 0 failed, 0 errors, 2 skipped
- full regression date: 2026-10-01
- full regression duration: 8,078.52 seconds (2:14:38)
- dashboard integration: 4 passed
- resilience regression: 272 passed
- dependency audit: `pip-audit -r backend/requirements.lock --strict` → no known vulnerabilities
- container lock verification: 91/91 locked Python packages matched the container
- GHCR container supply-chain build: successful
- registry image digest: `sha256:bf3061cefed2ac377d5e8959678b3626c16f6d48e57e5ec497bd0650c580f348`
- registry SBOM attestation: verified
- registry SLSA provenance attestation: verified
- registry attestation linkage to linux/amd64 image manifest: verified

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
- production-like artifact deployment/execution and image signing
- startup/shutdown execution
- post-deployment smoke testing
- measured production resource baseline
- independent external security testing

These must not be represented as completed until independently executed
and evidenced.

## Open Evidence Gates

The following remain tracked before final release-candidate freeze:

- fully hash-pinned dependency artifact reproducibility
- image signing and release-signature verification
- review of open dependency-update pull requests
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
