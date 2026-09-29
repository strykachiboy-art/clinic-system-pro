# Database Degradation Runbook

## Use when

Use when:

- readiness reports database unhealthy
- database latency increases
- requests fail because of database operations
- connection failures increase
- transactions become unreliable

## 1. Verify

Check:

- GET /health/ready
- GET /api/v1/operations
- GET /api/v1/operations/failures

Review:

- database health
- readiness latency
- request failure rate
- database query count
- database time
- recent application failures

## 2. Determine failure mode

Classify the issue as:

- connectivity
- authentication/configuration
- latency
- connection exhaustion
- query failure
- transaction failure
- infrastructure capacity

## 3. Containment

Prefer:

- stop a failing deployment
- restore healthy database connectivity
- remove an unhealthy application instance where appropriate
- reduce unnecessary load
- address connection exhaustion without deleting data

Do not run destructive SQL during an incident unless there is a documented, authorized procedure for that failure.

## 4. Verify

Confirm:

- database healthy
- application readiness healthy
- HTTP failure rate returning toward baseline
- database latency stabilizing
- transactions completing successfully

## 5. Data integrity

If there is evidence of inconsistency:

- stop unnecessary write activity where safe
- preserve evidence
- escalate to the appropriate recovery procedure

Do not improvise restore actions here.

The controlled backup/restore drill is a separate roadmap procedure.

## 6. Close

Record:

- failure mode
- affected capability
- containment action
- recovery action
- verification result
- integrity concerns
- required follow-up
