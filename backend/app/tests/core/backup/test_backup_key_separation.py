from __future__ import annotations

import base64

import pytest

from app.core.backup.backup_encryption import (
    encrypt_backup_artifact,
)


def _backup_key() -> str:
    return base64.urlsafe_b64encode(
        b"b" * 32
    ).decode("ascii")


def _integration_key() -> str:
    return base64.urlsafe_b64encode(
        b"i" * 32
    ).decode("ascii")


def test_backup_key_is_independent_from_integration_key(
    app,
    tmp_path,
):
    app.config["BACKUP_ENCRYPTION_KEY"] = _backup_key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"
    app.config["INTEGRATION_ENCRYPTION_KEY"] = (
        _integration_key()
    )

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"

    source.write_bytes(
        b"backup-domain-secret"
    )

    assert (
        encrypt_backup_artifact(
            source,
            encrypted,
        )
        == 1
    )

    assert encrypted.exists()


def test_backup_key_cannot_reuse_integration_key(
    app,
    tmp_path,
):
    shared_key = _backup_key()

    app.config["BACKUP_ENCRYPTION_KEY"] = shared_key
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"
    app.config["INTEGRATION_ENCRYPTION_KEY"] = shared_key

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"

    source.write_bytes(
        b"backup-domain-secret"
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "must be distinct from "
            "INTEGRATION_ENCRYPTION_KEY"
        ),
    ):
        encrypt_backup_artifact(
            source,
            encrypted,
        )

    assert not encrypted.exists()

    assert not (
        tmp_path
        / "backup.dump.enc.partial"
    ).exists()


def test_backup_key_version_is_independent(
    app,
    tmp_path,
):
    app.config["BACKUP_ENCRYPTION_KEY"] = _backup_key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "7"
    app.config["INTEGRATION_ENCRYPTION_KEY"] = (
        _integration_key()
    )
    app.config["INTEGRATION_ENCRYPTION_KEY_VERSION"] = "99"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"

    source.write_bytes(
        b"independent-key-version"
    )

    assert (
        encrypt_backup_artifact(
            source,
            encrypted,
        )
        == 1
    )

    assert encrypted.exists()


def test_backup_key_missing_still_fails_closed(
    app,
    tmp_path,
):
    app.config.pop(
        "BACKUP_ENCRYPTION_KEY",
        None,
    )

    app.config["INTEGRATION_ENCRYPTION_KEY"] = (
        _integration_key()
    )

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"

    source.write_bytes(
        b"backup"
    )

    with pytest.raises(
        RuntimeError,
        match="BACKUP_ENCRYPTION_KEY",
    ):
        encrypt_backup_artifact(
            source,
            encrypted,
        )

    assert not encrypted.exists()