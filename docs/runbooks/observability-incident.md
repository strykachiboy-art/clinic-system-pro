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

## 5. Load Shedding / Resource Pressure

Use when sustained queue pressure, CPU pressure, memory pressure, or repeated
rate-limit events indicate that the service is approaching resource limits.

Existing application protections include:

- endpoint-specific rate limits for authentication and AI operations
- request-size protection through MAX_CONTENT_LENGTH
- Celery queue-depth monitoring
- CPU and memory utilization monitoring
- worker utilization and concurrency monitoring

Operational response:

1. Preserve health endpoints and core clinical request processing.
2. Investigate queue growth and worker health before repeatedly restarting
   workers.
3. At the configured queue-depth warning threshold, begin containment and
   capacity investigation.
4. At the configured queue-depth critical threshold, initiate the approved
   scaling or containment procedure and reduce non-essential workload where
   operationally appropriate.
5. Sustained CPU or memory utilization at the configured warning threshold
   requires capacity or worker-health investigation.
6. Endpoint rate limits remain authoritative for protected operations and
   should return normal rate-limit responses rather than allowing uncontrolled
   retry amplification.
7. Production reverse-proxy infrastructure must enforce connection/request
   limits and provide controlled overload responses where application
   capacity is exhausted.
8. Do not shed authentication, authorization, tenant-isolation, audit, or
   critical clinical persistence merely to preserve non-critical workload.
9. Do not perform destructive database actions as a load-shedding response.

Production load-shedding controls that depend on the reverse proxy, process
manager, container runtime, or infrastructure capacity must be validated in
the production-like backend environment.

Recovery requires:

- dependency health restored
- readiness healthy
- queue pressure stable or falling
- CPU and memory pressure returned to acceptable levels
- normal request processing confirmed

Document the trigger, containment action, affected workload, recovery action,
and verification evidence.
## 6. Close

Record:

- root cause if known
- containment action
- recovery action
- verification evidence
- remaining risk
- follow-up work

Unknown root cause is acceptable. Unsupported assumptions are not.

