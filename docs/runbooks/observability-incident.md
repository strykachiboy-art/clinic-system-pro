# Observability Incident Runbook

## Use when

Use for HTTP 5xx spikes, unexpected application errors, multiple subsystem alerts, unexplained degradation, or unknown operational incidents.

## 1. Establish scope

Check:

- GET /health/live
- GET /health/ready
- GET /api/v1/operations
- GET /api/v1/operations/failures

Record the incident start time, affected component, first failure, latest failure, request ID, trace ID, and alert code where available.

Do not copy secrets or PHI into the incident record.

## 2. Determine failure type

Classify the incident as:

- API/application
- database
- Redis
- Celery
- Socket.IO
- infrastructure/system

Failure event types include:

- http.5xx
- application.error
- celery.task_failure
- celery.task_retry

## 3. Correlate

For an individual failure, correlate:

- event_id
- request_id
- trace_id
- component
- event_type
- timestamp

## 4. Contain

Prefer the least disruptive safe action.

Examples:

- stop an unsafe deployment
- disable a failing optional integration
- restart only the affected worker
- remove a clearly unhealthy worker from service
- prevent repeated failed task execution when appropriate

Do not perform destructive database actions from this runbook.

## 5. Verify

Confirm:

- dependency health is restored
- readiness is healthy
- new failure volume is falling
- queue pressure is stable
- critical alerts are resolved or understood
- normal request processing resumes

## 6. Close

Record:

- root cause if known
- containment action
- recovery action
- verification evidence
- remaining risk
- follow-up work

Unknown root cause is acceptable. Unsupported assumptions are not.
