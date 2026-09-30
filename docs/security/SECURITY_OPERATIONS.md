# Security Operations Runbook

## Events Requiring Monitoring

- repeated authentication failures
- repeated rate-limit violations
- privilege changes
- clinic transfers
- emergency access grants
- emergency access denials
- emergency access revocations
- audit write failures
- token revocation failures
- cross-tenant authorization denials
- webhook signature failures
- provider authentication failures
- Redis fail-closed events
- database interruption events
- backup verification failures
- restore drill failures
- TLS certificate renewal failures
- unexpected production configuration changes

## Operational Response

1. Preserve relevant audit and observability evidence.
2. Identify affected tenant and actor.
3. Revoke affected credentials where required.
4. Disable compromised integration credentials where required.
5. Verify tenant boundaries.
6. Verify audit continuity.
7. Assess whether clinical or financial records were exposed.
8. Preserve incident timestamps and request identifiers.
9. Apply minimal remediation.
10. Add a regression test before closing the engineering defect.

## Privileged-Action Review

Security-sensitive operations should be periodically reviewed for:

- unexpected actor
- unexpected clinic
- unusual frequency
- emergency-access concentration
- repeated authorization failures
- unusual integration failures

## Secret Rotation

JWT/application secrets must be rotated through the production deployment
process.

Changing JWT_SECRET_KEY invalidates existing JWT signatures and therefore
requires coordinated application deployment.

Integration and webhook secrets must be rotated at the provider and in the
corresponding clinic integration configuration.

Encryption-key rotation must follow a dedicated migration procedure and must
not be performed by simply replacing an active encryption key.

### Secret Rotation Drill

Perform a documented secret-rotation drill at least annually and after any
material authentication or integration-secret handling change.

The drill must verify:

1. A replacement secret is generated through the approved secret-management
   process.
2. The replacement secret is deployed without exposing its value in source
   control, logs, test output, or deployment artifacts.
3. Existing credentials affected by the rotation are invalidated as expected.
4. Authentication and affected integrations continue to operate with the
   replacement secret.
5. Failure and rollback behavior are verified where supported.
6. Audit and deployment evidence records the rotation event without recording
   secret values.

Production credentials must never be used for a rotation drill unless the
drill is an approved production operation.

## TLS Certificate Renewal

Production TLS certificates must have an owner, an expiry date, and a
documented renewal procedure.

Certificate expiry must be monitored continuously where deployment
infrastructure supports automated certificate monitoring.

Perform renewal before expiry with sufficient operational margin to allow
validation and rollback. The target renewal window should be no later than
30 days before certificate expiry.

After renewal, verify:

- certificate validity and hostname coverage
- complete certificate chain
- HTTPS connectivity
- reverse-proxy/application connectivity
- health endpoints
- Socket.IO connectivity where applicable

Record the certificate renewal date, expiry date, deployment version, and
validation evidence.

Emergency certificate replacement must follow the same evidence and
rollback requirements as a planned renewal.

## Configuration Drift

Production configuration must be treated as controlled deployment state.

The expected configuration contract must be maintained in version-controlled
documentation and deployment configuration, while secret values remain in
the approved secret-management system.

Configuration drift reviews must be performed:

- before production deployment
- after infrastructure or dependency changes
- after security-sensitive configuration changes
- at least quarterly

The review must compare the running configuration against the approved
production contract and identify:

- unexpected environment variables
- missing required variables
- changed security settings
- changed database or Redis endpoints
- unexpected CORS origins
- changed TLS or reverse-proxy settings
- unexpected feature or operational flags

Unexpected drift must be investigated, documented, and either reverted or
formally approved before the next deployment.

Secret values must never be included in drift reports. Record only the
configuration key, expected state, observed state where safe, affected
component, remediation, and approval/evidence reference.

## Incident Evidence

Keep:

- relevant audit events
- structured application logs
- request identifiers
- deployment version
- migration revision
- security findings
- remediation commits
- regression test evidence
- secret-rotation drill evidence
- TLS certificate renewal evidence
- configuration-drift review evidence
