from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.backup import backup_encryption as backup_crypto
from app.core.backup.backup_encryption import (
    encrypt_backup_artifact,
)
from app.core.backup.restore_service import (
    RestoreError,
    restore_full_backup,
)


def _backup_key() -> str:
    return base64.urlsafe_b64encode(
        b"b" * 32
    ).decode("ascii")


def _integration_key() -> str:
    return base64.urlsafe_b64encode(
        b"i" * 32
    ).decode("ascii")


@pytest.fixture(autouse=True)
def _backup_encryption_context(app):
    app.config["BACKUP_ENCRYPTION_KEY"] = _backup_key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"
    app.config["INTEGRATION_ENCRYPTION_KEY"] = (
        _integration_key()
    )

    with app.app_context():
        yield


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_file(
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(payload)


def _build_encrypted_backup(
    tmp_path,
    *,
    database_payload=b"database-dump",
):
    backup_root = tmp_path / "backup"
    database_path = backup_root / "database.dump"
    source_path = backup_root / "database-source.dump"

    _write_file(
        source_path,
        database_payload,
    )

    encrypt_backup_artifact(
        source_path,
        database_path,
    )

    source_path.unlink()

    file_payload = b"clinical-file"
    storage_key = "profile_images/photo.jpg"

    backup_file = (
        backup_root
        / "files"
        / storage_key
    )

    _write_file(
        backup_file,
        file_payload,
    )

    manifest = {
        "version": 1,
        "file_count": 1,
        "total_size_bytes": len(file_payload),
        "files": [
            {
                "storage_key": storage_key,
                "physical_path": (
                    "storage/profile_images/photo.jpg"
                ),
                "backup_path": (
                    "files/profile_images/photo.jpg"
                ),
                "sha256": _sha256(file_payload),
                "size_bytes": len(file_payload),
                "modified_at": (
                    "2026-10-08T00:00:00+00:00"
                ),
            }
        ],
    }

    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    manifest_path = (
        backup_root
        / "files"
        / "manifest.json"
    )

    _write_file(
        manifest_path,
        manifest_bytes,
    )

    metadata = {
        "version": 1,
        "backup_id": "backup-failure-recovery-001",
        "created_at": (
            "2026-10-08T00:00:00+00:00"
        ),
        "success": True,
        "database": {
            "success": True,
            "database_name": "clinic_system",
            "database_host": "localhost",
            "database_port": 5432,
            "backup_path": str(database_path),
            "backup_size_bytes": database_path.stat().st_size,
            "backup_sha256": _sha256(
                database_path.read_bytes()
            ),
            "format": "custom",
            "encrypted": True,
        },
        "files": {
            "success": True,
            "backup_path": str(
                backup_root / "files"
            ),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256(
                manifest_bytes
            ),
            "file_count": 1,
            "total_size_bytes": len(file_payload),
        },
    }

    metadata_path = backup_root / "metadata.json"

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
        ).encode("utf-8"),
    )

    return backup_root


def _refresh_database_checksum(
    backup_root: Path,
) -> None:
    database_path = (
        backup_root
        / "database.dump"
    )

    metadata_path = (
        backup_root
        / "metadata.json"
    )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    metadata["database"][
        "backup_size_bytes"
    ] = database_path.stat().st_size

    metadata["database"][
        "backup_sha256"
    ] = _sha256(
        database_path.read_bytes()
    )

    metadata_path.write_text(
        (
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        encoding="utf-8",
    )


def _restore_with_fake_pg_restore(
    backup_root: Path,
    tmp_path: Path,
    monkeypatch,
):
    observed = {
        "command": None,
    }

    def fake_restore(
        command,
        **kwargs,
    ):
        observed["command"] = command

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
        fake_restore,
    )

    result = restore_full_backup(
        backup_path=backup_root,
        database_url=(
            "postgresql://backup@localhost/"
            "clinic_system"
        ),
        storage_root=(
            tmp_path
            / "storage"
        ),
    )

    return result, observed


def test_encryption_interruption_cleans_partial_and_recovers(
    app,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "database.dump"
    encrypted = tmp_path / "database.dump.enc"

    source.write_bytes(
        b"backup-data-" * 100
    )

    original_encrypt = (
        backup_crypto.AESGCM.encrypt
    )

    calls = {
        "count": 0,
    }

    def injected_encrypt(
        self,
        nonce,
        data,
        aad,
    ):
        calls["count"] += 1

        if calls["count"] == 2:
            raise RuntimeError(
                "synthetic crypto interruption"
            )

        return original_encrypt(
            self,
            nonce,
            data,
            aad,
        )

    monkeypatch.setattr(
        backup_crypto.AESGCM,
        "encrypt",
        injected_encrypt,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic crypto interruption",
    ):
        encrypt_backup_artifact(
            source,
            encrypted,
            chunk_size=16,
        )

    assert calls["count"] == 2
    assert not encrypted.exists()
    assert not (
        tmp_path
        / "database.dump.enc.partial"
    ).exists()

    monkeypatch.undo()

    assert (
        encrypt_backup_artifact(
            source,
            encrypted,
            chunk_size=16,
        )
        > 1
    )

    assert encrypted.exists()
    assert not (
        tmp_path
        / "database.dump.enc.partial"
    ).exists()


def test_corrupted_ciphertext_fails_closed_then_original_recovers(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_encrypted_backup(
        tmp_path
    )

    database_path = (
        backup_root
        / "database.dump"
    )

    original = database_path.read_bytes()

    corrupted = bytearray(original)
    corrupted[-1] ^= 0x01
    database_path.write_bytes(corrupted)

    _refresh_database_checksum(
        backup_root
    )

    def fail_restore(*args, **kwargs):
        raise AssertionError(
            "pg_restore must not run after crypto failure"
        )

    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        fail_restore,
    )

    with pytest.raises(
        RestoreError,
        match="Unable to decrypt database backup",
    ):
        restore_full_backup(
            backup_path=backup_root,
            database_url=(
                "postgresql://backup@localhost/"
                "clinic_system"
            ),
            storage_root=(
                tmp_path
                / "failed-storage"
            ),
        )

    assert not list(
        tmp_path.glob(
            "clinic-system-backup-restore-*"
        )
    )

    database_path.write_bytes(
        original
    )

    _refresh_database_checksum(
        backup_root
    )

    result, observed = (
        _restore_with_fake_pg_restore(
            backup_root,
            tmp_path,
            monkeypatch,
        )
    )

    assert result.success is True
    assert observed["command"] is not None
    assert not Path(
        observed["command"][-1]
    ).exists()


def test_truncated_ciphertext_fails_closed_then_original_recovers(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_encrypted_backup(
        tmp_path
    )

    database_path = (
        backup_root
        / "database.dump"
    )

    original = database_path.read_bytes()

    database_path.write_bytes(
        original[:-3]
    )

    _refresh_database_checksum(
        backup_root
    )

    def fail_restore(*args, **kwargs):
        raise AssertionError(
            "pg_restore must not run after truncation"
        )

    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        fail_restore,
    )

    with pytest.raises(
        RestoreError,
        match="Unable to decrypt database backup",
    ):
        restore_full_backup(
            backup_path=backup_root,
            database_url=(
                "postgresql://backup@localhost/"
                "clinic_system"
            ),
            storage_root=(
                tmp_path
                / "truncated-storage"
            ),
        )

    database_path.write_bytes(
        original
    )

    _refresh_database_checksum(
        backup_root
    )

    result, _ = (
        _restore_with_fake_pg_restore(
            backup_root,
            tmp_path,
            monkeypatch,
        )
    )

    assert result.success is True


def test_wrong_key_fails_closed_without_plaintext_recovery_artifact(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = _build_encrypted_backup(
        tmp_path
    )

    app.config["BACKUP_ENCRYPTION_KEY"] = (
        base64.urlsafe_b64encode(
            b"c" * 32
        ).decode("ascii")
    )

    def fail_restore(*args, **kwargs):
        raise AssertionError(
            "pg_restore must not run with wrong backup key"
        )

    monkeypatch.setattr(
        "app.core.backup.restore_service.subprocess.run",
        fail_restore,
    )

    with pytest.raises(
        RestoreError,
        match="Unable to decrypt database backup",
    ):
        restore_full_backup(
            backup_path=backup_root,
            database_url=(
                "postgresql://backup@localhost/"
                "clinic_system"
            ),
            storage_root=(
                tmp_path
                / "wrong-key-storage"
            ),
        )

    assert not list(
        tmp_path.glob(
            "clinic-system-backup-restore-*"
        )
    )