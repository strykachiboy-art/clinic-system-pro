from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.core.backup.backup_service import (
    BackupServiceError,
    create_full_backup,
)
from app.core.backup.backup_storage import (
    BackupStorageError,
)


@dataclass(frozen=True)
class FakeDatabaseBackupResult:
    success: bool = True
    database_name: str = "clinic_system"
    backup_size_bytes: int = 8
    backup_sha256: str = "database-sha"
    format: str = "custom"


@dataclass(frozen=True)
class FakeFileBackupResult:
    success: bool = True
    file_count: int = 1
    total_size_bytes: int = 7
    manifest_sha256: str = "files-sha"


def test_create_full_backup_cleans_partial_backup_when_metadata_checksum_fails(
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
            b"database"
        )

        return FakeDatabaseBackupResult()

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
            b"manifest"
        )

        return FakeFileBackupResult()

    observed = {
        "metadata_path": None,
    }

    def fail_metadata_checksum(
        path,
    ):
        observed[
            "metadata_path"
        ] = Path(
            path
        )

        raise BackupStorageError(
            "simulated metadata checksum failure"
        )

    monkeypatch.setattr(
        "app.core.backup.backup_service.calculate_sha256",
        fail_metadata_checksum,
    )

    with app.app_context():
        with pytest.raises(
            BackupStorageError,
            match="simulated metadata checksum failure",
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

    assert observed[
        "metadata_path"
    ] is not None

    assert not any(
        tmp_path.iterdir()
    )
