# Celery Degradation Runbook

## Use when

Use when:

- workers are unavailable
- queue depth increases
- task failures increase
- retry events increase
- long-running tasks accumulate
- broker health is degraded

## 1. Verify

Check:

- GET /api/v1/operations
- GET /api/v1/operations/failures

Review:

- broker health
- worker count
- total concurrency
- active tasks
- reserved tasks
- scheduled tasks
- queue depth
- worker utilization
- long-running tasks

## 2. Determine failure mode

Possible states:

- broker failure
- worker failure
- queue pressure
- task failure
- retry storm

## 3. Containment

Prefer the smallest safe action:

- restore broker connectivity
- restart only unhealthy workers
- stop a worker that repeatedly fails
- prevent a retry storm where operationally supported
- restore sufficient worker capacity

Do not discard queued work as a generic recovery action.

## 4. Inspect failed work

Use:

- event_id
- task_name
- task_id
- event_type
- timestamp
- severity

Do not expose task arguments or payloads in incident records.

## 5. Verify

Confirm:

- broker healthy
- worker count restored
- queues stable or decreasing
- active tasks progressing
- retry volume normalizing
- long-running tasks decreasing

## 6. Close

Record:

- affected task or queue
- worker impact
- containment
- recovery
- verification evidence
- follow-up action
