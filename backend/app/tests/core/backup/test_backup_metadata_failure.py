from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_service import (
    BackupServiceError,
    create_full_backup,
)


def test_create_full_backup_cleans_partial_backup_when_metadata_write_fails(
    app,
    tmp_path,
    monkeypatch,
):
    def fake_database_backup(**kwargs):
        output = Path(
            kwargs["output_path"]
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_bytes(
            b"database-artifact"
        )

        class Result:
            success = True
            database_name = "clinic_system"
            backup_size_bytes = 18
            backup_sha256 = "database-sha"
            format = "custom"

        return Result()

    def fake_file_backup(**kwargs):
        output = Path(
            kwargs["output_path"]
        )

        output.mkdir(
            parents=True,
            exist_ok=True,
        )

        (
            output
            / "manifest.json"
        ).write_bytes(
            b"file-manifest"
        )

        class Result:
            success = True
            file_count = 1
            total_size_bytes = 14
            manifest_sha256 = "files-sha"

        return Result()

    def fail_metadata_write(
        *args,
        **kwargs,
    ):
        from app.core.backup.backup_storage import (
            BackupStorageError,
        )

        raise BackupStorageError(
            "simulated metadata write failure"
        )

    monkeypatch.setattr(
        "app.core.backup.backup_service.write_metadata",
        fail_metadata_write,
    )

    with app.app_context():
        with pytest.raises(
            BackupServiceError,
            match="Unable to write full backup metadata",
        ):
            create_full_backup(
                database_url=(
                    "postgresql://backup"
                ),
                backup_root=tmp_path,
                storage_root=(
                    tmp_path
                    / "storage"
                ),
                database_backup_callable=(
                    fake_database_backup
                ),
                file_backup_callable=(
                    fake_file_backup
                ),
            )

    assert list(
        tmp_path.iterdir()
    ) == []
