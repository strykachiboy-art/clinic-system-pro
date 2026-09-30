from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.backup.database_backup import (
    DatabaseBackupError,
    backup_database,
)


POSTGRES_URL = (
    "postgresql://backup_user:"
    "secret-password"
    "@localhost:5432/"
    "clinic_system"
)


def test_backup_database_creates_result_and_checksum(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic_system.dump"
    )

    payload = (
        b"synthetic-postgresql-backup"
    )

    def fake_run(
        command,
        *,
        check,
        capture_output,
        text,
        encoding,
        errors,
        env,
        timeout,
    ):
        output_index = (
            command.index("--file")
            + 1
        )

        partial_path = Path(
            command[output_index]
        )

        partial_path.write_bytes(
            payload
        )

        assert "secret-password" not in (
            command
        )

        assert env["PGPASSWORD"] == (
            "secret-password"
        )

        return Mock(
            returncode=0,
            stderr="",
        )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: (
            "C:/PostgreSQL/bin/pg_dump.exe"
        ),
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.subprocess.run",
        fake_run,
    )

    result = backup_database(
        output_path=output,
        database_url=POSTGRES_URL,
    )

    expected_checksum = (
        hashlib.sha256(
            payload
        ).hexdigest()
    )

    assert result.success is True
    assert result.database_name == (
        "clinic_system"
    )
    assert result.database_host == (
        "localhost"
    )
    assert result.database_port == (
        5432
    )
    assert result.backup_path == str(
        output.resolve()
    )
    assert result.backup_size_bytes == (
        len(payload)
    )
    assert result.backup_sha256 == (
        expected_checksum
    )
    assert result.format == "custom"
    assert result.migration_revision is None
    assert output.read_bytes() == payload


def test_backup_database_preserves_migration_revision(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic.dump"
    )

    def fake_run(
        command,
        **kwargs,
    ):
        partial_path = Path(
            command[
                command.index("--file")
                + 1
            ]
        )

        partial_path.write_bytes(
            b"backup"
        )

        return Mock(
            returncode=0,
            stderr="",
        )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: value,
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.subprocess.run",
        fake_run,
    )

    result = backup_database(
        output_path=output,
        database_url=POSTGRES_URL,
        migration_revision="abc123",
    )

    assert result.migration_revision == (
        "abc123"
    )


def test_backup_database_rejects_non_postgresql_database(
    tmp_path,
):
    with pytest.raises(
        DatabaseBackupError,
        match="requires a PostgreSQL database",
    ):
        backup_database(
            output_path=(
                tmp_path
                / "clinic.dump"
            ),
            database_url=(
                "sqlite:///:memory:"
            ),
        )


def test_backup_database_rejects_empty_database_url(
    app,
    tmp_path,
):
    with pytest.raises(
        DatabaseBackupError,
        match="Database URL cannot be empty",
    ):
        backup_database(
            output_path=(
                tmp_path
                / "clinic.dump"
            ),
            database_url="   ",
        )


def test_backup_database_rejects_missing_pg_dump(
    app,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: None,
    )

    with pytest.raises(
        DatabaseBackupError,
        match="pg_dump executable was not found",
    ):
        backup_database(
            output_path=(
                tmp_path
                / "clinic.dump"
            ),
            database_url=POSTGRES_URL,
        )


def test_backup_database_rejects_existing_output(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic.dump"
    )

    output.write_bytes(
        b"existing"
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: value,
    )

    with pytest.raises(
        DatabaseBackupError,
        match="Backup output already exists",
    ):
        backup_database(
            output_path=output,
            database_url=POSTGRES_URL,
        )


def test_backup_database_cleans_partial_on_pg_dump_failure(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic.dump"
    )

    def fake_run(
        command,
        **kwargs,
    ):
        partial_path = Path(
            command[
                command.index("--file")
                + 1
            ]
        )

        partial_path.write_bytes(
            b"partial"
        )

        return Mock(
            returncode=1,
            stderr="permission denied",
        )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: value,
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.subprocess.run",
        fake_run,
    )

    with pytest.raises(
        DatabaseBackupError,
        match="pg_dump failed: permission denied",
    ):
        backup_database(
            output_path=output,
            database_url=POSTGRES_URL,
        )

    assert not output.exists()

    assert not (
        tmp_path
        / "clinic.dump.partial"
    ).exists()


def test_backup_database_cleans_partial_on_timeout(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic.dump"
    )

    def fake_run(
        command,
        **kwargs,
    ):
        partial_path = Path(
            command[
                command.index("--file")
                + 1
            ]
        )

        partial_path.write_bytes(
            b"partial"
        )

        raise __import__(
            "subprocess"
        ).TimeoutExpired(
            cmd=command,
            timeout=300,
        )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: value,
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.subprocess.run",
        fake_run,
    )

    with pytest.raises(
        DatabaseBackupError,
        match="pg_dump timed out",
    ):
        backup_database(
            output_path=output,
            database_url=POSTGRES_URL,
        )

    assert not output.exists()

    assert not (
        tmp_path
        / "clinic.dump.partial"
    ).exists()


def test_backup_database_rejects_invalid_timeout(
    app,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        lambda value: value,
    )

    with pytest.raises(
        DatabaseBackupError,
        match="Backup timeout must be a positive integer",
    ):
        backup_database(
            output_path=(
                tmp_path
                / "clinic.dump"
            ),
            database_url=POSTGRES_URL,
            timeout_seconds=0,
        )


def test_backup_database_accepts_pg_dump_custom_path(
    app,
    tmp_path,
    monkeypatch,
):
    output = (
        tmp_path
        / "clinic.dump"
    )

    observed = {
        "command": None,
    }

    def fake_which(value):
        return (
            "C:/PostgreSQL/bin/pg_dump.exe"
        )

    def fake_run(
        command,
        **kwargs,
    ):
        observed["command"] = command

        partial_path = Path(
            command[
                command.index("--file")
                + 1
            ]
        )

        partial_path.write_bytes(
            b"backup"
        )

        return Mock(
            returncode=0,
            stderr="",
        )

    monkeypatch.setattr(
        "app.core.backup.database_backup.shutil.which",
        fake_which,
    )

    monkeypatch.setattr(
        "app.core.backup.database_backup.subprocess.run",
        fake_run,
    )

    result = backup_database(
        output_path=output,
        database_url=POSTGRES_URL,
        pg_dump_path="pg_dump",
    )

    assert result.success is True
    assert observed["command"][0] == (
        "C:/PostgreSQL/bin/pg_dump.exe"
    )

    assert (
        observed["command"]
        [observed["command"].index(
            "--format"
        ) + 1]
        == "custom"
    )