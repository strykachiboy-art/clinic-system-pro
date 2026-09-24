from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    calculate_sha256,
    create_backup_directory,
    generate_safe_backup_path,
    read_artifact,
    read_metadata,
    resolve_backup_path,
    verify_artifact_exists,
    write_artifact,
    write_metadata,
)


def test_create_backup_directory_creates_directory(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    created = create_backup_directory(
        backup_root=root
    )

    assert created == (
        root.resolve()
    )

    assert created.exists()
    assert created.is_dir()


def test_resolve_backup_path_preserves_root_boundary(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    root.mkdir()

    resolved = resolve_backup_path(
        "database/clinic.dump",
        backup_root=root,
    )

    assert resolved == (
        root
        / "database"
        / "clinic.dump"
    ).resolve()


def test_resolve_backup_path_rejects_parent_traversal(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    with pytest.raises(
        BackupStorageError,
        match="Invalid backup path",
    ):
        resolve_backup_path(
            "../outside.dump",
            backup_root=root,
        )


def test_resolve_backup_path_rejects_absolute_path(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    with pytest.raises(
        BackupStorageError,
        match="Backup path must be relative",
    ):
        resolve_backup_path(
            Path(
                "C:/outside.dump"
            ),
            backup_root=root,
        )


def test_generate_safe_backup_path_creates_unique_safe_path(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    first = generate_safe_backup_path(
        prefix="clinic-db",
        extension="dump",
        relative_directory="database",
        backup_root=root,
    )

    second = generate_safe_backup_path(
        prefix="clinic-db",
        extension="dump",
        relative_directory="database",
        backup_root=root,
    )

    assert first != second
    assert first.parent == (
        root
        / "database"
    ).resolve()

    assert second.parent == (
        root
        / "database"
    ).resolve()

    assert first.name.startswith(
        "clinic-db-"
    )

    assert first.suffix == ".dump"


def test_generate_safe_backup_path_rejects_path_injection(
    tmp_path,
):
    with pytest.raises(
        BackupStorageError,
        match="cannot contain path separators",
    ):
        generate_safe_backup_path(
            prefix="../escape",
            backup_root=(
                tmp_path
                / "backups"
            ),
        )


def test_write_artifact_writes_bytes(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    path = resolve_backup_path(
        "artifact.bin",
        backup_root=root,
    )

    result = write_artifact(
        path,
        b"backup-data",
    )

    assert result == path
    assert path.read_bytes() == (
        b"backup-data"
    )


def test_write_artifact_rejects_existing_file_without_overwrite(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    path = resolve_backup_path(
        "artifact.bin",
        backup_root=root,
    )

    write_artifact(
        path,
        b"first",
    )

    with pytest.raises(
        BackupStorageError,
        match="already exists",
    ):
        write_artifact(
            path,
            b"second",
        )

    assert path.read_bytes() == (
        b"first"
    )


def test_write_artifact_supports_explicit_overwrite(
    tmp_path,
):
    root = (
        tmp_path
        / "backups"
    )

    path = resolve_backup_path(
        "artifact.bin",
        backup_root=root,
    )

    write_artifact(
        path,
        b"first",
    )

    write_artifact(
        path,
        b"second",
        overwrite=True,
    )

    assert path.read_bytes() == (
        b"second"
    )


def test_verify_artifact_exists_rejects_missing_artifact(
    tmp_path,
):
    with pytest.raises(
        BackupStorageError,
        match="does not exist",
    ):
        verify_artifact_exists(
            tmp_path
            / "missing.dump"
        )


def test_verify_artifact_exists_rejects_directory(
    tmp_path,
):
    directory = (
        tmp_path
        / "artifact"
    )

    directory.mkdir()

    with pytest.raises(
        BackupStorageError,
        match="is not a file",
    ):
        verify_artifact_exists(
            directory
        )


def test_calculate_sha256_returns_expected_checksum(
    tmp_path,
):
    artifact = (
        tmp_path
        / "artifact.bin"
    )

    payload = (
        b"synthetic-backup"
    )

    artifact.write_bytes(
        payload
    )

    expected = (
        hashlib.sha256(
            payload
        ).hexdigest()
    )

    assert calculate_sha256(
        artifact
    ) == expected


def test_read_artifact_returns_exact_bytes(
    tmp_path,
):
    artifact = (
        tmp_path
        / "artifact.bin"
    )

    payload = (
        b"backup-payload"
    )

    artifact.write_bytes(
        payload
    )

    assert read_artifact(
        artifact
    ) == payload


def test_write_and_read_metadata(
    tmp_path,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    metadata = {
        "backup_id": "abc123",
        "success": True,
        "file_count": 3,
        "size_bytes": 512,
    }

    metadata_path = write_metadata(
        backup_directory,
        metadata,
    )

    assert metadata_path.exists()

    assert read_metadata(
        backup_directory
    ) == metadata


def test_write_metadata_rejects_existing_metadata(
    tmp_path,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    metadata = {
        "backup_id": "abc123",
    }

    write_metadata(
        backup_directory,
        metadata,
    )

    with pytest.raises(
        BackupStorageError,
        match="already exists",
    ):
        write_metadata(
            backup_directory,
            metadata,
        )


def test_write_metadata_supports_explicit_overwrite(
    tmp_path,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    write_metadata(
        backup_directory,
        {
            "version": 1,
        },
    )

    write_metadata(
        backup_directory,
        {
            "version": 2,
        },
        overwrite=True,
    )

    assert read_metadata(
        backup_directory
    ) == {
        "version": 2,
    }


def test_read_metadata_rejects_invalid_json(
    tmp_path,
):
    backup_directory = (
        tmp_path
        / "backup"
    )

    backup_directory.mkdir()

    (
        backup_directory
        / "metadata.json"
    ).write_text(
        "{invalid",
        encoding="utf-8",
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to read backup metadata",
    ):
        read_metadata(
            backup_directory
        )


def test_metadata_filename_cannot_escape_directory(
    tmp_path,
):
    with pytest.raises(
        BackupStorageError,
        match="Invalid metadata filename",
    ):
        write_metadata(
            tmp_path
            / "backup",
            {
                "test": True,
            },
            filename="../metadata.json",
        )