from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import current_app


DEFAULT_RETENTION_DAYS = 30
DEFAULT_MIN_RECOVERY_POINTS = 1
METADATA_FILENAME = "metadata.json"


class BackupRetentionError(Exception):
    pass


@dataclass(frozen=True)
class BackupRetentionCandidate:
    backup_path: str
    backup_id: str
    created_at: datetime
    expired: bool
    protected: bool


@dataclass(frozen=True)
class BackupDeletionResult:
    backup_path: str
    backup_id: str
    deleted: bool
    reason: str


@dataclass(frozen=True)
class BackupRetentionResult:
    success: bool
    retention_days: int
    minimum_recovery_points: int
    cutoff_at: str
    scanned_count: int
    expired_count: int
    protected_count: int
    deleted_count: int
    preserved_count: int
    deletions: tuple[BackupDeletionResult, ...]


def _get_retention_days(
    retention_days: int | None,
) -> int:
    if retention_days is None:
        retention_days = current_app.config.get(
            "BACKUP_RETENTION_DAYS",
            DEFAULT_RETENTION_DAYS,
        )

    if (
        isinstance(
            retention_days,
            bool,
        )
        or not isinstance(
            retention_days,
            int,
        )
    ):
        raise BackupRetentionError(
            "Backup retention days must be a positive integer"
        )

    if retention_days <= 0:
        raise BackupRetentionError(
            "Backup retention days must be a positive integer"
        )

    return retention_days


def _get_minimum_recovery_points(
    minimum_recovery_points: int | None,
) -> int:
    if minimum_recovery_points is None:
        minimum_recovery_points = (
            current_app.config.get(
                "BACKUP_MIN_RECOVERY_POINTS",
                DEFAULT_MIN_RECOVERY_POINTS,
            )
        )

    if (
        isinstance(
            minimum_recovery_points,
            bool,
        )
        or not isinstance(
            minimum_recovery_points,
            int,
        )
    ):
        raise BackupRetentionError(
            "Minimum recovery points must be a non-negative integer"
        )

    if minimum_recovery_points < 0:
        raise BackupRetentionError(
            "Minimum recovery points must be a non-negative integer"
        )

    return minimum_recovery_points


def _resolve_backup_root(
    backup_root: str | Path,
) -> Path:
    root = Path(
        backup_root
    ).resolve()

    if not root.exists():
        raise BackupRetentionError(
            "Backup root does not exist"
        )

    if not root.is_dir():
        raise BackupRetentionError(
            "Backup root is not a directory"
        )

    return root


def _parse_created_at(
    value: Any,
) -> datetime:
    if not isinstance(
        value,
        str,
    ):
        raise BackupRetentionError(
            "Backup created_at must be an ISO-8601 string"
        )

    value = value.strip()

    if not value:
        raise BackupRetentionError(
            "Backup created_at cannot be empty"
        )

    try:
        parsed = datetime.fromisoformat(
            value
        )
    except ValueError as exc:
        raise BackupRetentionError(
            "Backup created_at is invalid"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _read_metadata(
    backup_directory: Path,
) -> dict[str, Any] | None:
    metadata_path = (
        backup_directory
        / METADATA_FILENAME
    )

    if not metadata_path.exists():
        return None

    if not metadata_path.is_file():
        raise BackupRetentionError(
            "Backup metadata path is not a file"
        )

    try:
        import json

        with metadata_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            value = json.load(
                handle
            )
    except (
        OSError,
        ValueError,
    ) as exc:
        raise BackupRetentionError(
            "Unable to read backup metadata"
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise BackupRetentionError(
            "Backup metadata must be a JSON object"
        )

    return value


def _discover_backups(
    backup_root: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    discovered: list[
        tuple[Path, dict[str, Any]]
    ] = []

    try:
        directories = sorted(
            (
                path
                for path in backup_root.iterdir()
                if path.is_dir()
                and not path.is_symlink()
            ),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise BackupRetentionError(
            f"Unable to inspect backup root: {exc}"
        ) from exc

    for directory in directories:
        metadata = _read_metadata(
            directory
        )

        if metadata is None:
            continue

        if metadata.get(
            "success"
        ) is not True:
            continue

        backup_id = metadata.get(
            "backup_id"
        )

        if not isinstance(
            backup_id,
            str,
        ) or not backup_id.strip():
            raise BackupRetentionError(
                "Backup metadata is missing backup_id"
            )

        _parse_created_at(
            metadata.get(
                "created_at"
            )
        )

        discovered.append(
            (
                directory,
                metadata,
            )
        )

    return discovered


def identify_expired_backups(
    *,
    backup_root: str | Path,
    retention_days: int | None = None,
    minimum_recovery_points: int | None = None,
    now: datetime | None = None,
) -> tuple[
    BackupRetentionCandidate,
    ...
]:
    root = _resolve_backup_root(
        backup_root
    )

    days = None
    minimum_points = None

    if retention_days is not None:
        days = _get_retention_days(
            retention_days
        )

    if minimum_recovery_points is not None:
        minimum_points = (
            _get_minimum_recovery_points(
                minimum_recovery_points
            )
        )

    if days is None:
        days = _get_retention_days(
            None
        )

    if minimum_points is None:
        minimum_points = (
            _get_minimum_recovery_points(
                None
            )
        )

    if now is None:
        now = datetime.now(
            timezone.utc
        )
    elif now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )
    else:
        now = now.astimezone(
            timezone.utc
        )

    cutoff = (
        now
        - timedelta(
            days=days
        )
    )

    backups = _discover_backups(
        root
    )

    backups.sort(
        key=lambda item: _parse_created_at(
            item[1]["created_at"]
        ),
        reverse=True,
    )

    protected_ids = {
        metadata["backup_id"]
        for _, metadata in backups[:minimum_points]
    }

    candidates = []

    for directory, metadata in backups:
        created_at = _parse_created_at(
            metadata["created_at"]
        )

        expired = (
            created_at < cutoff
        )

        protected = (
            metadata["backup_id"]
            in protected_ids
        )

        candidates.append(
            BackupRetentionCandidate(
                backup_path=str(
                    directory
                ),
                backup_id=str(
                    metadata["backup_id"]
                ),
                created_at=created_at,
                expired=expired,
                protected=protected,
            )
        )

    return tuple(candidates)


def apply_backup_retention(
    *,
    backup_root: str | Path,
    retention_days: int | None = None,
    minimum_recovery_points: int | None = None,
    now: datetime | None = None,
) -> BackupRetentionResult:
    root = _resolve_backup_root(
        backup_root
    )

    days = None
    minimum_points = None

    if retention_days is not None:
        days = _get_retention_days(
            retention_days
        )

    if minimum_recovery_points is not None:
        minimum_points = (
            _get_minimum_recovery_points(
                minimum_recovery_points
            )
        )

    if days is None:
        days = _get_retention_days(
            None
        )

    if minimum_points is None:
        minimum_points = (
            _get_minimum_recovery_points(
                None
            )
        )

    if now is None:
        now = datetime.now(
            timezone.utc
        )
    elif now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )
    else:
        now = now.astimezone(
            timezone.utc
        )

    cutoff = (
        now
        - timedelta(
            days=days
        )
    )

    candidates = identify_expired_backups(
        backup_root=root,
        retention_days=days,
        minimum_recovery_points=minimum_points,
        now=now,
    )

    deletions: list[
        BackupDeletionResult
    ] = []

    expired_count = 0
    protected_count = 0
    deleted_count = 0
    preserved_count = 0

    for candidate in candidates:
        if not candidate.expired:
            preserved_count += 1

            deletions.append(
                BackupDeletionResult(
                    backup_path=(
                        candidate.backup_path
                    ),
                    backup_id=(
                        candidate.backup_id
                    ),
                    deleted=False,
                    reason=(
                        "inside retention window"
                    ),
                )
            )

            continue

        expired_count += 1

        if candidate.protected:
            protected_count += 1
            preserved_count += 1

            deletions.append(
                BackupDeletionResult(
                    backup_path=(
                        candidate.backup_path
                    ),
                    backup_id=(
                        candidate.backup_id
                    ),
                    deleted=False,
                    reason=(
                        "protected recovery point"
                    ),
                )
            )

            continue

        backup_directory = Path(
            candidate.backup_path
        ).resolve()

        try:
            backup_directory.relative_to(
                root
            )
        except ValueError as exc:
            raise BackupRetentionError(
                "Backup path escapes backup root"
            ) from exc

        try:
            shutil.rmtree(
                backup_directory
            )
        except OSError as exc:
            raise BackupRetentionError(
                "Unable to delete expired backup "
                f"{candidate.backup_id}"
            ) from exc

        deleted_count += 1

        deletions.append(
            BackupDeletionResult(
                backup_path=(
                    candidate.backup_path
                ),
                backup_id=(
                    candidate.backup_id
                ),
                deleted=True,
                reason="expired",
            )
        )

    return BackupRetentionResult(
        success=True,
        retention_days=days,
        minimum_recovery_points=(
            minimum_points
        ),
        cutoff_at=cutoff.isoformat(),
        scanned_count=len(
            candidates
        ),
        expired_count=expired_count,
        protected_count=protected_count,
        deleted_count=deleted_count,
        preserved_count=preserved_count,
        deletions=tuple(
            deletions
        ),
    )