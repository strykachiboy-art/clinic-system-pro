from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.backup.backup_retention import (
    BackupRetentionError,
    apply_backup_retention,
    identify_expired_backups,
)


NOW = datetime(
    2026,
    9,
    24,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def _create_backup(
    root: Path,
    *,
    backup_id: str,
    created_at: datetime,
    success: bool = True,
):
    directory = (
        root
        / backup_id
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {
        "version": 1,
        "backup_id": backup_id,
        "created_at": created_at.isoformat(),
        "success": success,
    }

    (
        directory
        / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (
        directory
        / "artifact.bin"
    ).write_bytes(
        b"backup"
    )

    return directory


def test_identify_expired_backups_marks_old_backup(
    tmp_path,
):
    old_backup = _create_backup(
        tmp_path,
        backup_id="old",
        created_at=(
            NOW
            - timedelta(
                days=31
            )
        ),
    )

    candidates = identify_expired_backups(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].backup_path == str(
        old_backup
    )
    assert candidates[0].expired is True
    assert candidates[0].protected is False


def test_identify_expired_backups_preserves_active_backup(
    tmp_path,
):
    active = _create_backup(
        tmp_path,
        backup_id="active",
        created_at=(
            NOW
            - timedelta(
                days=10
            )
        ),
    )

    candidates = identify_expired_backups(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert candidates[0].backup_path == str(
        active
    )
    assert candidates[0].expired is False


def test_apply_backup_retention_deletes_expired_backup(
    tmp_path,
):
    expired = _create_backup(
        tmp_path,
        backup_id="expired",
        created_at=(
            NOW
            - timedelta(
                days=31
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.success is True
    assert result.deleted_count == 1
    assert result.expired_count == 1
    assert not expired.exists()


def test_apply_backup_retention_preserves_backup_inside_window(
    tmp_path,
):
    active = _create_backup(
        tmp_path,
        backup_id="active",
        created_at=(
            NOW
            - timedelta(
                days=29
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.deleted_count == 0
    assert result.preserved_count == 1
    assert active.exists()


def test_apply_backup_retention_preserves_latest_recovery_point(
    tmp_path,
):
    latest = _create_backup(
        tmp_path,
        backup_id="latest",
        created_at=(
            NOW
            - timedelta(
                days=60
            )
        ),
    )

    older = _create_backup(
        tmp_path,
        backup_id="older",
        created_at=(
            NOW
            - timedelta(
                days=61
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=1,
        now=NOW,
    )

    assert latest.exists()
    assert not older.exists()

    assert result.deleted_count == 1
    assert result.protected_count == 1


def test_apply_backup_retention_preserves_multiple_required_points(
    tmp_path,
):
    first = _create_backup(
        tmp_path,
        backup_id="first",
        created_at=(
            NOW
            - timedelta(
                days=60
            )
        ),
    )

    second = _create_backup(
        tmp_path,
        backup_id="second",
        created_at=(
            NOW
            - timedelta(
                days=61
            )
        ),
    )

    third = _create_backup(
        tmp_path,
        backup_id="third",
        created_at=(
            NOW
            - timedelta(
                days=62
            )
        ),
    )

    apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=2,
        now=NOW,
    )

    assert first.exists()
    assert second.exists()
    assert not third.exists()


def test_apply_backup_retention_ignores_unsuccessful_backup(
    tmp_path,
):
    failed = _create_backup(
        tmp_path,
        backup_id="failed",
        created_at=(
            NOW
            - timedelta(
                days=60
            )
        ),
        success=False,
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.scanned_count == 0
    assert result.deleted_count == 0
    assert failed.exists()


def test_apply_backup_retention_ignores_non_backup_directories(
    tmp_path,
):
    unrelated = (
        tmp_path
        / "not-a-backup"
    )

    unrelated.mkdir()

    (
        unrelated
        / "data.txt"
    ).write_text(
        "keep me",
        encoding="utf-8",
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.scanned_count == 0
    assert unrelated.exists()


def test_apply_backup_retention_requires_valid_retention_days(
    tmp_path,
):
    with pytest.raises(
        BackupRetentionError,
        match="positive integer",
    ):
        apply_backup_retention(
            backup_root=tmp_path,
            retention_days=0,
            now=NOW,
        )


def test_apply_backup_retention_rejects_boolean_retention_days(
    tmp_path,
):
    with pytest.raises(
        BackupRetentionError,
        match="positive integer",
    ):
        apply_backup_retention(
            backup_root=tmp_path,
            retention_days=True,
            now=NOW,
        )


def test_apply_backup_retention_requires_valid_minimum_points(
    tmp_path,
):
    with pytest.raises(
        BackupRetentionError,
        match="non-negative integer",
    ):
        apply_backup_retention(
            backup_root=tmp_path,
            minimum_recovery_points=-1,
            now=NOW,
        )


def test_apply_backup_retention_rejects_boolean_minimum_points(
    tmp_path,
):
    with pytest.raises(
        BackupRetentionError,
        match="non-negative integer",
    ):
        apply_backup_retention(
            backup_root=tmp_path,
            minimum_recovery_points=True,
            now=NOW,
        )


def test_apply_backup_retention_reports_deletion_reason(
    tmp_path,
):
    _create_backup(
        tmp_path,
        backup_id="expired",
        created_at=(
            NOW
            - timedelta(
                days=31
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.deletions[0].deleted is True
    assert result.deletions[0].reason == (
        "expired"
    )


def test_apply_backup_retention_reports_protected_reason(
    tmp_path,
):
    _create_backup(
        tmp_path,
        backup_id="protected",
        created_at=(
            NOW
            - timedelta(
                days=31
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=1,
        now=NOW,
    )

    assert result.deletions[0].deleted is False
    assert result.deletions[0].reason == (
        "protected recovery point"
    )


def test_apply_backup_retention_reports_active_reason(
    tmp_path,
):
    _create_backup(
        tmp_path,
        backup_id="active",
        created_at=(
            NOW
            - timedelta(
                days=1
            )
        ),
    )

    result = apply_backup_retention(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert result.deletions[0].deleted is False
    assert result.deletions[0].reason == (
        "inside retention window"
    )


def test_identify_expired_backups_orders_newest_first(
    tmp_path,
):
    newest = _create_backup(
        tmp_path,
        backup_id="newest",
        created_at=(
            NOW
            - timedelta(
                days=31
            )
        ),
    )

    older = _create_backup(
        tmp_path,
        backup_id="older",
        created_at=(
            NOW
            - timedelta(
                days=32
            )
        ),
    )

    candidates = identify_expired_backups(
        backup_root=tmp_path,
        retention_days=30,
        minimum_recovery_points=0,
        now=NOW,
    )

    assert candidates[0].backup_path == str(
        newest
    )

    assert candidates[1].backup_path == str(
        older
    )


def test_apply_backup_retention_rejects_missing_root(
    tmp_path,
):
    with pytest.raises(
        BackupRetentionError,
        match="does not exist",
    ):
        apply_backup_retention(
            backup_root=(
                tmp_path
                / "missing"
            ),
            retention_days=30,
            now=NOW,
        )