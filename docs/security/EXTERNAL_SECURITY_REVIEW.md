# External Security Review Scope

This document defines the independent/adversarial testing scope.

A successful internal regression suite does not constitute an independent
penetration test.

## Required Test Areas

### Authentication
- credential abuse
- token replay
- refresh-token abuse
- logout/revocation
- inactive accounts
- OAuth state replay and race behavior

### Authorization
- IDOR
- cross-clinic access
- role escalation
- privileged-role modification
- forged actor IDs
- forged clinic IDs

### Emergency Access
- unauthorized requester
- self-approval
- excessive scope
- excessive duration
- expired access reuse
- cross-clinic patient access
- revocation bypass

### Clinical Resources
- patient
- consultation
- laboratory
- pharmacy
- prescription
- ward
- ambulance
- HIE

### Realtime
- unauthorized room subscription
- participant removal races
- stale authorization
- message delivery across tenants

### Files
- path traversal
- object ownership bypass
- content-type abuse
- filename/path manipulation
- oversized payloads

### Integrations
- webhook forgery
- signature bypass
- credential misuse
- external identifier abuse
- SSRF against configurable endpoints

### Audit
- mutation attempts
- actor spoofing
- tenant spoofing
- redaction bypass
- transaction rollback behavior

### Availability
- authentication flooding
- API flooding
- rate-limit bypass
- oversized payloads
- connection exhaustion

## Evidence Required

Every finding must contain:

- reproduction steps
- affected endpoint/resource
- attacker privilege level
- impact
- root cause
- remediation
- regression test
- retest result

No certification or compliance conclusion should be drawn from this document alone.
