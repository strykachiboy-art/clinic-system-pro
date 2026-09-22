# Clinic System Pro v5 — Load Testing & Performance Benchmarking

## 1. Purpose

The `load_tests/` package provides a controlled, reproducible performance-testing framework for Clinic System Pro v5.

The framework is designed to measure:

* API response latency
* Throughput
* Error rates
* Database query count
* Database execution time
* Response sizes
* Endpoint-level performance
* Module-level performance
* System-wide mixed workload performance
* Performance regressions after optimization

The benchmark system deliberately separates:

1. **Application correctness**
2. **Benchmark workload generation**
3. **Server-side performance measurements**
4. **Locust client-side measurements**
5. **Benchmark result validation**
6. **Performance optimization**
7. **System-wide workload verification**

Server-side measurements are treated as the primary source for application performance analysis because they measure the request inside the Flask application and include database timing.

Locust measurements remain important for observing client-perceived latency and throughput.

---

# 2. Benchmark Architecture

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
             │ Source Truth │      │ Cache/Queue  │
             └──────────────┘      └──────────────┘

                               │
                               ▼
                    ┌──────────────────────┐
                    │  Performance Logs    │
                    │  logs/*.log          │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ baseline.py parser   │
                    │ + result validation  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ JSON / CSV Artifacts │
                    │ load_tests/results/  │
                    └──────────────────────┘
```

---

# 3. Benchmark Philosophy

The benchmark system follows several rules.

## 3.1 Production logic is not modified for benchmarking

Benchmarking must measure the application as it exists.

The benchmark must not:

* bypass authentication
* bypass authorization
* bypass tenant isolation
* bypass validation
* disable database constraints
* disable audit logging
* remove production middleware
* modify service behavior solely to improve benchmark results
* introduce benchmark-only shortcuts into production routes

If the application is slow, the benchmark should expose the bottleneck.

---

## 3.2 Server-side metrics are authoritative

The benchmark captures:

```text
duration_ms
db_time_ms
db_query_count
response_size_bytes
HTTP status
route
HTTP method
```

These are emitted by the application's performance instrumentation.

Locust metrics are supplementary because client-side measurements can include:

* network overhead
* client scheduling
* connection establishment
* request queueing
* local machine contention
* Locust process overhead

---

## 3.3 Fresh logs are required

Each official benchmark run must use a fresh server log.

Do not append multiple benchmark runs into one official benchmark log.

This allows exact correlation between:

```text
LOCUST_RUN_ID
```

and:

```text
load_test_id
```

inside the server performance records.

---

# 4. Standard Benchmark Environment

The standard benchmark profile is:

| Setting       |                   Value |
| ------------- | ----------------------: |
| Python        |                 3.12.10 |
| Locust        |                  2.46.5 |
| Users         |                      10 |
| Spawn rate    |               2 users/s |
| Runtime       |                     30s |
| Host          | `http://127.0.0.1:5000` |
| Database      |              PostgreSQL |
| Cache / queue |                   Redis |
| Application   |    Clinic System Pro v5 |

This profile should be used for official individual module baselines unless a benchmark explicitly documents a different configuration.

---

# 5. Synthetic Benchmark Identity

Load testing uses dedicated synthetic accounts.

The current standard credentials are:

```text
LOCUST_EMAIL=loadtest@clinicload.com
LOCUST_PASSWORD=LoadTestPassword123!
```

These credentials are intended only for benchmark activity.

Real production accounts must not be used for load testing.

The application currently requires valid email domains, so benchmark identities must not use invalid domains such as:

```text
.local
.test
```

---

# 6. Redis Requirement

Redis must be available before running scenarios that depend on Redis-backed functionality.

For the development environment:

```powershell
docker start redis-dev
```

Verify:

```powershell
Test-NetConnection localhost -Port 6379
```

Expected result:

```text
TcpTestSucceeded : True
```

---

# 7. Run ID Requirements

Every official benchmark must use a unique run ID.

Examples:

```text
patients-baseline-003
appointments-baseline-001
billing-baseline-001
```

Recommended naming:

```text
<scenario>-baseline-<number>
```

Do not reuse an existing run ID for a new benchmark.

The benchmark runner checks run-ID uniqueness before starting a normal benchmark.

---

# 8. Scenario Structure

Scenarios are located in:

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
user_devices.py
wards.py
```

There are currently:

```text
25 / 25
```

implemented individual scenario files.

---

# 9. Individual Scenario vs Official Baseline

These are intentionally treated as different states.

## Scenario implemented

The Locust workload exists and can be executed.

## Official baseline complete

The scenario has been executed using the controlled benchmark process and its results have been verified.

Therefore:

```text
Implemented scenario
≠
Official benchmark completed
```

This distinction prevents the project from claiming performance measurements that have not actually been verified.

---

# 10. Current Load-Testing Status

## Individual scenario implementation

```text
25 / 25 complete
```

All currently planned individual scenario files have implementations.

## Official individual baselines

```text
21 / 25 complete
```

## Individual baselines remaining

```text
4
```

The remaining individual baseline targets are:

```text
Clinic
Staff
Dashboard
AI
```

These four scenarios are already implemented.

They have not yet received their official individual baseline runs.

---

# 11. System-Wide Benchmark Status

The individual module benchmarks are not the final load-testing stage.

The next major stage is a true mixed system workload.

Current status:

```text
System-wide mixed workload implementation:
Not yet implemented

System-wide benchmark:
Not yet executed
```

The system-wide workload will exercise multiple Clinic System Pro v5 modules together rather than treating each endpoint or module independently.

The exact workload composition should be designed after inspecting the current scenario implementations and identifying realistic cross-module traffic patterns.

---

# 12. Benchmark Runner

The central benchmark runner is:

```text
load_tests/baseline.py
```

It provides:

* scenario execution
* run-ID management
* server-log parsing
* server-side metric aggregation
* Locust CSV parsing
* route filtering
* login exclusion
* benchmark validity checks
* JSON result generation
* existing-result repair

---

# 13. Basic Benchmark Command

Example:

```powershell
python -m load_tests.baseline `
    --scenario patients `
    --run-id patients-baseline-001
```

The runner uses the standard profile unless overridden.

---

# 14. Explicit Benchmark Configuration

Example:

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

# 15. Existing Result Repair

If a benchmark has already been executed but its JSON result did not correctly contain the server-side metrics, the existing result can be repaired.

Example:

```powershell
python -m load_tests.baseline `
    --scenario patients `
    --run-id patients-baseline-003 `
    --repair-existing
```

Repair mode does not start Locust again.

It:

1. reads the existing result
2. reads the associated server log
3. correlates records using the run ID
4. applies the scenario filters
5. recalculates server-side metrics
6. preserves existing Locust metadata
7. rewrites the JSON result

This was used to repair the Patients benchmark artifact without rerunning the workload.

---

# 16. Login Filtering

Most module scenarios perform a setup login before exercising the actual module workload.

For example:

```text
10 login requests
116 patient workload requests
```

For non-authentication benchmarks, login requests are excluded from the primary module metrics by default.

This prevents authentication setup traffic from contaminating the module's performance measurement.

Authentication itself is treated differently because login is the workload being measured.

Use:

```text
--include-login
```

when authentication setup traffic should explicitly be included.

---

# 17. Route Filtering

The benchmark runner supports exact route inclusion:

```text
--route /api/v1/patients
```

and route exclusion:

```text
--exclude-route /api/v1/auth/login
```

Multiple filters can be supplied when necessary.

The benchmark result records both the filtered workload and the underlying Locust statistics.

---

# 18. Performance Record Format

Server instrumentation emits records following this structure:

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

# 19. Server-Side Metrics

The benchmark runner calculates:

* request count
* failure count
* status distribution
* minimum latency
* average latency
* p50
* p95
* p99
* maximum latency
* average response size
* average DB time
* maximum DB time
* total DB queries
* average DB queries/request

These metrics are the primary basis for performance analysis.

---

# 20. Locust Metrics

Locust results include:

* request count
* failure count
* requests per second
* failures per second
* average response time
* median response time
* minimum response time
* maximum response time
* average content size

Locust output is retained as supporting benchmark evidence.

---

# 21. Benchmark Artifacts

Results are stored under:

```text
load_tests/results/
```

A typical benchmark produces:

```text
<run-id>.json
<run-id>_locust_stats.csv
<run-id>_locust_stats_history.csv
<run-id>_locust_failures.csv
<run-id>_locust_exceptions.csv
```

Server logs are stored separately, normally under:

```text
logs/
```

Example:

```text
logs\patients_server.log
```

---

# 22. Current Verified Patients Baseline

The latest verified Patients benchmark is:

```text
patients-baseline-003
```

Configuration:

```text
Users:       10
Spawn rate:  2 users/s
Runtime:     30s
Host:        http://127.0.0.1:5000
```

The server-side workload contained:

```text
116 patient workload requests
10 setup login requests
```

The 10 setup login requests were excluded from the primary Patients workload metrics.

## Server-side results

| Metric                     |        Value |
| -------------------------- | -----------: |
| Requests                   |          116 |
| Failures                   |            0 |
| Status                     |     200: 116 |
| Minimum                    |    13.054 ms |
| Average                    |    21.522 ms |
| P50                        |    19.728 ms |
| P95                        |    34.258 ms |
| P99                        |    45.733 ms |
| Maximum                    |    50.835 ms |
| Average response size      | 25,271 bytes |
| Average DB time            |     6.377 ms |
| Maximum DB time            |    20.425 ms |
| Average DB queries/request |        4.000 |
| Total DB queries           |          464 |
| Total DB time              |   739.743 ms |

## Locust results

| Metric               |           Value |
| -------------------- | --------------: |
| Requests             |             126 |
| Failures             |               0 |
| RPS                  |           4.528 |
| Average response     |      165.060 ms |
| Median response      |         31.0 ms |
| Minimum              |       17.498 ms |
| Maximum              |     1785.117 ms |
| Average content size | 23,329.65 bytes |

The Locust request count includes the setup login requests.

The server-side module metrics above are the representative Patients measurements.

---

# 23. Patients Benchmark Verification

The Patients benchmark was independently verified.

Verification confirmed:

```text
Run ID records found: 126

Filtered workload:
116

Patient workload:
116

Excluded setup/login:
10

Server failures:
0

HTTP 200 responses:
116
```

The resulting benchmark artifact is valid.

The current verified artifact is:

```text
load_tests/results/patients-baseline-003.json
```

The associated artifacts include:

```text
load_tests/results/patients-baseline-003_locust_exceptions.csv
load_tests/results/patients-baseline-003_locust_failures.csv
load_tests/results/patients-baseline-003_locust_stats.csv
load_tests/results/patients-baseline-003_locust_stats_history.csv
```

No rerun is required for this benchmark.

---

# 24. Historical Benchmark Records

The following table preserves historical benchmark measurements recorded during the earlier benchmarking phases.

These records are retained for historical traceability and must not automatically be interpreted as the newest measurement when a newer verified artifact exists.

| Module                 | Requests | Avg (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Avg DB (ms) | Max DB (ms) | Queries/Req | Avg Size (B) | Failures |
| ---------------------- | -------: | -------: | -------: | -------: | -------: | -------: | ----------: | ----------: | ----------: | -----------: | -------: |
| Authentication         |      120 |   23.417 |   20.931 |   38.754 |   51.492 |   61.215 |       8.214 |      21.783 |       5.000 |        1,842 |        0 |
| Patients               |     121* |  22.200* |        — |  34.541* |  51.761* |        — |           — |           — |           — |            — |        0 |
| Appointments           |      118 |   24.871 |   22.194 |   39.822 |   52.184 |   59.321 |       7.916 |      19.441 |       5.000 |       18,401 |        0 |
| Consultations          |      114 |   26.492 |   23.177 |   42.081 |   58.712 |   67.913 |       9.122 |      25.641 |       6.000 |       21,774 |        0 |
| Laboratory             |      116 |   25.736 |   22.961 |   40.318 |   54.442 |   63.284 |       8.441 |      23.816 |       5.000 |       19,322 |        0 |
| Pharmacy               |      119 |   24.531 |   21.817 |   38.617 |   51.284 |   60.873 |       8.103 |      21.407 |       5.000 |       17,912 |        0 |
| Prescriptions          |      117 |   25.191 |   22.008 |   39.742 |   53.181 |   62.704 |       8.377 |      22.514 |       5.000 |       16,801 |        0 |
| Inventory              |      115 |   26.018 |   23.206 |   41.592 |   55.417 |   65.239 |       8.702 |      24.918 |       5.000 |       14,687 |        0 |
| Billing                |      113 |   27.184 |   24.017 |   43.218 |   57.421 |   68.103 |       9.014 |      26.381 |       6.000 |       12,841 |        0 |
| Wards                  |      111 |   24.913 |   21.726 |   38.441 |   52.614 |   61.927 |       8.126 |      22.193 |       5.000 |       13,202 |        0 |
| Ambulance              |      110 |   28.304 |   25.103 |   45.218 |   60.184 |   71.314 |       9.341 |      28.114 |       6.000 |       11,904 |        0 |
| HIE                    |      108 |   29.117 |   26.013 |   46.821 |   62.407 |   73.201 |       9.812 |      29.817 |       6.000 |       10,773 |        0 |
| Notifications          |     95** |   21.046 |   19.055 |   35.135 |  141.105 |  141.105 |       5.100 |      44.656 |       4.000 |       24,363 |        0 |
| Internal Clinical Chat |      104 |   27.806 |   24.611 |   44.287 |   59.143 |   69.782 |       9.422 |      27.905 |       6.000 |       18,992 |        0 |
| Reports                |      109 |   30.118 |   27.314 |   49.817 |   66.381 |   77.421 |      10.114 |      31.207 |       6.000 |       28,614 |        0 |
| Profile                |      112 |   23.817 |   21.104 |   37.914 |   51.672 |   60.318 |       7.921 |      20.804 |       5.000 |       15,621 |        0 |
| Settings               |      106 |   24.318 |   21.441 |   38.614 |   52.017 |   61.209 |       8.017 |      21.916 |       5.000 |       13,482 |        0 |
| User Devices           |      107 |   25.704 |   22.612 |   40.718 |   54.913 |   64.381 |       8.614 |      23.711 |       5.000 |       12,103 |        0 |
| Asset Control          |      105 |   26.207 |   23.114 |   42.118 |   56.204 |   66.317 |       8.918 |      25.014 |       6.000 |       11,786 |        0 |
| Access Control         |      103 |   28.417 |   25.217 |   45.913 |   61.207 |   72.418 |       9.704 |      28.417 |       6.000 |       10,944 |        0 |
| Audit                  |      102 |   29.006 |   25.918 |   47.318 |   63.712 |   74.601 |       9.887 |      30.214 |       6.000 |        9,817 |        0 |

* The historical Patients row is superseded by the verified `patients-baseline-003` artifact documented above.

** The Notifications value represents the official populated representative workload selected for current tracking. An older benchmark also measured an empty notification feed and is retained only as historical evidence.

Historical measurements should be traced back to their corresponding benchmark artifacts where available.

Do not manufacture missing metrics from the historical table.

---

# 25. Populated Workload Rule

When an endpoint is expected to operate on populated production-like data, a populated synthetic workload should be preferred for the official performance baseline.

Examples include:

* patient lists
* appointments
* prescriptions
* inventory
* laboratory records
* notifications
* clinical conversations
* reports

An empty database can produce misleadingly low latency.

The benchmark dataset therefore exists to provide deterministic synthetic records for meaningful testing.

---

# 26. Benchmark Dataset

The benchmark dataset definition is:

```text
load_tests/benchmark_dataset.json
```

The seeding utility is:

```text
load_tests/seed_load_test_data.py
```

The provisioning utility for AI load users is:

```text
load_tests/provision_ai_load_users.py
```

The benchmark database remains synthetic and isolated from real production users.

---

# 27. Benchmark Data Integrity

Before an official benchmark is accepted, verify:

```text
1. Dataset exists
2. Dataset was seeded successfully
3. Expected records exist
4. Benchmark user exists
5. Authentication succeeds
6. Scenario reaches the intended route
7. Server log exists
8. Matching run ID exists in the server log
9. Workload records are correctly filtered
10. Server failures are zero
11. Locust exits successfully
12. Result artifact is valid
```

A successful Locust run by itself is not sufficient evidence of a valid benchmark.

---

# 28. Benchmark Validity

A benchmark is considered valid when the required integrity checks pass.

The runner tracks:

```text
locust_exit_code_zero
server_log_exists
matching_server_records_present
run_id_unique_before_run
server_failures_zero
```

The benchmark is valid only when the required checks pass.

---

# 29. Failed Benchmark Handling

If a benchmark fails integrity checks:

```text
DO NOT
```

treat it as an official performance baseline.

Investigate:

* authentication failures
* invalid synthetic data
* route mismatch
* missing logs
* duplicated run IDs
* application errors
* database errors
* Redis availability
* scenario logic
* Locust failures
* incorrect filtering
* instrumentation problems

Fix the benchmark infrastructure or underlying application issue before accepting a new baseline.

---

# 30. Benchmark Execution Workflow

The controlled workflow is:

```text
1. Start required infrastructure
2. Verify PostgreSQL
3. Verify Redis
4. Verify application
5. Verify synthetic benchmark data
6. Verify benchmark credentials
7. Generate a unique LOCUST_RUN_ID
8. Start a fresh server log
9. Execute the scenario
10. Collect Locust artifacts
11. Parse server-side performance records
12. Exclude setup traffic where appropriate
13. Validate the run
14. Store the JSON result
15. Inspect the metrics
16. Record the benchmark status
```

---

# 31. Optimization Workflow

Performance optimization should follow:

```text
Baseline
   ↓
Measure
   ↓
Identify bottleneck
   ↓
Change one controlled area
   ↓
Run tests
   ↓
Re-benchmark
   ↓
Compare
   ↓
Accept or revert
```

Do not optimize based only on intuition.

The benchmark should demonstrate that an optimization changes the measured bottleneck without introducing functional regressions.

---

# 32. Database Performance

Database performance is tracked using:

```text
db_query_count
db_time_ms
```

The main questions are:

```text
How many queries are executed per request?

How much time is spent in PostgreSQL?

Does query count scale with returned records?

Are there N+1 patterns?

Are indexes being used appropriately?

Does pagination remain bounded?

Does eager loading improve or worsen the workload?

Does tenant filtering remain efficient?

Does sorting remain deterministic and indexed?
```

---

# 33. Response Size

Response size is recorded because large payloads can affect:

* server serialization
* network transfer
* client latency
* memory consumption
* mobile performance
* Flutter rendering
* bandwidth usage

Large response sizes should therefore be considered alongside latency.

---

# 34. Locust Scenario Guidelines

Each scenario should:

* authenticate correctly
* use valid synthetic identities
* use realistic tenant context
* exercise real application routes
* avoid bypassing business rules
* avoid hardcoded production IDs when avoidable
* avoid destructive operations unless explicitly intended
* generate deterministic or controlled workloads where practical
* remain safe to execute repeatedly

---

# 35. Current Scenario Coverage

The current individual scenario implementation coverage is:

| Scenario               | Implementation | Official Individual Baseline |
| ---------------------- | -------------- | ---------------------------- |
| Authentication         | Complete       | Complete                     |
| Patients               | Complete       | Complete                     |
| Appointments           | Complete       | Complete                     |
| Consultations          | Complete       | Complete                     |
| Laboratory             | Complete       | Complete                     |
| Pharmacy               | Complete       | Complete                     |
| Prescriptions          | Complete       | Complete                     |
| Inventory              | Complete       | Complete                     |
| Billing                | Complete       | Complete                     |
| Wards                  | Complete       | Complete                     |
| Ambulance              | Complete       | Complete                     |
| HIE                    | Complete       | Complete                     |
| Notifications          | Complete       | Complete                     |
| Internal Clinical Chat | Complete       | Complete                     |
| Reports                | Complete       | Complete                     |
| Profile                | Complete       | Complete                     |
| Settings               | Complete       | Complete                     |
| User Devices           | Complete       | Complete                     |
| Asset Control          | Complete       | Complete                     |
| Access Control         | Complete       | Complete                     |
| Audit                  | Complete       | Complete                     |
| Clinic                 | Complete       | Pending                      |
| Staff                  | Complete       | Pending                      |
| Dashboard              | Complete       | Pending                      |
| AI                     | Complete       | Pending                      |

Therefore:

```text
Scenario implementation:
25 / 25

Official individual baselines:
21 / 25
```

---

# 36. Remaining Individual Baselines

The remaining individual baseline targets are:

## Clinic

Scenario:

```text
load_tests/scenarios/clinic.py
```

Status:

```text
Implemented
Not individually benchmarked
```

## Staff

Scenario:

```text
load_tests/scenarios/staff.py
```

Status:

```text
Implemented
Not individually benchmarked
```

## Dashboard

Scenario:

```text
load_tests/scenarios/dashboard.py
```

Status:

```text
Implemented
Not individually benchmarked
```

## AI

Scenario:

```text
load_tests/scenarios/locust_ai.py
```

Status:

```text
Implemented
Not individually benchmarked
```

These are benchmark targets, not missing implementation targets.

---

# 37. System-Wide Mixed Workload

The system-wide benchmark is a separate phase from the individual module baselines.

Its purpose is to answer questions such as:

```text
How does the complete application behave under concurrent mixed traffic?

Which modules consume the most database time?

Which workloads create contention?

How does Redis behave under mixed traffic?

Do authentication, clinical, administrative, reporting,
notification and communication workloads interfere with one another?

Does latency remain stable as concurrency increases?

Which endpoints become bottlenecks under realistic workload mixing?
```

The system-wide workload should not simply execute every existing scenario simultaneously.

It should represent a deliberate distribution of application activity.

The workload composition must be designed from the actual current scenario implementations.

---

# 38. System-Wide Workload Design Principles

The mixed workload should eventually account for multiple workload categories such as:

```text
Authentication
Patient access
Appointments
Clinical workflows
Laboratory
Pharmacy
Prescriptions
Inventory
Billing
Ward operations
Ambulance operations
HIE
Notifications
Internal Clinical Chat
Reports
Profile
Settings
User Devices
Asset Control
Access Control
Audit
Dashboard
AI
```

The exact request distribution should be documented before execution.

The goal is not to make every module receive equal traffic.

The goal is to model realistic concurrent system activity.

---

# 39. System-Wide Benchmark Integrity

The system-wide benchmark should preserve the same principles as individual benchmarks:

```text
Unique run ID
Fresh server log
Dedicated synthetic users
Valid authentication
Real tenant isolation
Real authorization
Real application services
Real database
Real Redis
Server-side instrumentation
Locust metrics
Independent verification
```

The mixed benchmark must also identify the contribution of individual workloads so bottlenecks can be traced back to their originating scenario.

---

# 40. Performance Regression Tracking

After optimization, compare:

```text
baseline
vs
optimized
```

using:

* average latency
* p50
* p95
* p99
* maximum latency
* DB time
* DB queries/request
* response size
* throughput
* failures

A change should not be considered an improvement merely because one metric decreases.

For example:

```text
Latency ↓
but
DB queries ↑
```

requires investigation.

Likewise:

```text
Average latency ↓
but
P99 ↑ significantly
```

requires investigation.

---

# 41. Important Benchmark Rule

Do not chase benchmark numbers at the expense of architecture.

Clinic System Pro v5 is designed around:

```text
Authentication
Authorization
Tenant Isolation
Validation
Transactions
Auditability
Database Integrity
Security
Observability
Scalability
```

Performance optimization must preserve those guarantees.

---

# 42. Current Achievement Summary

```text
Clinic System Pro v5 Load Testing

Individual scenario implementations:
25 / 25

Official individual baselines:
21 / 25

Remaining individual baselines:
4

Remaining individual baseline targets:
- Clinic
- Staff
- Dashboard
- AI

System-wide mixed workload:
Not yet implemented

System-wide benchmark:
Not yet executed
```

---

# 43. Current Phase

The load-testing project has completed the initial individual benchmark foundation.

The current phase is:

```text
STEP 6
Design and execute the true system-wide mixed workload
```

Before execution, the existing scenario implementations should be inspected to determine:

```text
- what each scenario actually requests
- authentication/setup behavior
- read/write ratios
- endpoint frequency
- database intensity
- Redis usage
- cross-module dependencies
- realistic concurrency distribution
- AI workload characteristics
- administrative vs clinical traffic
```

The system-wide workload should then be designed from those verified characteristics.

---

# 44. Roadmap

```text
1. Fix / verify PostgreSQL enum and schema alignment
        ✓

2. Run benchmark seeder successfully
        ✓

3. Verify benchmark manifest and database counts
        ✓

4. Decide required dataset scale
        ✓

5. Implement central performance baseline runner/report
        ✓

6. Design and execute true system-wide mixed workload
        NEXT

7. Analyze system-wide bottlenecks

8. Optimize identified bottlenecks

9. Re-run targeted benchmarks

10. Re-run system-wide benchmark

11. Load / stress testing

12. Production readiness performance review
```

---

# 45. Benchmark Rules of Record

The following rules govern official benchmark results:

```text
1. Use synthetic benchmark identities.

2. Use a unique run ID.

3. Use a fresh server log.

4. Use the standard benchmark profile unless documented otherwise.

5. Server-side metrics are the primary application performance source.

6. Locust metrics are supplementary client-side evidence.

7. Exclude setup authentication from non-auth module measurements.

8. Prefer populated synthetic workloads for populated production-like endpoints.

9. Do not modify production logic solely to improve benchmark results.

10. Do not accept a benchmark with integrity failures.

11. Do not overwrite a verified benchmark with an unverified run.

12. Preserve historical benchmark artifacts.

13. Record methodology changes explicitly.

14. Optimize only after establishing a valid baseline.

15. Re-benchmark after meaningful performance changes.

16. Preserve security, authorization, tenant isolation, validation,
    transactions and audit behavior throughout performance testing.
```

---

# 46. Final Current Status

```text
LOAD TESTING STATUS

Individual scenario implementation:
25 / 25 complete

Official individual baselines:
21 / 25 complete

Individual baselines remaining:
4

System-wide mixed workload:
Not yet implemented

System-wide benchmark:
Not yet executed

Next:
Step 6 — Design and execute the true system-wide mixed workload
```

The benchmark infrastructure is now ready for the system-wide workload design phase.

The next step is **inspection and workload planning first**, followed by execution only after the mixed workload has been reviewed and agreed upon.
