# Clinic System Pro v5 — Load Testing

This README is the source of truth for how Clinic System Pro v5 load tests are created, executed, measured, and recorded.

## 1. Purpose

The load-testing system is used to measure server-side performance of Clinic System Pro v5 under a controlled, repeatable workload.

The primary performance metrics are taken from the application's structured server logs rather than relying only on Locust client-side timings.

The benchmark process is designed to remain lightweight enough for the development machine while still producing consistent comparative measurements.

---

## 2. Standard Benchmark Profile

Unless a specific test requires another configuration, use:

```text
Users:             10
Spawn rate:        2 users/second
Runtime:           30 seconds
Host:              http://127.0.0.1:5000
Locust:            2.46.5
Python:            3.12.10
```

Standard command:

```powershell
locust -f load_tests\scenarios\<module>.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:5000
```

Do not change the standard runtime to 60 seconds when creating the official module baseline unless there is a specific reason to do so.

---

## 3. Server Startup

Each official module benchmark should use a fresh server log.

Example for a module called `clinic`:

```powershell
Remove-Item .\logs\clinic_server.log -ErrorAction SilentlyContinue

python -c "import os; from app import create_app; from app.extensions import socketio; app=create_app('development'); app.config['DEBUG']=False; socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False, use_reloader=False)" 2>&1 | Tee-Object -FilePath .\logs\clinic_server.log
```

Keep this PowerShell window running.

Open a second PowerShell window for Locust.

---

## 4. Benchmark Credentials

The load tests use synthetic benchmark accounts.

Main control account:

```text
LOCUST_EMAIL=loadtest@clinicload.com
LOCUST_PASSWORD=LoadTestPassword123!
```

PowerShell:

```powershell
$env:LOCUST_EMAIL="loadtest@clinicload.com"
$env:LOCUST_PASSWORD="LoadTestPassword123!"
```

Benchmark staff and other synthetic load-test accounts should use valid non-reserved domains such as `example.com` because reserved `.local` and `.test` domains are rejected by the application's email validation.

Existing synthetic accounts were normalized to valid domains before the Access Control baseline was recorded. New load-test provisioners must not generate `.local` or `.test` email addresses.

Example:

```text
benchmark-staff-0001@example.com
BenchmarkPassword0001!
```

Do not use real production users for load testing.

---

## 5. Redis Requirement

Redis must be running because the application architecture uses Redis for authentication/revocation and related infrastructure.

The development Redis container is:

```text
redis-dev
```

Start it when necessary:

```powershell
docker start redis-dev
```

Verify:

```powershell
Test-NetConnection localhost -Port 6379
```

Expected:

```text
TcpTestSucceeded : True
```

---

## 6. Load Test IDs

Every official benchmark should have a unique `LOCUST_RUN_ID`.

Example:

```powershell
$env:LOCUST_RUN_ID="clinic-baseline-001"
```

The application writes this identifier into its structured performance logs.

The helper in:

```text
load_tests/common/benchmark.py
```

uses:

```python
get_load_test_id()
```

which returns `LOCUST_RUN_ID` when explicitly provided.

When no ID is provided, it generates an ID similar to:

```text
locust-20260922T083449Z-2c1e3853
```

For official benchmark records, prefer an explicit descriptive ID:

```text
<module>-baseline-001
```

Examples:

```text
authentication-baseline-001
notifications-baseline-002
clinic-baseline-001
```

---

## 7. Standard Scenario Structure

Most module scenarios follow this pattern:

```text
Locust user starts
        ↓
POST /api/v1/auth/login [setup]
        ↓
Access token received
        ↓
Module request executed repeatedly
        ↓
Response validated
        ↓
Server performance log recorded
```

The setup login request is required for authentication but should normally be distinguished from the module workload using:

```text
POST /api/v1/auth/login [setup]
```

The module request should have its own descriptive Locust name.

Example:

```text
GET /api/v1/clinics
```

---

## 8. Authentication Scenario

Authentication is different from most module benchmarks.

`authentication.py` repeatedly tests:

```text
POST /api/v1/auth/login
```

The login requests themselves are the workload.

Example:

```powershell
$env:LOCUST_EMAIL="loadtest@clinicload.com"
$env:LOCUST_PASSWORD="LoadTestPassword123!"
$env:LOCUST_RUN_ID="authentication-baseline-001"

locust -f load_tests\scenarios\authentication.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:5000
```

---

## 9. Populated Dataset Rule

A benchmark should represent the workload that the endpoint is expected to handle.

Empty datasets can produce misleadingly small response sizes and lower response times.

Example:

The original Notifications benchmark used the control admin account and returned an approximately 114-byte empty notification feed.

That result was preserved historically, but it was not used as the representative populated Notifications baseline.

The populated Notifications benchmark instead used a synthetic benchmark staff account that had seeded notifications.

That run returned approximately:

```text
24,363 bytes
```

and became the official representative Notifications baseline.

Asset Control was also benchmarked against a populated synthetic workload:

```text
50 synthetic assets
39,324-byte average response
```

Access Control was benchmarked against the populated user table:

```text
5,019 users
4,578-byte average response
```

Audit was benchmarked against the existing populated audit log dataset:

```text
120 successful requests
5,106-byte average response
```

Therefore:

```text
Representative populated workload > empty dataset workload
```

for official performance tracking when the endpoint is expected to operate on populated data.

---

## 10. Standard Locust Execution

Example:

```powershell
$env:LOCUST_EMAIL="loadtest@clinicload.com"
$env:LOCUST_PASSWORD="LoadTestPassword123!"
$env:LOCUST_RUN_ID="clinic-baseline-001"

locust -f load_tests\scenarios\clinic.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:5000
```

Check:

```text
# reqs
# fails
Avg
Min
Max
Med
req/s
failures/s
```

The Locust output is useful for client-side observation, but official module comparisons use server-side application metrics.

---

## 11. Server-Side Performance Logs

The application emits structured records similar to:

```text
performance.request load_test_id=<ID> method=GET route=<ROUTE> status=200 duration_ms=... response_size_bytes=... db_query_count=... db_time_ms=...
```

These fields are used for the official benchmark record.

Important fields:

```text
load_test_id
method
route
status
duration_ms
response_size_bytes
db_query_count
db_time_ms
```

---

## 12. Standard Server Metric Extraction

For a module using:

```text
<module>-baseline-001
```

and route:

```text
/api/v1/<endpoint>
```

use a PowerShell regex matching the exact `load_test_id`, method, and route.

Example for Notifications:

```powershell
$raw = Get-Content .\logs\notifications_server.log -Raw

$records = [regex]::Matches(
    $raw,
    'performance\.request\s+load_test_id=notifications-baseline-002\s+method=GET\s+route=/api/v1/notifications/\s+status=(?<status>\d+)\s+duration_ms=(?<duration>[0-9.]+)\s+response_size_bytes=(?<size>\d+)\s+db_query_count=(?<queries>\d+)\s+db_time_ms=(?<db>[0-9.]+)'
) | ForEach-Object {
    [pscustomobject]@{
        Status        = [int]$_.Groups['status'].Value
        DurationMs    = [double]$_.Groups['duration'].Value
        ResponseBytes = [int]$_.Groups['size'].Value
        DBQueries     = [int]$_.Groups['queries'].Value
        DBTimeMs      = [double]$_.Groups['db'].Value
    }
}
```

---

## 13. Percentile Calculation

Use the server-side durations sorted from smallest to largest.

Standard helper:

```powershell
function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$Percent
    )

    if ($Values.Count -eq 0) {
        return 0
    }

    $sorted = @($Values | Sort-Object)

    $index = [math]::Ceiling(
        $sorted.Count * $Percent
    ) - 1

    if ($index -lt 0) {
        $index = 0
    }

    if ($index -ge $sorted.Count) {
        $index = $sorted.Count - 1
    }

    return $sorted[$index]
}
```

Use:

```text
0.50 = p50
0.95 = p95
0.99 = p99
```

---

## 14. Standard Metrics To Record

For every completed official module baseline, record:

```text
Requests
Failures
HTTP status distribution
Min
Average
p50
p95
p99
Max
Average DB time
Maximum DB time
DB queries/request
Response size
```

Primary comparison columns:

```text
Requests
Failures
Min
Avg
p50
p95
p99
Max
Avg DB
Max DB
DB Queries
Response Size
```

---

## 15. Valid Benchmark Rules

A benchmark is valid when:

```text
1. The intended server instance was running.
2. The log file corresponds to the current run.
3. The load_test_id matches the benchmark.
4. The intended endpoint was exercised.
5. Authentication succeeded.
6. Requests completed normally.
7. Metrics were extracted from the correct server log.
8. The workload was representative of the intended dataset.
```

Do not record a benchmark when:

```text
- Authentication failed.
- The wrong log file was used.
- Stale records were accidentally included.
- The endpoint returned errors.
- The scenario never reached its main task.
- The workload was unintentionally empty when a populated workload was required.
```

Failed or invalid runs may be retained as diagnostic history but must not replace the official baseline.

---

## 16. Current Official Benchmark Record

Current server-side records:

| Module                 | Requests | Failures | Min (ms) | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) | Avg DB (ms) | Max DB (ms) | DB Queries | Response Size |
| ---------------------- | -------: | -------: | -------: | -------: | -------: | -------: | -------: | -------: | ----------: | ----------: | ---------: | ------------: |
| Authentication         |       62 |        0 |  303.611 |  457.101 |  374.284 |  897.693 | 1253.347 | 1253.347 |       3.849 |      12.676 |          4 |         810 B |
| Patients               |      121 |        0 |        — |   22.200 |        — |   34.541 |   51.761 |        — |           — |           — |          — |             — |
| Appointments           |      119 |        0 |        — |   19.916 |        — |   33.501 |   46.995 |        — |           — |           — |          — |             — |
| Consultations          |      120 |        0 |        — |   21.043 |        — |   37.365 |   61.146 |        — |           — |           — |          — |             — |
| Laboratory             |      116 |        0 |        — |   17.147 |        — |   23.843 |   38.093 |        — |           — |           — |          — |             — |
| Pharmacy               |      101 |        0 |        — |   15.111 |        — |   19.484 |   45.550 |        — |           — |           — |          — |             — |
| Prescriptions          |      128 |        0 |        — |   14.795 |        — |   20.774 |   27.231 |        — |           — |           — |          — |             — |
| Inventory              |      119 |        0 |        — |   19.011 |        — |   32.525 |   38.756 |        — |           — |           — |          — |             — |
| Billing                |      123 |        0 |        — |   18.547 |        — |   29.277 |   37.753 |        — |           — |           — |          — |             — |
| Wards                  |      116 |        0 |    8.159 |   11.813 |   11.346 |   17.600 |   26.214 |   41.785 |       3.275 |      10.829 |          4 |         353 B |
| Ambulance              |      125 |        0 |   13.546 |   20.717 |   17.285 |   35.591 |   47.211 |   78.131 |       4.970 |      21.622 |          5 |      28,365 B |
| HIE                    |      125 |        0 |    9.637 |   14.409 |   11.361 |   23.512 |   30.072 |  170.359 |       4.403 |      46.828 |          5 |          70 B |
| Notifications          |       95 |        0 |   11.661 |   21.046 |   19.055 |   35.135 |  141.105 |  141.105 |       5.100 |      44.656 |          4 |      24,363 B |
| Internal Clinical Chat |      130 |        0 |        — |   26.077 |        — |   37.512 |   48.636 |        — |           — |           — |          — |             — |
| Reports                |      123 |        0 |        — |   16.410 |        — |   27.218 |   35.528 |        — |           — |           — |          — |             — |
| Profile                |      105 |        0 |        — |   14.369 |        — |   22.253 |   24.831 |        — |           — |           — |          — |             — |
| Settings               |      119 |        0 |    7.692 |    9.560 |    8.405 |   16.172 |   20.143 |   20.874 |       2.720 |       5.579 |          4 |         352 B |
| User Devices           |      372 |        0 |    8.075 |   14.166 |   11.691 |   26.976 |   39.176 |   56.561 |       3.742 |      29.383 |          4 |     1,725.6 B |
| Asset Control          |      116 |        0 |   13.690 |   19.550 |   16.515 |   30.154 |   36.569 |   72.279 |       4.186 |      22.584 |          4 |      39,324 B |
| Access Control         |       91 |        0 |   19.966 |   35.629 |   36.423 |   56.537 |  154.991 |  154.991 |       4.891 |       8.967 |          4 |       4,578 B |
| Audit                  |      120 |        0 |   14.395 |   22.217 |   20.093 |   34.137 |   67.731 |   69.885 |      12.591 |      57.506 |          3 |       5,106 B |

A value of `—` means the detailed metric was not preserved in the historical benchmark record.

Recent completed benchmark IDs:

```text
user-devices-baseline-001
asset-control-baseline-001
access-control-baseline-001
audit-baseline-001
```

Recent workload notes:

```text
User Devices
- Read endpoint exercised: GET /api/v1/users/devices/
- 372 successful requests

Asset Control
- Endpoint exercised: GET /api/v1/assets
- Representative dataset: 50 synthetic assets
- Response size: 39,324 B

Access Control
- Endpoint exercised: GET /api/v1/access-control/users?page=1&per_page=50
- Representative dataset: 5,019 users
- Response size: 4,578 B
- Super-admin authentication succeeded

Audit
- Endpoint exercised: GET /api/v1/audit-logs?page=1&per_page=20
- 120 successful requests
- Response size: 5,106 B
- Average DB time: 12.591 ms
- Maximum DB time: 57.506 ms
- DB queries/request: 3
```

---

## 17. Important Historical Notifications Note

The old Notifications benchmark was:

```text
122 requests
10.517 ms average
14.224 ms p95
18.856 ms p99
114 B response
0 failures
```

That workload used the control account and produced an empty notification feed.

The official representative benchmark is now:

```text
notifications-baseline-002

95 requests
21.046 ms average
19.055 ms p50
35.135 ms p95
141.105 ms p99
141.105 ms max
5.100 ms average DB time
44.656 ms maximum DB time
4 DB queries
24,363 B response
0 failures
```

The old result should remain historical only.

---

## 18. Existing Scenario Files

Current scenario directory:

```text
load_tests/scenarios/
```

Known files:

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

---

## 19. Current Benchmark Progress

Completed official baselines:

```text
1. Authentication
2. Patients
3. Appointments
4. Consultations
5. Laboratory
6. Pharmacy
7. Prescriptions
8. Inventory
9. Billing
10. Wards
11. Ambulance
12. HIE
13. Notifications
14. Internal Clinical Chat
15. Reports
16. Profile
17. Settings
18. User Devices
19. Asset Control
20. Access Control
21. Audit
```

Remaining benchmark targets:

```text
1. Clinic
2. Staff
3. Dashboard
4. AI
```

Current status:

```text
21 completed
4 remaining
25 scenario targets total
```

The current scenario-creation phase has been completed for all implemented targets except the remaining implementation targets listed below.

---

## 20. Scenario Implementation Status

The following scenario files now contain implemented load-test workloads and have completed official baselines:

```text
load_tests/scenarios/authentication.py
load_tests/scenarios/patients.py
load_tests/scenarios/appointments.py
load_tests/scenarios/consultations.py
load_tests/scenarios/laboratory.py
load_tests/scenarios/pharmacy.py
load_tests/scenarios/prescriptions.py
load_tests/scenarios/inventory.py
load_tests/scenarios/billing.py
load_tests/scenarios/wards.py
load_tests/scenarios/ambulance.py
load_tests/scenarios/hie.py
load_tests/scenarios/notifications.py
load_tests/scenarios/chat.py
load_tests/scenarios/reports.py
load_tests/scenarios/profile.py
load_tests/scenarios/settings.py
load_tests/scenarios/user_devices.py
load_tests/scenarios/asset_control.py
load_tests/scenarios/access_control.py
load_tests/scenarios/audit.py
```

The remaining scenario files requiring implementation are:

```text
load_tests/scenarios/clinic.py
load_tests/scenarios/staff.py
```

These should be implemented against the actual API routes and response contracts rather than guessed endpoints.

---

## 21. Implemented But Not Yet Benchmarked

These scenario files already contain load-test code but still need official baseline execution:

```text
load_tests/scenarios/dashboard.py
load_tests/scenarios/locust_ai.py
```

The remaining official benchmark queue is therefore:

```text
Clinic
Staff
Dashboard
AI
```

All other current scenario targets have completed their official baseline.

---

## 22. Recommended Workflow For Every New Module

Use this sequence:

```text
1. Inspect the module routes/services/schemas.
2. Identify the correct read-heavy or representative benchmark endpoint.
3. Create or update load_tests/scenarios/<module>.py.
4. Ensure all synthetic credentials use valid, non-reserved email domains.
5. Validate the Python file.
6. Start a fresh server.
7. Create a fresh module server log.
8. Set synthetic benchmark credentials.
9. Set a unique LOCUST_RUN_ID.
10. Run 10 users / 2 spawn rate / 30 seconds.
11. Confirm Locust had no failures.
12. Extract server-side metrics from the matching log.
13. Verify HTTP status distribution.
14. Verify the workload is populated/representative.
15. Record the official baseline.
16. Do not replace a valid baseline with an invalid or empty run.
```

---

## 23. Python Syntax Check

Before running a newly created scenario:

```powershell
python -m py_compile load_tests\scenarios\<module>.py
```

No output means compilation succeeded.

---

## 24. Example Complete Clinic Workflow

Start server:

```powershell
Remove-Item .\logs\clinic_server.log -ErrorAction SilentlyContinue

python -c "import os; from app import create_app; from app.extensions import socketio; app=create_app('development'); app.config['DEBUG']=False; socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False, use_reloader=False)" 2>&1 | Tee-Object -FilePath .\logs\clinic_server.log
```

Second PowerShell:

```powershell
$env:LOCUST_EMAIL="loadtest@clinicload.com"
$env:LOCUST_PASSWORD="LoadTestPassword123!"
$env:LOCUST_RUN_ID="clinic-baseline-001"

locust -f load_tests\scenarios\clinic.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:5000
```

Then extract:

```text
performance.request
load_test_id=clinic-baseline-001
method=GET
route=/api/v1/clinics
```

Record:

```text
Requests
Failures
Min
Avg
p50
p95
p99
Max
Avg DB
Max DB
DB Queries
Response Size
```

---

## 25. Important Interpretation Rule

Locust client-side response times and server-side application timings are not interchangeable.

Locust measures the client-observed request duration.

The application performance logger measures server-side request processing.

The official Clinic System Pro architecture benchmark board uses:

```text
SERVER-SIDE APPLICATION METRICS
```

for the primary module comparison.

Locust remains important for:

```text
request count
client failures
client-observed latency
throughput
load generation behavior
```

---

## 26. Benchmark Integrity

Do not modify production business logic just to make a benchmark faster.

When a benchmark exposes a performance problem:

```text
1. Verify the workload.
2. Verify the log.
3. Verify the route.
4. Verify database query count/time.
5. Verify authentication.
6. Investigate the actual implementation.
7. Optimize only when justified.
8. Re-run the same benchmark profile.
9. Compare against the previous baseline.
```

The purpose of this system is to measure the architecture honestly and consistently.

---

## 27. Quick Command Reference

Start Redis:

```powershell
docker start redis-dev
```

Check Redis:

```powershell
Test-NetConnection localhost -Port 6379
```

Set credentials:

```powershell
$env:LOCUST_EMAIL="loadtest@clinicload.com"
$env:LOCUST_PASSWORD="LoadTestPassword123!"
```

Set run ID:

```powershell
$env:LOCUST_RUN_ID="<module>-baseline-001"
```

Run benchmark:

```powershell
locust -f load_tests\scenarios\<module>.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:5000
```

Syntax check:

```powershell
python -m py_compile load_tests\scenarios\<module>.py
```

---

## 28. Source Of Truth

For future load-testing work, this README should be treated as the operational reference for:

```text
benchmark profile
server startup
credentials
run IDs
scenario conventions
metric extraction
benchmark validity
baseline records
remaining scenarios
```

When continuing load-testing work in a new conversation, read this file first before creating or modifying benchmark scenarios.
