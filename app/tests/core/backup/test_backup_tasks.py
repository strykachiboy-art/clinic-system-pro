from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.backup.backup_retention import (
    BackupRetentionError,
)
from app.core.backup.backup_service import (
    BackupServiceError,
)
from app.core.backup.backup_tasks import (
    run_backup_retention,
    run_scheduled_backup,
)


def test_run_scheduled_backup_creates_and_verifies_backup(
    monkeypatch,
):
    backup_result = {
        "success": True,
        "backup_id": "backup-001",
        "backup_path": (
            "/tmp/backup-001"
        ),
        "database": {
            "success": True,
        },
        "files": {
            "success": True,
        },
    }

    verification_result = Mock(
        success=True,
        database=Mock(
            valid=True,
            backup_path=(
                "/tmp/backup-001/database.dump"
            ),
            size_bytes=128,
            sha256="a" * 64,
        ),
        files=Mock(
            valid=True,
            manifest_path=(
                "/tmp/backup-001/files/manifest.json"
            ),
            file_count=2,
            total_size_bytes=256,
            manifest_sha256="b" * 64,
        ),
        cross_system_valid=True,
    )

    observed = {
        "backup_called": False,
        "verify_called": False,
    }

    def fake_backup():
        observed[
            "backup_called"
        ] = True

        return backup_result

    def fake_verify(**kwargs):
        observed[
            "verify_called"
        ] = True

        assert kwargs[
            "backup_path"
        ] == (
            "/tmp/backup-001"
        )

        assert kwargs[
            "database_metadata"
        ] == {
            "success": True,
        }

        assert kwargs[
            "file_metadata"
        ] == {
            "success": True,
        }

        return verification_result

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.create_full_backup",
        fake_backup,
    )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.verify_full_backup",
        fake_verify,
    )

    result = run_scheduled_backup()

    assert result["success"] is True
    assert result["backup_id"] == (
        "backup-001"
    )
    assert result[
        "verification"
    ]["success"] is True

    assert observed[
        "backup_called"
    ] is True

    assert observed[
        "verify_called"
    ] is True


def test_run_scheduled_backup_fails_on_unsuccessful_backup(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.backup.backup_tasks.create_full_backup",
        lambda: {
            "success": False,
        },
    )

    with pytest.raises(
        BackupServiceError,
        match="unsuccessful backup",
    ):
        run_scheduled_backup()


def test_run_scheduled_backup_fails_when_backup_metadata_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.backup.backup_tasks.create_full_backup",
        lambda: {
            "success": True,
            "backup_id": "backup-001",
            "backup_path": (
                "/tmp/backup-001"
            ),
        },
    )

    with pytest.raises(
        BackupServiceError,
        match="missing database metadata",
    ):
        run_scheduled_backup()


def test_run_scheduled_backup_propagates_verification_failure(
    monkeypatch,
):
    from app.core.backup.backup_verification import (
        BackupVerificationError,
    )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.create_full_backup",
        lambda: {
            "success": True,
            "backup_id": "backup-001",
            "backup_path": (
                "/tmp/backup-001"
            ),
            "database": {
                "success": True,
            },
            "files": {
                "success": True,
            },
        },
    )

    def fail_verification(**kwargs):
        raise BackupVerificationError(
            "corrupted artifact"
        )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.verify_full_backup",
        fail_verification,
    )

    with pytest.raises(
        BackupServiceError,
        match="verification failed",
    ):
        run_scheduled_backup()


def test_run_backup_retention_uses_configured_root(
    app,
    monkeypatch,
):
    observed = {
        "backup_root": None,
    }

    app.config[
        "BACKUP_ROOT"
    ] = (
        "C:/clinic-backups"
    )

    class Result:
        success = True
        retention_days = 30
        minimum_recovery_points = 1
        cutoff_at = (
            "2026-08-25T00:00:00+00:00"
        )
        scanned_count = 10
        expired_count = 3
        protected_count = 1
        deleted_count = 2
        preserved_count = 8

    def fake_retention(**kwargs):
        observed[
            "backup_root"
        ] = kwargs[
            "backup_root"
        ]

        return Result()

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.apply_backup_retention",
        fake_retention,
    )

    with app.app_context():
        result = run_backup_retention()

    assert result["success"] is True
    assert observed[
        "backup_root"
    ] == "C:/clinic-backups"

    assert result[
        "deleted_count"
    ] == 2


def test_run_backup_retention_uses_default_root(
    app,
    monkeypatch,
):
    app.config.pop(
        "BACKUP_ROOT",
        None,
    )

    observed = {
        "backup_root": None,
    }

    class Result:
        success = True
        retention_days = 30
        minimum_recovery_points = 1
        cutoff_at = (
            "2026-08-25T00:00:00+00:00"
        )
        scanned_count = 0
        expired_count = 0
        protected_count = 0
        deleted_count = 0
        preserved_count = 0

    def fake_retention(**kwargs):
        observed[
            "backup_root"
        ] = kwargs[
            "backup_root"
        ]

        return Result()

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.apply_backup_retention",
        fake_retention,
    )

    with app.app_context():
        result = run_backup_retention()

    assert result["success"] is True

    assert observed[
        "backup_root"
    ].endswith(
        "/backups"
    ) or observed[
        "backup_root"
    ].endswith(
        "\\backups"
    )


def test_run_backup_retention_propagates_failure(
    app,
    monkeypatch,
):
    def fail_retention(**kwargs):
        raise BackupRetentionError(
            "retention failure"
        )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.apply_backup_retention",
        fail_retention,
    )

    with app.app_context():
        with pytest.raises(
            BackupServiceError,
            match="retention failed",
        ):
            run_backup_retention()