from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    write_metadata,
)


def test_write_metadata_cleans_temporary_file_after_write_failure(
    tmp_path,
    monkeypatch,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    original_open = Path.open

    class FailingWriter:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return self._handle.__exit__(
                exc_type,
                exc_value,
                traceback,
            )

        def write(self, payload):
            self._handle.write(
                payload[:8]
            )
            self._handle.flush()

            raise OSError(
                "synthetic metadata write denial"
            )

    def fail_temp_write(
        self,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        if (
            self.name.startswith(
                ".metadata.json."
            )
            and self.name.endswith(
                ".tmp"
            )
            and mode == "x"
        ):
            handle = original_open(
                self,
                mode=mode,
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
                            )

            return FailingWriter(
                handle
            )

        return original_open(
            self,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
                )

    monkeypatch.setattr(
        Path,
        "open",
        fail_temp_write,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to write backup metadata",
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

    assert (
        "synthetic metadata write denial"
        in str(
            exc_info.value.__cause__
        )
    )

    assert not (
        backup_directory
        / "metadata.json"
    ).exists()

    assert list(
        backup_directory.glob(
            ".metadata.json.*.tmp"
        )
    ) == []
