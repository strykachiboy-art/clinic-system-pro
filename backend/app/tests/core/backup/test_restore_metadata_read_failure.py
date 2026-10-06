from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
)
from app.core.backup.restore_service import (
    RestoreError,
    restore_full_backup,
)


def test_restore_full_backup_fails_closed_on_metadata_read_failure(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = (
        tmp_path
        / "backup"
    )

    backup_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_path = (
        backup_root
        / "metadata.json"
    )

    metadata_path.write_text(
        '{"success":true}',
        encoding="utf-8",
    )

    pg_restore_called = {
        "called": False,
    }

    def fail_pg_restore(*args, **kwargs):
        pg_restore_called[
            "called"
        ] = True

        raise AssertionError(
            "pg_restore must not run when metadata cannot be read"
        )

    def fail_metadata_read(*args, **kwargs):
        raise BackupStorageError(
            "simulated metadata read failure"
        )

    monkeypatch.setattr(
        "app.core.backup.restore_service.read_metadata",
        fail_metadata_read,
    )

    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        fail_pg_restore,
    )

    with app.app_context():
        with pytest.raises(
            RestoreError,
            match="Unable to read backup metadata",
        ):
            restore_full_backup(
                backup_path=backup_root,
                database_url=(
                    "postgresql://backup@localhost/"
                    "clinic_system"
                ),
                storage_root=(
                    tmp_path
                    / "restored-storage"
                ),
            )

    assert pg_restore_called[
        "called"
    ] is False

    assert metadata_path.exists()
