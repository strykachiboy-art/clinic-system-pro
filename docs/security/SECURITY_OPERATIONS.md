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
