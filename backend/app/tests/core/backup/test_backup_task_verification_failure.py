from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_service import (
    BackupServiceError,
)
from app.core.backup.backup_tasks import (
    run_scheduled_backup,
)
from app.core.backup.backup_verification import (
    BackupVerificationError,
)


def test_scheduled_backup_verification_failure_cleans_untrusted_backup(
    tmp_path,
    monkeypatch,
):
    backup_root = (
        tmp_path
        / "backup-20261006T000000Z-test"
    )

    backup_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        backup_root
        / "database.dump"
    ).write_bytes(
        b"untrusted-backup"
    )

    (
        backup_root
        / "metadata.json"
    ).write_text(
        '{"success":true}',
        encoding="utf-8",
    )

    def fake_create_full_backup():
        return {
            "success": True,
            "backup_id": "backup-test-001",
            "backup_path": str(
                backup_root
            ),
            "database": {
                "success": True,
            },
            "files": {
                "success": True,
            },
        }

    def fail_verification(**kwargs):
        assert kwargs[
            "backup_path"
        ] == str(
            backup_root
        )

        raise BackupVerificationError(
            "simulated checksum mismatch"
        )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.create_full_backup",
        fake_create_full_backup,
    )

    monkeypatch.setattr(
        "app.core.backup.backup_tasks.verify_full_backup",
        fail_verification,
    )

    with pytest.raises(
        BackupServiceError,
        match="Scheduled backup verification failed",
    ):
        run_scheduled_backup()

    assert not backup_root.exists()

    assert tmp_path.exists()
    assert list(
        tmp_path.iterdir()
    ) == []
