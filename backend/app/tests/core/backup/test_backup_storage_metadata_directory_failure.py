from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    write_metadata,
)


def test_write_metadata_wraps_directory_creation_failure(
    tmp_path,
    monkeypatch,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    original_mkdir = Path.mkdir

    def fail_target_directory_mkdir(
        self,
        mode=0o777,
        parents=False,
        exist_ok=False,
    ):
        if self == backup_directory:
            raise OSError(
                "synthetic metadata directory denial"
            )

        return original_mkdir(
            self,
            mode=mode,
            parents=parents,
            exist_ok=exist_ok,
        )

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_target_directory_mkdir,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to create metadata directory",
    ) as exc_info:
        write_metadata(
            backup_directory,
            {
                "backup_id": "backup-001",
                "success": True,
            },
        )

    assert isinstance(
        exc_info.value.__cause__,
        OSError,
    )
    assert "synthetic metadata directory denial" in str(
        exc_info.value.__cause__
    )
