from __future__ import annotations

import base64

import pytest

from app.core.backup.backup_encryption import (
    decrypt_backup_artifact,
    encrypt_backup_artifact,
)


def _key() -> str:
    return base64.urlsafe_b64encode(b"b" * 32).decode("ascii")


def _other_key() -> str:
    return base64.urlsafe_b64encode(b"c" * 32).decode("ascii")


@pytest.fixture(autouse=True)
def _app_context(app):
    # The module reads current_app.config, so make sure a context is active
    # regardless of how the shared `app` fixture is written.
    with app.app_context():
        yield


def test_encrypt_decrypt_round_trip(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "database.dump"
    encrypted = tmp_path / "database.dump.enc"
    restored = tmp_path / "database.restore.dump"

    payload = (b"clinic-backup-payload-" * 1000) + b"!"
    source.write_bytes(payload)

    chunks = encrypt_backup_artifact(source, encrypted, chunk_size=128)

    assert chunks > 1
    assert encrypted.exists()
    assert not (tmp_path / "database.dump.enc.partial").exists()

    assert decrypt_backup_artifact(encrypted, restored) == chunks
    assert restored.read_bytes() == payload


def test_exact_chunk_multiple_round_trip(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    payload = b"x" * 64
    source.write_bytes(payload)

    assert encrypt_backup_artifact(source, encrypted, chunk_size=16) == 4
    assert decrypt_backup_artifact(encrypted, restored) == 4
    assert restored.read_bytes() == payload


def test_empty_artifact_round_trip(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "empty.dump"
    encrypted = tmp_path / "empty.dump.enc"
    restored = tmp_path / "empty.restore.dump"

    source.write_bytes(b"")

    # One empty, authenticated, final chunk.
    assert encrypt_backup_artifact(source, encrypted) == 1
    assert decrypt_backup_artifact(encrypted, restored) == 1
    assert restored.read_bytes() == b""


def test_missing_key_fails_closed(app, tmp_path):
    app.config.pop("BACKUP_ENCRYPTION_KEY", None)

    source = tmp_path / "backup.dump"
    destination = tmp_path / "backup.dump.enc"
    source.write_bytes(b"secret")

    with pytest.raises(RuntimeError, match="BACKUP_ENCRYPTION_KEY"):
        encrypt_backup_artifact(source, destination)

    assert not destination.exists()


def test_invalid_key_length_fails_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(
        b"short"
    ).decode("ascii")

    source = tmp_path / "backup.dump"
    destination = tmp_path / "backup.dump.enc"
    source.write_bytes(b"secret")

    with pytest.raises(RuntimeError, match="32 bytes"):
        encrypt_backup_artifact(source, destination)

    assert not destination.exists()


def test_key_version_is_written_and_enforced(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "7"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    source.write_bytes(b"versioned backup")
    encrypt_backup_artifact(source, encrypted)

    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "8"

    with pytest.raises(RuntimeError, match="key version does not match"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()


def test_wrong_key_fails_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    source.write_bytes(b"sensitive backup data")
    encrypt_backup_artifact(source, encrypted)

    app.config["BACKUP_ENCRYPTION_KEY"] = _other_key()

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()
    assert not (tmp_path / "restored.dump.partial").exists()


def test_tampered_ciphertext_fails_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    source.write_bytes(b"tamper detection payload")
    encrypt_backup_artifact(source, encrypted)

    data = bytearray(encrypted.read_bytes())
    data[-1] ^= 0x01
    encrypted.write_bytes(data)

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()
    assert not (tmp_path / "restored.dump.partial").exists()


def test_truncated_artifact_fails_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    source.write_bytes(b"truncation detection payload")
    encrypt_backup_artifact(source, encrypted)

    data = encrypted.read_bytes()
    encrypted.write_bytes(data[:-3])

    with pytest.raises(ValueError, match="truncated"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()


def test_truncation_at_chunk_boundary_fails_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    # 40 bytes @ 16 -> chunks of 16, 16, 8 plaintext bytes.
    source.write_bytes(b"y" * 40)
    assert encrypt_backup_artifact(source, encrypted, chunk_size=16) == 3

    # Drop the whole last record: 8-byte length prefix + (8 bytes + 16 tag).
    data = encrypted.read_bytes()
    encrypted.write_bytes(data[: -(8 + 8 + 16)])

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()
    assert not (tmp_path / "restored.dump.partial").exists()


def test_existing_destination_is_never_overwritten(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"

    source.write_bytes(b"backup")
    encrypted.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        encrypt_backup_artifact(source, encrypted)

    assert encrypted.read_bytes() == b"existing"
def test_trailing_bytes_fail_closed(app, tmp_path):
    app.config["BACKUP_ENCRYPTION_KEY"] = _key()
    app.config["BACKUP_ENCRYPTION_KEY_VERSION"] = "1"

    source = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.enc"
    restored = tmp_path / "restored.dump"

    source.write_bytes(b"trailing data detection")
    encrypt_backup_artifact(source, encrypted)

    encrypted.write_bytes(
        encrypted.read_bytes() + b"TRAILING-GARBAGE"
    )

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_backup_artifact(encrypted, restored)

    assert not restored.exists()
    assert not (tmp_path / "restored.dump.partial").exists()
