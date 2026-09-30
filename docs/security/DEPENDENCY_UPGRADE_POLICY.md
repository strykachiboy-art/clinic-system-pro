# Dependency Upgrade Policy

## Release Handling

- Security releases: apply promptly after compatibility verification.
- Patch releases: apply during a planned maintenance window.
- Minor releases: require compatibility review and full regression testing.
- Major releases: require a dedicated upgrade plan and production-like validation.

## Core Dependencies

- Python minor versions: verify runtime and dependency compatibility before upgrading.
- PostgreSQL minor versions: controlled maintenance upgrade with backup/restore verification.
- PostgreSQL major versions: dedicated upgrade project.
- Redis patch/minor versions: controlled upgrade with Celery, Socket.IO, and readiness verification.
- Redis major versions: dedicated compatibility project.

## Required Verification

Every dependency upgrade must preserve authentication, tenant isolation, audit, transactions, migrations, Celery, and Redis/Socket.IO behavior.

Before production:
- run dependency security audit
- run migration checks
- run relevant regression and resilience tests
- maintain a rollback path
- record upgrade and verification evidence
