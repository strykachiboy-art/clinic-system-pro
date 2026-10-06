from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.backup import restore_service
from app.core.backup.restore_service import (
    RestoreError,
    restore_full_backup,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(payload)


def _build_backup(tmp_path, *, file_payload=b"clinical-file"):
    backup_root = tmp_path / "backup"

    database_payload = b"database-dump"
    database_path = backup_root / "database.dump"
    _write_file(database_path, database_payload)

    storage_key = "profile_images/photo.jpg"
    backed_up_file = backup_root / "files" / Path(storage_key)
    _write_file(backed_up_file, file_payload)

    manifest = {
        "version": 1,
        "file_count": 1,
        "total_size_bytes": len(file_payload),
        "files": [
            {
                "storage_key": storage_key,
                "physical_path": "storage/profile_images/photo.jpg",
                "backup_path": "files/profile_images/photo.jpg",
                "sha256": _sha256(file_payload),
                "size_bytes": len(file_payload),
                "modified_at": "2026-09-24T00:00:00+00:00",
            }
        ],
    }

    manifest_path = backup_root / "files" / "manifest.json"
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _write_file(manifest_path, manifest_bytes)

    metadata = {
        "version": 1,
        "backup_id": "backup-test-001",
        "created_at": "2026-09-24T00:00:00+00:00",
        "success": True,
        "database": {
            "success": True,
            "database_name": "clinic_system",
            "database_host": "localhost",
            "database_port": 5432,
            "backup_path": str(database_path),
            "backup_size_bytes": len(database_payload),
            "backup_sha256": _sha256(database_payload),
            "format": "custom",
        },
        "files": {
            "success": True,
            "backup_path": str(backup_root / "files"),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256(manifest_bytes),
            "file_count": 1,
            "total_size_bytes": len(file_payload),
        },
    }

    _write_file(
        backup_root / "metadata.json",
        (
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )

    return backup_root


def _patch_pg_restore(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.backup.restore_service.shutil.which",
        lambda value: "pg_restore",
    )
    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        lambda *args, **kwargs: Mock(
            returncode=0,
            stderr="",
            stdout="",
        ),
    )


def test_restore_full_backup_rejects_checksum_corruption_after_storage_commit(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_backup(tmp_path)
    storage_root = tmp_path / "restored-storage"

    original_commit = (
        restore_service._commit_storage_restore
    )

    def corrupt_after_commit(
        *,
        staging_root,
        storage_root,
        replace_existing,
    ):
        original_commit(
            staging_root=staging_root,
            storage_root=storage_root,
            replace_existing=replace_existing,
        )

        restored_file = (
            storage_root
            / "profile_images"
            / "photo.jpg"
        )
        restored_file.write_bytes(b"tampered-data")

    monkeypatch.setattr(
        restore_service,
        "_commit_storage_restore",
        corrupt_after_commit,
    )
    _patch_pg_restore(monkeypatch)

    with app.app_context():
        with pytest.raises(
            RestoreError,
            match="Restored file checksum mismatch",
        ):
            restore_full_backup(
                backup_path=backup_root,
                database_url=(
                    "postgresql://backup@localhost/"
                    "clinic_system"
                ),
                storage_root=storage_root,
            )

    assert (
        storage_root
        / "profile_images"
        / "photo.jpg"
    ).read_bytes() == b"tampered-data"


def test_restore_full_backup_rejects_size_corruption_after_storage_commit(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_backup(tmp_path)
    storage_root = tmp_path / "restored-storage"

    original_commit = (
        restore_service._commit_storage_restore
    )

    def truncate_after_commit(
        *,
        staging_root,
        storage_root,
        replace_existing,
    ):
        original_commit(
            staging_root=staging_root,
            storage_root=storage_root,
            replace_existing=replace_existing,
        )

        restored_file = (
            storage_root
            / "profile_images"
            / "photo.jpg"
        )
        restored_file.write_bytes(b"x")

    monkeypatch.setattr(
        restore_service,
        "_commit_storage_restore",
        truncate_after_commit,
    )
    _patch_pg_restore(monkeypatch)

    with app.app_context():
        with pytest.raises(
            RestoreError,
            match="Restored file size mismatch",
        ):
            restore_full_backup(
                backup_path=backup_root,
                database_url=(
                    "postgresql://backup@localhost/"
                    "clinic_system"
                ),
                storage_root=storage_root,
            )

    assert (
        storage_root
        / "profile_images"
        / "photo.jpg"
    ).read_bytes() == b"x"
