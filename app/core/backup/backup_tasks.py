from __future__ import annotations

from typing import Any

from app.core.backup.backup_service import (
    BackupServiceError,
    create_full_backup,
)
from app.core.backup.backup_retention import (
    BackupRetentionError,
    apply_backup_retention,
)
from app.core.backup.backup_verification import (
    BackupVerificationError,
    verify_full_backup,
)
from app.extensions import celery


def _verify_backup_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get(
        "success"
    ) is not True:
        raise BackupServiceError(
            "Backup task received an unsuccessful backup result"
        )

    backup_path = result.get(
        "backup_path"
    )

    database_metadata = result.get(
        "database"
    )

    file_metadata = result.get(
        "files"
    )

    if not isinstance(
        backup_path,
        str,
    ) or not backup_path.strip():
        raise BackupServiceError(
            "Backup result is missing backup_path"
        )

    if not isinstance(
        database_metadata,
        dict,
    ):
        raise BackupServiceError(
            "Backup result is missing database metadata"
        )

    if not isinstance(
        file_metadata,
        dict,
    ):
        raise BackupServiceError(
            "Backup result is missing file metadata"
        )

    try:
        verification = verify_full_backup(
            backup_path=backup_path,
            database_metadata=(
                database_metadata
            ),
            file_metadata=(
                file_metadata
            ),
        )
    except BackupVerificationError as exc:
        raise BackupServiceError(
            f"Scheduled backup verification failed: {exc}"
        ) from exc

    return {
        "success": True,
        "backup_id": result.get(
            "backup_id"
        ),
        "backup_path": backup_path,
        "verification": {
            "success": verification.success,
            "database": {
                "valid": (
                    verification.database.valid
                ),
                "backup_path": (
                    verification.database.backup_path
                ),
                "size_bytes": (
                    verification.database.size_bytes
                ),
                "sha256": (
                    verification.database.sha256
                ),
            },
            "files": {
                "valid": (
                    verification.files.valid
                ),
                "manifest_path": (
                    verification.files.manifest_path
                ),
                "file_count": (
                    verification.files.file_count
                ),
                "total_size_bytes": (
                    verification.files.total_size_bytes
                ),
                "manifest_sha256": (
                    verification.files.manifest_sha256
                ),
            },
            "cross_system_valid": (
                verification.cross_system_valid
            ),
        },
    }


@celery.task(
    name="run_scheduled_backup",
)
def run_scheduled_backup() -> dict[str, Any]:
    result = create_full_backup()

    return _verify_backup_result(
        result
    )


@celery.task(
    name="run_backup_retention",
)
@celery.task(
    name="run_backup_retention",
)
def run_backup_retention() -> dict[str, Any]:
    from flask import current_app

    backup_root = current_app.config.get(
        "BACKUP_ROOT"
    )

    if not backup_root:
        backup_root = (
            current_app.instance_path
            + "/backups"
        )

    try:
        result = apply_backup_retention(
            backup_root=backup_root,
        )

    except BackupRetentionError as exc:
        raise BackupServiceError(
            f"Scheduled backup retention failed: {exc}"
        ) from exc

    return {
        "success": result.success,
        "retention_days": (
            result.retention_days
        ),
        "minimum_recovery_points": (
            result.minimum_recovery_points
        ),
        "cutoff_at": result.cutoff_at,
        "scanned_count": (
            result.scanned_count
        ),
        "expired_count": (
            result.expired_count
        ),
        "protected_count": (
            result.protected_count
        ),
        "deleted_count": (
            result.deleted_count
        ),
        "preserved_count": (
            result.preserved_count
        ),
    }