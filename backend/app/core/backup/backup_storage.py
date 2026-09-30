from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import current_app


DEFAULT_BACKUP_DIRECTORY = "backups"
DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024
METADATA_FILENAME = "metadata.json"


class BackupStorageError(Exception):
    pass


def _get_configured_backup_root() -> Path:
    configured_root = current_app.config.get(
        "BACKUP_ROOT"
    )

    if configured_root:
        root = Path(
            configured_root
        )
    else:
        root = (
            Path(
                current_app.instance_path
            )
            / DEFAULT_BACKUP_DIRECTORY
        )

    return root.resolve()


def _validate_relative_path(
    relative_path: str | Path,
) -> Path:
    path = Path(
        relative_path
    )

    if path.is_absolute():
        raise BackupStorageError(
            "Backup path must be relative"
        )

    if not path.parts:
        raise BackupStorageError(
            "Backup path cannot be empty"
        )

    if any(
        part in {
            "",
            ".",
            "..",
        }
        for part in path.parts
    ):
        raise BackupStorageError(
            "Invalid backup path"
        )

    return path


def _ensure_within_root(
    root: Path,
    target: Path,
) -> None:
    try:
        target.relative_to(
            root
        )
    except ValueError as exc:
        raise BackupStorageError(
            "Backup path escapes the backup root"
        ) from exc


def resolve_backup_path(
    relative_path: str | Path,
    *,
    backup_root: str | Path | None = None,
) -> Path:
    relative = _validate_relative_path(
        relative_path
    )

    root = (
        _get_configured_backup_root()
        if backup_root is None
        else Path(
            backup_root
        ).resolve()
    )

    target = (
        root
        / relative
    ).resolve()

    _ensure_within_root(
        root,
        target,
    )

    return target


def create_backup_directory(
    relative_path: str | Path = "",
    *,
    backup_root: str | Path | None = None,
) -> Path:
    if relative_path == "":
        directory = (
            _get_configured_backup_root()
            if backup_root is None
            else Path(
                backup_root
            ).resolve()
        )
    else:
        directory = resolve_backup_path(
            relative_path,
            backup_root=backup_root,
        )

    try:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise BackupStorageError(
            f"Unable to create backup directory: {exc}"
        ) from exc

    return directory


def generate_safe_backup_path(
    *,
    prefix: str = "backup",
    extension: str | None = None,
    relative_directory: str | Path = "",
    backup_root: str | Path | None = None,
) -> Path:
    if not isinstance(
        prefix,
        str,
    ):
        raise BackupStorageError(
            "Backup filename prefix must be a string"
        )

    prefix = prefix.strip()

    if not prefix:
        raise BackupStorageError(
            "Backup filename prefix cannot be empty"
        )

    if Path(prefix).name != prefix:
        raise BackupStorageError(
            "Backup filename prefix cannot contain path separators"
        )

    if extension is not None:
        if not isinstance(
            extension,
            str,
        ):
            raise BackupStorageError(
                "Backup extension must be a string"
            )

        extension = extension.strip()

        if extension:
            extension = (
                extension.lstrip(".")
            )

            if not extension.isidentifier():
                raise BackupStorageError(
                    "Invalid backup extension"
                )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    unique_id = uuid4().hex

    filename = (
        f"{prefix}-"
        f"{timestamp}-"
        f"{unique_id}"
    )

    if extension:
        filename = (
            f"{filename}."
            f"{extension}"
        )

    if relative_directory == "":
        relative_path = Path(
            filename
        )
    else:
        directory = _validate_relative_path(
            relative_directory
        )

        relative_path = (
            directory
            / filename
        )

    path = resolve_backup_path(
        relative_path,
        backup_root=backup_root,
    )

    try:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise BackupStorageError(
            f"Unable to create backup directory: {exc}"
        ) from exc

    return path


def write_artifact(
    path: str | Path,
    data: bytes,
    *,
    overwrite: bool = False,
) -> Path:
    if not isinstance(
        data,
        bytes,
    ):
        raise BackupStorageError(
            "Backup artifact data must be bytes"
        )

    target = Path(
        path
    ).resolve()

    parent = target.parent

    try:
        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        mode = (
            "wb"
            if overwrite
            else "xb"
        )

        with target.open(
            mode
        ) as handle:
            handle.write(
                data
            )

    except FileExistsError as exc:
        raise BackupStorageError(
            "Backup artifact already exists"
        ) from exc

    except OSError as exc:
        raise BackupStorageError(
            f"Unable to write backup artifact: {exc}"
        ) from exc

    return target


def verify_artifact_exists(
    path: str | Path,
) -> Path:
    target = Path(
        path
    ).resolve()

    if not target.exists():
        raise BackupStorageError(
            "Backup artifact does not exist"
        )

    if not target.is_file():
        raise BackupStorageError(
            "Backup artifact is not a file"
        )

    return target


def calculate_sha256(
    path: str | Path,
) -> str:
    target = verify_artifact_exists(
        path
    )

    digest = hashlib.sha256()

    try:
        with target.open(
            "rb"
        ) as handle:
            while True:
                chunk = handle.read(
                    DEFAULT_HASH_CHUNK_SIZE
                )

                if not chunk:
                    break

                digest.update(
                    chunk
                )

    except OSError as exc:
        raise BackupStorageError(
            f"Unable to read backup artifact: {exc}"
        ) from exc

    return digest.hexdigest()


def read_artifact(
    path: str | Path,
) -> bytes:
    target = verify_artifact_exists(
        path
    )

    try:
        return target.read_bytes()
    except OSError as exc:
        raise BackupStorageError(
            f"Unable to read backup artifact: {exc}"
        ) from exc


def write_metadata(
    backup_directory: str | Path,
    metadata: dict[str, Any],
    *,
    filename: str = METADATA_FILENAME,
    overwrite: bool = False,
) -> Path:
    if not isinstance(
        metadata,
        dict,
    ):
        raise BackupStorageError(
            "Backup metadata must be a dictionary"
        )

    if not isinstance(
        filename,
        str,
    ):
        raise BackupStorageError(
            "Metadata filename must be a string"
        )

    filename = filename.strip()

    if not filename:
        raise BackupStorageError(
            "Metadata filename cannot be empty"
        )

    if Path(filename).name != filename:
        raise BackupStorageError(
            "Invalid metadata filename"
        )

    directory = Path(
        backup_directory
    ).resolve()

    try:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise BackupStorageError(
            f"Unable to create metadata directory: {exc}"
        ) from exc

    metadata_path = (
        directory
        / filename
    ).resolve()

    _ensure_within_root(
        directory,
        metadata_path,
    )

    payload = json.dumps(
        metadata,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    temporary_path = (
        directory
        / (
            f".{filename}."
            f"{uuid4().hex}.tmp"
        )
    )

    try:
        with temporary_path.open(
            "x",
            encoding="utf-8",
        ) as handle:
            handle.write(
                payload
            )

        if metadata_path.exists():
            if not overwrite:
                temporary_path.unlink(
                    missing_ok=True
                )

                raise BackupStorageError(
                    "Backup metadata already exists"
                )

            temporary_path.replace(
                metadata_path
            )
        else:
            temporary_path.replace(
                metadata_path
            )

    except BackupStorageError:
        raise

    except (
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        temporary_path.unlink(
            missing_ok=True
        )

        raise BackupStorageError(
            f"Unable to write backup metadata: {exc}"
        ) from exc

    return metadata_path


def read_metadata(
    backup_directory: str | Path,
    *,
    filename: str = METADATA_FILENAME,
) -> dict[str, Any]:
    if not isinstance(
        filename,
        str,
    ):
        raise BackupStorageError(
            "Metadata filename must be a string"
        )

    filename = filename.strip()

    if not filename:
        raise BackupStorageError(
            "Metadata filename cannot be empty"
        )

    if Path(filename).name != filename:
        raise BackupStorageError(
            "Invalid metadata filename"
        )

    directory = Path(
        backup_directory
    ).resolve()

    metadata_path = (
        directory
        / filename
    ).resolve()

    _ensure_within_root(
        directory,
        metadata_path,
    )

    verify_artifact_exists(
        metadata_path
    )

    try:
        with metadata_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            value = json.load(
                handle
            )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise BackupStorageError(
            f"Unable to read backup metadata: {exc}"
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise BackupStorageError(
            "Backup metadata must contain a JSON object"
        )

    return value