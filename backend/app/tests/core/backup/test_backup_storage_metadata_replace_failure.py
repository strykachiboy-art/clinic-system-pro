from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    read_metadata,
    write_metadata,
)


def test_write_metadata_preserves_existing_metadata_when_replace_fails(
    tmp_path,
    monkeypatch,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    original_metadata = {
        "version": 1,
        "backup_id": "original",
        "success": True,
    }

    write_metadata(
        backup_directory,
        original_metadata,
    )

    original_replace = Path.replace

    def fail_temp_replace(
        self,
        target,
    ):
        if (
            self.parent == backup_directory
            and self.name.startswith(
                ".metadata.json."
            )
            and self.name.endswith(
                ".tmp"
            )
        ):
            raise OSError(
                "synthetic metadata replace denial"
            )

        return original_replace(
            self,
            target,
        )

    monkeypatch.setattr(
        Path,
        "replace",
        fail_temp_replace,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to write backup metadata",
    ) as exc_info:
        write_metadata(
            backup_directory,
            {
                "version": 2,
                "backup_id": "replacement",
                "success": True,
            },
            overwrite=True,
        )

    assert isinstance(
        exc_info.value.__cause__,
        OSError,
    )

    assert (
        "synthetic metadata replace denial"
        in str(
            exc_info.value.__cause__
        )
    )

    assert read_metadata(
        backup_directory
    ) == original_metadata

    assert not list(
        backup_directory.glob(
            ".metadata.json.*.tmp"
        )
    )
