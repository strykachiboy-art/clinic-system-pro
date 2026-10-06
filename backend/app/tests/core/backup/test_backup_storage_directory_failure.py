from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    create_backup_directory,
)


def test_create_backup_directory_wraps_filesystem_failure(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "backups"

    def fail_mkdir(
        self,
        mode=0o777,
        parents=False,
        exist_ok=False,
    ):
        raise OSError(
            "synthetic filesystem denial"
        )

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_mkdir,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to create backup directory",
    ) as exc_info:
        create_backup_directory(
            relative_path="backup-001",
            backup_root=root,
        )

    assert isinstance(
        exc_info.value.__cause__,
        OSError,
    )
    assert "synthetic filesystem denial" in str(
        exc_info.value.__cause__
    )
