# Backup / Restore Security Drill

The repository contains a controlled backup and restore drill for validating database recovery, filesystem recovery, authentication recovery, chat outbox recovery, and post-restore integrity.

## Preconditions

* completed full backup
* dedicated PostgreSQL restore target
* dedicated filesystem restore target
* source database and target database must be different
* source storage and target storage must be different
* `pg_restore` available
* `psql` available
* operator authorization
* restore target must not contain existing application data

## Execute

```powershell
$env:RESTORE_DRILL_CONFIRMATION="RESTORE_DRILL_APPROVED"
$env:RESTORE_DRILL_TARGET_DATABASE_URL="<dedicated-postgres-target>"

python -m app.core.backup.restore_drill `
    --backup-path "<backup-directory>" `
    --target-storage-root "<dedicated-storage-target>" `
    --report-path "artifacts/restore-drill-report.json"
```

## Verification Evidence Fields

The restore drill report must contain these successful recovery indicators:

* `authentication_invalidated: true`
* `outbox_recovery_completed: true`
* `post_restore_verification_completed: true`
* `success: true`

Authentication recovery is complete when `authentication_invalidated: true`.

Post-restore verification is complete when `post_restore_verification_completed: true`.

A successful restore drill is indicated by `success: true`.