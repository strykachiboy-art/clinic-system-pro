from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.backup.restore_service import (
    RestoreError,
    restore_full_backup,
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


def _build_backup(
    tmp_path,
):
    backup_root = (
        tmp_path
        / "backup"
    )

    database_payload = (
        b"database-dump"
    )

    database_path = (
        backup_root
        / "database.dump"
    )

    _write_file(
        database_path,
        database_payload,
    )

    file_payload = (
        b"clinical-file"
    )

    storage_key = (
        "profile_images"
        "/photo.jpg"
    )

    backed_up_file = (
        backup_root
        / "files"
        / Path(storage_key)
    )

    _write_file(
        backed_up_file,
        file_payload,
    )

    manifest = {
        "version": 1,
        "file_count": 1,
        "total_size_bytes": len(
            file_payload
        ),
        "files": [
            {
                "storage_key": storage_key,
                "physical_path": (
                    "storage"
                    "/profile_images"
                    "/photo.jpg"
                ),
                "backup_path": (
                    "files"
                    "/profile_images"
                    "/photo.jpg"
                ),
                "sha256": _sha256(
                    file_payload
                ),
                "size_bytes": len(
                    file_payload
                ),
                "modified_at": (
                    "2026-10-06T00:00:00+00:00"
                ),
            }
        ],
    }

    manifest_path = (
        backup_root
        / "files"
        / "manifest.json"
    )

    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode(
        "utf-8"
    )

    _write_file(
        manifest_path,
        manifest_bytes,
    )

    metadata = {
        "version": 1,
        "backup_id": "backup-test-008",
        "created_at": (
            "2026-10-06T00:00:00+00:00"
        ),
        "success": True,
        "database": {
            "success": True,
            "database_name": "clinic_system",
            "database_host": "localhost",
            "database_port": 5432,
            "backup_path": str(
                database_path
            ),
            "backup_size_bytes": len(
                database_payload
            ),
            "backup_sha256": _sha256(
                database_payload
            ),
            "format": "custom",
        },
        "files": {
            "success": True,
            "backup_path": str(
                backup_root
                / "files"
            ),
            "manifest_path": str(
                manifest_path
            ),
            "manifest_sha256": _sha256(
                manifest_bytes
            ),
            "file_count": 1,
            "total_size_bytes": len(
                file_payload
            ),
        },
    }

    metadata_path = (
        backup_root
        / "metadata.json"
    )

    _write_file(
        metadata_path,
        (
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode(
            "utf-8"
        ),
    )

    return backup_root


def test_restore_full_backup_reports_terminal_post_restore_verification_failure(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_backup(
        tmp_path
    )

    storage_root = (
        tmp_path
        / "restored-storage"
    )

    pg_restore_calls = []

    def fake_run(
        command,
        **kwargs,
    ):
        pg_restore_calls.append(
            command
        )

        return Mock(
            returncode=0,
            stderr="",
            stdout="",
        )

    monkeypatch.setattr(
        "app.core.backup.restore_service.shutil.which",
        lambda value: "pg_restore",
    )

    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        fake_run,
    )

    def fail_post_restore_verification():
        raise RuntimeError(
            "synthetic terminal verification failure"
        )

    with app.app_context():
        with pytest.raises(
            RestoreError,
            match="Post-restore verification failed",
        ):
            restore_full_backup(
                backup_path=backup_root,
                database_url=(
                    "postgresql://backup@localhost/"
                    "clinic_system"
                ),
                storage_root=storage_root,
                post_restore_verification=(
                    fail_post_restore_verification
                ),
            )

    assert len(
        pg_restore_calls
    ) == 1

    restored_file = (
        storage_root
        / "profile_images"
        / "photo.jpg"
    )

    assert restored_file.exists()
    assert restored_file.read_bytes() == (
        b"clinical-file"
    )

    assert not list(
        tmp_path.glob(
            "restored-storage.restore-*"
        )
    )
