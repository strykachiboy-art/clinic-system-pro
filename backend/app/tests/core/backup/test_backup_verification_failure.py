from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.core.backup.backup_verification import (
    BackupVerificationError,
    verify_database_backup,
    verify_file_backup,
)


def _sha256(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def _write_file(
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        payload
    )


def test_verify_database_backup_fails_closed_on_artifact_read_failure(
    tmp_path,
    monkeypatch,
):
    root = (
        tmp_path
        / "backup"
    )

    payload = (
        b"database-dump"
    )

    artifact = (
        root
        / "database.dump"
    )

    _write_file(
        artifact,
        payload,
    )

    original_open = Path.open

    class FailingReader:
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

        def read(
            self,
            *args,
            **kwargs,
        ):
            raise OSError(
                "simulated backup artifact read failure"
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
        path,
        mode="r",
        *args,
        **kwargs,
    ):
        return original_open(
            path,
            mode,
            *args,
            **kwargs,
        )

    def patched_open(
        self,
        self_path,
        mode="r",
        *args,
        **kwargs,
    ):
        if self_path == artifact:
            return FailingReader(
                self_path,
                mode,
            )

        return original_open(
            self_path,
            mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "open",
        patched_open,
    )

    with pytest.raises(
        BackupVerificationError,
        match="Unable to read backup artifact",
    ):
        verify_database_backup(
            backup_root=root,
            database_metadata={
                "backup_path": str(
                    artifact
                ),
                "backup_size_bytes": len(
                    payload
                ),
                "backup_sha256": _sha256(
                    payload
                ),
            },
        )


def test_verify_file_backup_fails_closed_on_manifest_hash_read_failure(
    tmp_path,
    monkeypatch,
):
    root = (
        tmp_path
        / "backup"
    )

    payload = (
        b"clinical-file"
    )

    backed_up_file = (
        root
        / "files"
        / "profile_images"
        / "photo.jpg"
    )

    _write_file(
        backed_up_file,
        payload,
    )

    manifest_path = (
        root
        / "files"
        / "manifest.json"
    )

    manifest = (
        b'{"version": 1, "file_count": 1, '
        b'"total_size_bytes": 14, "files": []}'
    )

    _write_file(
        manifest_path,
        manifest,
    )

    original_open = Path.open

    class FailingReader:
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

        def read(
            self,
            *args,
            **kwargs,
        ):
            raise OSError(
                "simulated manifest read failure"
            )

        def __getattr__(
            self,
            name,
        ):
            return getattr(
                self._handle,
                name,
            )

    def patched_open(
        self,
        mode="r",
        *args,
        **kwargs,
    ):
        if self == manifest_path:
            return FailingReader(
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
        Path,
        "open",
        patched_open,
    )

    with pytest.raises(
        BackupVerificationError,
        match="Unable to read backup artifact",
    ):
        verify_file_backup(
            backup_root=root,
            file_metadata={
                "manifest_path": str(
                    manifest_path
                ),
                "manifest_sha256": _sha256(
                    manifest
                ),
            },
        )
