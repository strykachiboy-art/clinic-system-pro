# Redis Degradation Runbook

## Use when

Use when:

- readiness reports Redis unhealthy
- Redis latency increases
- token revocation is degraded
- rate limiting is degraded
- Celery broker health is affected
- Socket.IO coordination is affected

## 1. Verify

Check:

- GET /health/ready
- GET /api/v1/operations
- GET /api/v1/operations/failures

Review:

- connected clients
- blocked clients
- used memory
- cache hit ratio
- rejected connections
- evicted keys
- expired keys
- instantaneous operations per second

## 2. Basic Redis checks

Use the least invasive checks available:

redis-cli PING
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO stats

Never expose connection URLs or credentials in incident records.

## 3. Determine impact

Check whether the degradation affects:

- authentication token revocation
- rate limiting
- Celery broker operations
- Socket.IO coordination
- application caching

Treat authentication and authorization dependencies as high priority.

## 4. Containment

Prefer:

- restore the healthy Redis service path
- remove an unhealthy Redis instance from service
- restart the affected Redis process only when justified
- reduce nonessential Redis load

Do not flush Redis databases or delete keys as a generic recovery step.

## 5. Verify

Confirm:

- Redis healthy
- application readiness healthy
- Celery broker healthy
- Socket.IO coordination healthy
- no continuing critical Redis alerts

## 6. Close

Record the observed failure mode, affected capabilities, recovery action, and verification result.
