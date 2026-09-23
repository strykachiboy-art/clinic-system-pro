# Clinic System Pro v5 — Load Testing & Performance Benchmarking

## 1. Purpose

The `load_tests/` package provides a controlled, reproducible performance and load-testing framework for Clinic System Pro v5.

It is designed to measure and investigate:

```text
API response latency
Throughput
Error rates
Database query count
Database execution time
Response sizes
Endpoint-level performance
Module-level performance
System-wide mixed workloads
Performance regressions
Infrastructure behavior
```

The load-testing system deliberately separates:

```text
Application correctness
Benchmark workload generation
Server-side performance measurements
Locust client-side measurements
Benchmark result validation
Performance profiling
Performance optimization
System-wide workload verification
```

The benchmark environment exercises the real application path rather than creating benchmark-only shortcuts.

---

# 2. Performance Testing Principles

Performance testing follows these rules:

```text
Authentication is real
Authorization is real
Tenant isolation is real
Validation is real
Transactions remain enabled
Audit logging remains enabled
Production service logic is exercised
Database constraints remain active
Redis dependencies remain active
```

Benchmarking must not bypass application guarantees just to produce better numbers.

The purpose of the framework is to expose real application behavior and identify measurable bottlenecks.

---

# 3. Benchmark Architecture

```text
                    ┌──────────────────────┐
                    │   Benchmark Runner   │
                    │   baseline.py        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       Locust         │
                    │  Scenario Workload   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Flask API Server   │
                    │ Clinic System Pro v5 │
                    └──────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
             ┌──────────────┐      ┌──────────────┐
             │ PostgreSQL   │      │    Redis     │
             │ Source Truth │      │ Infrastructure│
             └──────────────┘      └──────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Performance Metrics  │
                    │ Server-side records  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ JSON / CSV / Logs    │
                    │ Benchmark Artifacts  │
                    └──────────────────────┘
```

---

# 4. Server-Side Metrics vs Locust Metrics

Server-side measurements are the primary source for application performance analysis.

The application records values such as:

```text
duration_ms
db_time_ms
db_query_count
response_size_bytes
HTTP status
HTTP method
route
load_test_id
```

Locust measurements remain important for observing client-perceived behavior.

Client-side timing may include:

```text
Network overhead
Client scheduling
Connection establishment
Local machine contention
Locust process overhead
```

Therefore:

```text
Server-side metrics
=
Primary application-performance evidence

Locust metrics
=
Client-side supporting evidence
```

---

# 5. Benchmark Environment

The standard local benchmark profile used for the controlled benchmark cycle is:

| Setting        | Value                       |
| -------------- | --------------------------- |
| Python         | 3.12.x                      |
| Locust         | Project environment version |
| Users          | Controlled per scenario     |
| Spawn rate     | Controlled per scenario     |
| Runtime        | Controlled per scenario     |
| Host           | `http://127.0.0.1:5000`     |
| Database       | PostgreSQL                  |
| Infrastructure | Redis                       |
| Application    | Clinic System Pro v5        |

Individual benchmark commands must record their actual user count, spawn rate, runtime, host, and run ID.

The standard local profile is not a production-capacity claim.

---

# 6. Synthetic Benchmark Identity

Load testing uses dedicated synthetic accounts.

The benchmark environment must never use real patient or staff accounts.

Typical environment variables include:

```text
LOCUST_EMAIL
LOCUST_PASSWORD
LOCUST_PATIENT_ID
LOCUST_DRUGS
LOCUST_TOKENS_FILE
LOCUST_AI_MODE
```

Synthetic data is preferred because it makes performance measurements repeatable without exposing real medical information.

---

# 7. Run ID Requirements

Every benchmark run must use a unique run ID.

Examples:

```text
patients-baseline-003
appointments-baseline-001
reports-baseline-001
system-mixed-baseline-003
```

Recommended format:

```text
<scenario>-baseline-<number>
```

Do not reuse a run ID for a new benchmark.

Run IDs provide correlation between:

```text
Locust execution
Server-side performance records
Logs
JSON benchmark artifacts
```

---

# 8. Scenario Layout

Individual Locust workloads are located in:

```text
load_tests/scenarios/
```

Current scenario files:

```text
access_control.py
ambulance.py
appointments.py
asset_control.py
audit.py
authentication.py
billing.py
chat.py
clinic.py
consultations.py
dashboard.py
hie.py
inventory.py
laboratory.py
locust_ai.py
notifications.py
patients.py
pharmacy.py
prescriptions.py
profile.py
reports.py
settings.py
staff.py
system_mixed.py
user_devices.py
wards.py
```

Current implementation coverage:

```text
25 / 25 individual scenarios
```

---

# 9. Scenario Implementation vs Benchmark Verification

These are separate states.

```text
Scenario implemented
≠
Scenario benchmark verified
```

An implementation means the workload exists.

A verified benchmark means the workload was executed using the controlled benchmark process and the resulting evidence passed the benchmark validation rules.

This distinction prevents unsupported performance claims.

---

# 10. Benchmark Runner

The central runner is:

```text
load_tests/baseline.py
```

The runner is responsible for capabilities including:

```text
Scenario execution
Run-ID management
Fresh-run validation
Server log correlation
Server-side metric aggregation
Locust artifact parsing
Route filtering
Login/setup filtering
Result validation
JSON result generation
Existing-result repair
```

The reporting helper is:

```text
load_tests/baseline_report.py
```

---

# 11. Basic Benchmark Command

Example:

```powershell
python -m load_tests.baseline `
    --scenario patients `
    --run-id patients-baseline-001
```

Explicit configuration can be supplied:

```powershell
python -m load_tests.baseline `
    --scenario patients `
    --run-id patients-baseline-001 `
    --host http://127.0.0.1:5000 `
    --users 10 `
    --spawn-rate 2 `
    --time 30s
```

---

# 12. Existing Result Repair

The benchmark runner supports repair of an existing result artifact when a benchmark has already been executed but server-side metrics need to be reconstructed.

Example:

```powershell
python -m load_tests.baseline `
    --scenario patients `
    --run-id patients-baseline-003 `
    --repair-existing
```

Repair mode does not execute Locust again.

It can:

```text
Read the existing benchmark result
Read the associated server log
Match records using the run ID
Apply the scenario filters
Recalculate server-side metrics
Preserve existing Locust metadata
Rewrite the JSON artifact
```

This provides reproducibility without unnecessarily rerunning a completed workload.

---

# 13. Login and Setup Filtering

Non-authentication scenarios normally perform authentication before exercising their primary module workload.

For example:

```text
Setup/login traffic
        ↓
Module workload
```

For module benchmarks, setup authentication is excluded from primary module metrics when appropriate.

This prevents login overhead from contaminating the measurement of the module being benchmarked.

Authentication scenarios are different because authentication itself is the workload.

---

# 14. Route Filtering

The benchmark runner can target a specific route:

```text
--route /api/v1/patients
```

and can exclude routes when needed:

```text
--exclude-route /api/v1/auth/login
```

This enables controlled analysis when one scenario exercises multiple application routes.

---

# 15. Performance Record Format

Server-side instrumentation records performance data in a structure similar to:

```text
performance.request
load_test_id=<run_id>
method=<HTTP_METHOD>
route=<route>
status=<status>
duration_ms=<duration>
response_size_bytes=<size>
db_query_count=<query_count>
db_time_ms=<db_time>
```

Example:

```text
performance.request load_test_id=patients-baseline-003 method=GET route=/api/v1/patients status=200 duration_ms=19.7275 response_size_bytes=25271 db_query_count=4 db_time_ms=6.3771
```

---

# 16. Primary Server-Side Metrics

The framework calculates metrics including:

```text
Request count
Failure count
Status distribution
Minimum latency
Average latency
P50
P95
P99
Maximum latency
Average response size
Average DB time
Maximum DB time
Total DB queries
Average DB queries/request
```

These values are used for application-performance analysis.

---

# 17. Locust Metrics

Locust provides supporting measurements including:

```text
Request count
Failure count
Requests per second
Average response time
Median response time
Minimum response time
Maximum response time
Average content size
```

Client-side numbers should always be interpreted together with server-side records.

---

# 18. Performance Profiling Tools

The load-testing package also contains targeted profiling tools.

Current profiling utilities include:

```text
profile_chat_create_message.py
profile_chat_security.py
profile_chat_security_deep.py
profile_chat_services.py

profile_dashboard_service.py
profile_dashboard_warm.py

explain_dashboard_queries.py
trace_chat_create_queries.py
```

These tools are used when an observed benchmark result requires deeper investigation.

Profiling is separate from the clean benchmark workload.

---

# 19. Database Query Analysis

Database behavior is measured using:

```text
db_query_count
db_time_ms
```

The framework is intended to expose:

```text
N+1 query patterns
Unexpected query multiplication
Expensive joins
Unbounded queries
Pagination problems
Missing indexes
Tenant-filter inefficiencies
Sorting inefficiencies
Unnecessary database round trips
```

Database optimization must preserve:

```text
Tenant isolation
Authorization
Transaction boundaries
Data correctness
Deterministic ordering
```

---

# 20. Response Size Analysis

Response size is measured because large payloads can affect:

```text
Server serialization
Network transfer
Client latency
Memory usage
Mobile performance
Flutter rendering
Bandwidth consumption
```

Latency should therefore never be evaluated independently of response size.

---

# 21. Benchmark Data

Benchmark data is controlled through:

```text
load_tests/benchmark_dataset.json
```

Data seeding:

```text
load_tests/seed_load_test_data.py
```

AI load-user provisioning:

```text
load_tests/provision_ai_load_users.py
```

Benchmark data is synthetic.

The production database must not be populated with benchmark-only records merely to generate benchmark results.

---

# 22. Benchmark Data Integrity

A benchmark should verify all relevant conditions before being accepted as evidence.

Typical checks include:

```text
Dataset exists
Synthetic users exist
Authentication succeeds
Intended route is reached
Fresh server log exists
Matching run ID exists
Correct workload records are present
Setup traffic is correctly filtered
Server failures are zero
Locust exits successfully
Result artifact is valid
```

A successful Locust process by itself is not sufficient evidence of a valid application benchmark.

---

# 23. Benchmark Validity

A benchmark is accepted only when the required integrity conditions pass.

Core validation concepts include:

```text
Unique run ID
Fresh execution context
Server log availability
Matching server records
Correct workload filtering
Zero unexpected server failures
Successful Locust completion
Valid result artifact
```

Invalid runs must be investigated rather than promoted to official baselines.

---

# 24. Benchmark Execution Workflow

The controlled workflow is:

```text
1. Start PostgreSQL
2. Start Redis
3. Start Clinic System Pro
4. Verify synthetic benchmark data
5. Verify benchmark identity
6. Generate a unique run ID
7. Start a fresh server log
8. Execute the Locust scenario
9. Collect Locust artifacts
10. Parse server-side performance records
11. Filter setup traffic where appropriate
12. Validate the run
13. Store the result
14. Analyze performance
15. Compare against previous verified results
```

---

# 25. Optimization Workflow

Performance optimization follows:

```text
Measure
   ↓
Establish baseline
   ↓
Identify measurable bottleneck
   ↓
Change one controlled area
   ↓
Run functional tests
   ↓
Re-benchmark
   ↓
Compare metrics
   ↓
Accept or revert
```

Optimization should not be based solely on intuition.

---

# 26. Performance Regression Tracking

Important comparison metrics include:

```text
Average latency
P50
P95
P99
Maximum latency
DB time
DB queries/request
Response size
Throughput
Failure count
```

A change should not be called an improvement solely because one number decreased.

Examples that require investigation:

```text
Latency ↓
DB queries ↑
```

or:

```text
Average latency ↓
P99 latency ↑ significantly
```

or:

```text
Server latency stable
Response size ↑ significantly
```

---

# 27. Individual Scenario Coverage

Current implementation coverage:

| Scenario       | Status      |
| -------------- | ----------- |
| Access Control | Implemented |
| Ambulance      | Implemented |
| Appointments   | Implemented |
| Asset Control  | Implemented |
| Audit          | Implemented |
| Authentication | Implemented |
| Billing        | Implemented |
| Chat           | Implemented |
| Clinic         | Implemented |
| Consultations  | Implemented |
| Dashboard      | Implemented |
| HIE            | Implemented |
| Inventory      | Implemented |
| Laboratory     | Implemented |
| AI             | Implemented |
| Notifications  | Implemented |
| Patients       | Implemented |
| Pharmacy       | Implemented |
| Prescriptions  | Implemented |
| Profile        | Implemented |
| Reports        | Implemented |
| Settings       | Implemented |
| Staff          | Implemented |
| User Devices   | Implemented |
| Wards          | Implemented |

Therefore:

```text
Individual scenario implementations:
25 / 25
```

---

# 28. System-Wide Mixed Workload

The system-wide workload is represented by:

```text
load_tests/scenarios/system_mixed.py
```

Its purpose is to exercise multiple application domains concurrently instead of benchmarking isolated modules independently.

The mixed workload incorporates realistic application categories such as:

```text
Clinical workflows
Patient access
Medication/inventory workflows
Front-desk activity
Administrative activity
Communication
Reporting
Dashboard activity
```

The system-wide benchmark is intended to reveal interactions and contention that isolated module tests cannot expose.

---

# 29. Verified System-Mixed Baseline

A controlled mixed baseline was established during the local benchmark cycle.

Current reference run:

```text
system-mixed-baseline-003
```

Recorded server-side reference metrics:

```text
Requests:
410

Failures:
0

Average server latency:
22.014 ms

P50:
17.465 ms

P95:
43.267 ms

P99:
95.092 ms

Maximum:
463.256 ms

Average DB time:
7.075 ms

Maximum DB time:
310.649 ms

Average DB queries/request:
5.327

Total DB queries:
2,184

Total DB time:
2,900.86 ms
```

This is a controlled local benchmark reference, not a distributed production-capacity claim.

The figures should be interpreted with the exact benchmark environment and workload configuration used for the run.

---

# 30. Local Hardware Limitation

Local development-machine benchmarks are useful for:

```text
Regression detection
Comparative optimization
Database behavior analysis
Endpoint profiling
Application correctness under load
```

They are not sufficient to establish very-large-scale production capacity.

Large concurrency claims require:

```text
Multiple load generators
Distributed execution
Controlled infrastructure
Dedicated database resources
Network-aware measurement
Monitoring
Repeatable environments
```

The project therefore separates:

```text
Application benchmark evidence
from
Production capacity claims
```

---

# 31. Concurrency vs Data Volume

Concurrency and data volume are separate benchmark dimensions.

Concurrency measures:

```text
How many clients/users are active simultaneously?
```

Data volume measures:

```text
How much data exists in the system?
```

The project must not treat a large database-record target as equivalent to a large concurrent-user target.

Future data-volume testing may use populated datasets in the thousands or beyond.

Future distributed concurrency testing is a separate exercise.

---

# 32. Current Load-Testing Phase

The dedicated load/performance-testing phase is considered complete for the current engineering cycle.

The completion boundary is:

```text
Individual scenarios:
25 / 25 implemented

Controlled benchmark infrastructure:
Established

Server-side performance instrumentation:
Established

Profiling tooling:
Established

System-mixed workload:
Established and exercised

Benchmark validation:
Established

Performance optimization / verification cycle:
Completed for the current phase
```

The next engineering phase is not another round of routine local baseline generation.

The project has moved to:

```text
Resilience and Recovery Engineering
```

---

# 33. AI Load Testing

The AI scenario is:

```text
load_tests/scenarios/locust_ai.py
```

The route exercised includes:

```text
POST /api/v1/ai/drug-interactions
```

The AI benchmark depends on an external provider.

Therefore AI performance measurements must be separated from ordinary application benchmarks because external conditions can include:

```text
Provider availability
Provider rate limits
Provider model access
Provider billing/quota
Provider network latency
```

The current AI integration was successfully exercised through provider authentication/model access, but generation benchmarking was blocked by an external provider quota condition.

Therefore:

```text
AI benchmark status:
Provider-blocked
```

This must not be interpreted as an application-route failure.

---

# 34. Why AI Is Tracked Separately

An external AI provider is not controlled by the Flask application.

Therefore:

```text
Normal application benchmark

vs

External-provider benchmark
```

must remain separate.

The AI scenario is retained for future controlled benchmarking when provider availability and quota permit.

---

# 35. Benchmark Result Philosophy

Every result should answer:

```text
What was measured?
Under what workload?
With how many users?
For how long?
Against which host?
Using which run ID?
What did the server record?
What did Locust record?
Was the run valid?
```

A benchmark without this context is not sufficient evidence.

---

# 36. Historical Results

Historical benchmark artifacts may remain useful for:

```text
Regression analysis
Optimization comparisons
Methodology review
Debugging
Historical traceability
```

Historical values must not automatically be treated as current measurements when a newer verified result exists.

Never manufacture missing metrics.

Always prefer the newest verified artifact for current performance statements.

---

# 37. Resilience Testing Is Separate

Resilience testing is intentionally isolated from ordinary load testing.

The new resilience package is:

```text
load_tests/resilience/
```

Current structure:

```text
load_tests/resilience/
├── README.md
├── __init__.py
├── common/
│   ├── __init__.py
│   ├── network.py
│   ├── socketio.py
│   ├── assertions.py
│   └── results.py
├── profiles/
│   ├── __init__.py
│   ├── slow_2g.py
│   ├── slow_3g.py
│   ├── high_latency.py
│   ├── jitter.py
│   ├── packet_loss.py
│   ├── bandwidth_limited.py
│   └── intermittent.py
├── scenarios/
│   ├── __init__.py
│   ├── http_resilience.py
│   ├── socketio_resilience.py
│   ├── auth_resilience.py
│   ├── chat_resilience.py
│   └── sync_resilience.py
├── runners/
│   ├── __init__.py
│   ├── resilience.py
│   └── resilience_report.py
└── results/
```

The resilience package is currently a scaffold.

No resilience-network behavior should be assumed to be implemented merely because the files exist.

---

# 38. Performance vs Resilience

The distinction is:

```text
PERFORMANCE

Measures:
latency
throughput
concurrency
database cost
resource behavior
response sizes
```

versus:

```text
RESILIENCE

Measures:
failure behavior
recovery
disconnect handling
retry behavior
degraded-network behavior
data integrity during interruption
duplicate protection
reconnection
offline behavior
```

A system can be fast and still be fragile.

It can also be resilient while needing performance optimization.

The two test disciplines therefore remain separate.

---

# 39. Current Resilience Targets

The resilience phase is expected to examine:

```text
Slow internet
High latency
Jitter
Packet loss
Bandwidth limitation
Intermittent connectivity

HTTP interruption
Authentication interruption
Socket.IO disconnect/reconnect
Chat recovery

Flutter offline behavior
SQLite synchronization

Redis degradation
Celery degradation

Recovery behavior
Duplicate protection
Data integrity protection
```

The implementation of these scenarios belongs to the resilience phase rather than the completed load-testing phase.

---

# 40. Existing Profiling Scope

Current profiling work has included focused inspection of:

```text
Dashboard service
Chat message creation
Chat security
Chat service execution
SQL execution
```

Profilers exist so that an observed performance issue can be traced to:

```text
Application code
Database queries
Service logic
Infrastructure interaction
```

Profiling results should not be confused with benchmark baselines.

---

# 41. Benchmark Safety Rules

Official benchmarks must:

```text
Use synthetic identities
Use controlled test data
Use unique run IDs
Preserve authentication
Preserve authorization
Preserve tenant isolation
Preserve validation
Preserve transactions
Preserve audit behavior
Use fresh benchmark context
Validate the resulting evidence
```

Avoid:

```text
Real patient accounts
Real production credentials
Uncontrolled destructive workloads
Benchmark-only production bypasses
Shared run IDs
Mixed benchmark logs
Unverified result promotion
```

---

# 42. Benchmark Methodology Rules

The project follows these rules of record:

```text
1. Use synthetic benchmark identities.

2. Use a unique run ID.

3. Use a fresh server log.

4. Record the actual benchmark configuration.

5. Treat server-side metrics as the primary application evidence.

6. Treat Locust metrics as supporting client-side evidence.

7. Exclude setup/login traffic from non-auth workloads where appropriate.

8. Prefer populated synthetic workloads for realistic data-dependent endpoints.

9. Do not modify production logic solely to improve benchmark numbers.

10. Do not accept runs with failed integrity checks.

11. Preserve verified benchmark artifacts.

12. Do not overwrite verified results with unverified runs.

13. Record methodology changes explicitly.

14. Optimize only after measuring the bottleneck.

15. Re-benchmark after meaningful performance changes.

16. Preserve security, tenant isolation, authorization, validation,
    transactions and auditability throughout performance testing.
```

---

# 43. Current Repository Utilities

The main load-testing utilities currently include:

```text
load_tests/baseline.py
load_tests/baseline_report.py
load_tests/common/auth.py
load_tests/common/benchmark.py

load_tests/seed_load_test_data.py
load_tests/provision_ai_load_users.py
load_tests/verify_benchmark_dataset.py
```

Profiling and investigation utilities include:

```text
load_tests/profile_chat_create_message.py
load_tests/profile_chat_security.py
load_tests/profile_chat_security_deep.py
load_tests/profile_chat_services.py
load_tests/profile_dashboard_service.py
load_tests/profile_dashboard_warm.py
load_tests/explain_dashboard_queries.py
load_tests/trace_chat_create_queries.py
```

---

# 44. Current Status Summary

```text
CLINIC SYSTEM PRO v5 LOAD TESTING

Individual scenario implementations:
25 / 25

Benchmark infrastructure:
Complete

Server-side performance instrumentation:
Complete

Benchmark validation:
Complete

Targeted profiling tools:
Complete

System-mixed workload:
Implemented and exercised

Current controlled mixed baseline:
system-mixed-baseline-003

Current load/performance phase:
COMPLETE FOR CURRENT ENGINEERING CYCLE

Next phase:
RESILIENCE AND RECOVERY ENGINEERING
```

---

# 45. What Load Testing Is No Longer Responsible For

The load-testing package should not be used to claim that the application already has:

```text
Production disaster recovery
Database backup
Restore capability
Point-in-time recovery
Offline synchronization
Network-failure recovery
Redis failover
Celery failover
Distributed million-user capacity
```

Those are separate engineering concerns.

---

# 46. Current Roadmap

The current engineering sequence is:

```text
LOAD / PERFORMANCE
        ✓

        ↓

RESILIENCE / RECOVERY
        NEXT

        ↓

BACKUP EXECUTION
        ↓
RESTORE + VERIFICATION
        ↓
RETENTION / RECOVERY POLICY
        ↓
PRODUCTION READINESS REVIEW
        ↓
FUTURE DISTRIBUTED SCALABILITY VALIDATION
```

The resilience and backup frameworks are deliberately separated from the performance baseline infrastructure so each discipline produces clean, interpretable evidence.

---

# 47. Final Status Boundary

The project distinguishes between:

```text
Implemented
Verified
Profiled
Scaffolded
Planned
```

A file existing in the repository does not mean the capability is operational.

In particular:

```text
Load testing:
Implemented and completed for the current cycle

Resilience framework:
Scaffolded

Backup framework:
Scaffolded

Offline synchronization:
Planned / not fully implemented
```

This distinction is intentional and must be preserved throughout the remaining engineering phases.
