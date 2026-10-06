from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    generate_safe_backup_path,
    read_metadata,
    write_artifact,
    write_metadata,
)


def test_generate_safe_backup_path_wraps_directory_creation_failure(
    tmp_path,
    monkeypatch,
):
    target_directory = tmp_path / "generated"

    original_mkdir = Path.mkdir

    def fail_target_directory_mkdir(self, *args, **kwargs):
        if self == target_directory:
            raise OSError("synthetic backup directory denial")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_target_directory_mkdir,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to create backup directory",
    ) as exc_info:
        generate_safe_backup_path(
            relative_directory="generated",
            backup_root=tmp_path,
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert "synthetic backup directory denial" in str(
        exc_info.value.__cause__
    )


def test_write_artifact_wraps_parent_directory_creation_failure(
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / "artifacts" / "backup.dump"

    original_mkdir = Path.mkdir

    def fail_artifact_parent_mkdir(self, *args, **kwargs):
        if self == artifact.parent:
            raise OSError("synthetic artifact directory denial")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_artifact_parent_mkdir,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to create backup artifact directory",
    ) as exc_info:
        write_artifact(
            artifact,
            b"backup-payload",
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert "synthetic artifact directory denial" in str(
        exc_info.value.__cause__
    )
    assert not artifact.exists()


def test_read_metadata_wraps_metadata_read_failure(
    tmp_path,
    monkeypatch,
):
    backup_directory = tmp_path / "backup"
    original_metadata = {
        "version": 1,
        "backup_id": "read-failure",
        "success": True,
    }

    write_metadata(
        backup_directory,
        original_metadata,
    )

    metadata_path = backup_directory / "metadata.json"
    original_open = Path.open

    def fail_metadata_open(self, *args, **kwargs):
        if self == metadata_path:
            raise OSError("synthetic metadata read denial")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "open",
        fail_metadata_open,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to read backup metadata",
    ) as exc_info:
        read_metadata(backup_directory)

    assert isinstance(exc_info.value.__cause__, OSError)
    assert "synthetic metadata read denial" in str(
        exc_info.value.__cause__
    )
