from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup import backup_storage
from app.core.backup.backup_storage import (
    BackupStorageError,
    write_artifact,
)


def test_write_artifact_mid_write_failure_cleans_partial_artifact(
    tmp_path,
    monkeypatch,
):
    artifact = (
        tmp_path
        / "backup-artifact.dump"
    )

    original_open = backup_storage.Path.open

    class FailingWriter:
        def __init__(
            self,
            path,
            mode,
        ):
            self._handle = original_open(
                path,
                mode,
            )

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            self._handle.close()
            return False

        def write(
            self,
            data,
        ):
            partial = data[
                : max(
                    1,
                    len(data) // 2,
                )
            ]

            self._handle.write(
                partial
            )

            self._handle.flush()

            raise OSError(
                "simulated backup artifact write failure"
            )

        def __getattr__(
            self,
            name,
        ):
            return getattr(
                self._handle,
                name,
            )

    def failing_open(
        self,
        mode="r",
        *args,
        **kwargs,
    ):
        if (
            self.parent == artifact.parent
            and self.name.startswith(".backup-artifact.dump.")
            and self.name.endswith(".tmp")
        ):
            return FailingWriter(
                self,
                mode,
            )

        return original_open(
            self,
            mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        backup_storage.Path,
        "open",
        failing_open,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to write backup artifact",
    ):
        backup_storage.write_artifact(
            artifact,
            b"backup artifact payload",
        )

    assert not artifact.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_artifact_overwrite_failure_preserves_existing_artifact(
    tmp_path,
    monkeypatch,
):
    artifact = (
        tmp_path
        / "backup-artifact.dump"
    )

    original_payload = (
        b"existing-valid-backup"
    )

    artifact.write_bytes(
        original_payload
    )

    original_open = backup_storage.Path.open

    class FailingWriter:
        def __init__(
            self,
            path,
            mode,
        ):
            self._handle = original_open(
                path,
                mode,
            )

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            self._handle.close()
            return False

        def write(
            self,
            data,
        ):
            self._handle.write(
                data[
                    : max(
                        1,
                        len(data) // 2,
                    )
                ]
            )

            self._handle.flush()

            raise OSError(
                "simulated backup overwrite failure"
            )

        def __getattr__(
            self,
            name,
        ):
            return getattr(
                self._handle,
                name,
            )

    def failing_open(
        self,
        mode="r",
        *args,
        **kwargs,
    ):
        if (
            self.name.startswith(
                ".backup-artifact.dump."
            )
            and self.name.endswith(
                ".tmp"
            )
        ):
            return FailingWriter(
                self,
                mode,
            )

        return original_open(
            self,
            mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        backup_storage.Path,
        "open",
        failing_open,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to write backup artifact",
    ):
        write_artifact(
            artifact,
            b"replacement-backup-payload",
            overwrite=True,
        )

    assert artifact.exists()

    assert artifact.read_bytes() == (
        original_payload
    )

    leftovers = [
        path
        for path in tmp_path.iterdir()
        if path.is_file()
        and path != artifact
    ]

    assert leftovers == []