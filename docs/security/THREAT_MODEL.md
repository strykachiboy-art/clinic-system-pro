# Clinic System Pro v5 - Security Threat Model

## Security Objective

Protect identity, tenant boundaries, clinical information, financial information,
medication safety, emergency access, audit integrity, and operational infrastructure.

## Primary Trust Boundaries

1. Internet / untrusted client → API
2. Authenticated client → authorization layer
3. User → tenant-scoped resources
4. Background worker → tenant-scoped work
5. Realtime socket → authorized conversation
6. Application → Redis
7. Application → PostgreSQL
8. Application → external payment/integration providers
9. Application → HIE provider adapters
10. Application → AI providers
11. Backup source → restore environment

## Threat Classes

### Identity
- credential stuffing
- token replay
- revoked-token reuse
- refresh-token abuse
- OAuth state replay/race
- inactive-user access

### Authorization
- IDOR
- cross-clinic access
- role escalation
- forged actor identity
- client-controlled clinic selection
- emergency-access scope abuse

### Data
- sensitive-data leakage
- unsafe file access
- audit tampering
- unintended caching
- backup exposure
- offline data exposure

### Integrations
- forged webhooks
- invalid signatures
- provider credential abuse
- malicious external identifiers
- unsafe external endpoints / SSRF

### Realtime
- stale room authorization
- unauthorized message delivery
- cross-clinic subscription
- participant removal race

### Availability
- Redis failure
- database interruption
- worker failure
- queue failure
- rate-limit abuse
- resource exhaustion

### Recovery
- unsafe restore target
- stale authentication after restore
- incomplete outbox recovery
- migration mismatch
- corrupted backup artifact

## Security Design Principles

- server-authoritative identity
- server-authoritative tenant context
- least privilege
- fail closed
- explicit validation
- transaction integrity
- auditable privileged actions
- bounded emergency access
- PostgreSQL as application source of truth
- evidence before production claims

## Final Review Requirement

Security architecture changes should be driven by a reproducible defect,
documented threat, penetration-test finding, operational requirement, or
measured production risk rather than speculative complexity.

### Encryption
- integration credential ciphertext disclosure
- wrong integration encryption key version
- accidental loss of legacy decryption keys
- backup encryption key compromise
- backup/integration key-domain confusion
- ciphertext corruption or truncation
- plaintext backup leakage during encryption or restore

### Recovery
- loss of the active backup encryption key
- unsafe recovery-secret custody
- restore using the wrong key
- incomplete temporary plaintext cleanup
- restore success reported without post-restore verification

## Encryption Trust Boundaries

1. Integration credential store -> integration encryption domain
2. Database backup source -> backup encryption domain
3. Encrypted backup artifact -> restore environment
4. Temporary plaintext restore -> pg_restore

## Encryption Security Controls

- fail closed on missing, invalid, or wrong keys
- record encryption key version for protected integration credentials
- keep integration and backup encryption keys in separate domains
- verify encrypted backup checksum before restore
- never fall back from encrypted restore to plaintext restore
- use a unique temporary restore location for decrypted database content
- remove temporary plaintext restore content after restore completion or failure
- keep backup encryption keys out of metadata and backup artifacts

## Encryption Evidence Boundary

The repository currently provides VERIFIED evidence for encrypted backup
generation, encrypted restore, key recovery, and crypto failure injection.

Production secret custody, key-management infrastructure, and production
operation remain deployment responsibilities.
