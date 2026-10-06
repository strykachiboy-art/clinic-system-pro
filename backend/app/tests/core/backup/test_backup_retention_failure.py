from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.backup.backup_retention import (
    BackupRetentionError,
    apply_backup_retention,
)


def _write_backup(
    root: Path,
    backup_id: str,
    created_at: str,
) -> Path:
    directory = (
        root
        / backup_id
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {
        "success": True,
        "backup_id": backup_id,
        "created_at": created_at,
    }

    (
        directory
        / "metadata.json"
    ).write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    (
        directory
        / "database.dump"
    ).write_bytes(
        b"backup"
    )

    return directory


def test_apply_backup_retention_reports_deletion_failure_without_false_success(
    app,
    tmp_path,
    monkeypatch,
):
    backup_root = (
        tmp_path
        / "backups"
    )

    now = datetime(
        2026,
        10,
        6,
        tzinfo=timezone.utc,
    )

    first = _write_backup(
        backup_root,
        "backup-old-001",
        "2026-08-02T00:00:00+00:00",
    )

    second = _write_backup(
        backup_root,
        "backup-old-002",
        "2026-08-01T00:00:00+00:00",
    )

    original_rmtree = (
        __import__(
            "app.core.backup.backup_retention",
            fromlist=["shutil"],
        ).shutil.rmtree
    )

    calls = []

    def failing_rmtree(
        path,
        *args,
        **kwargs,
    ):
        calls.append(
            Path(path)
        )

        if Path(path).name == (
            "backup-old-002"
        ):
            raise OSError(
                "simulated retention deletion failure"
            )

        return original_rmtree(
            path,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        "app.core.backup.backup_retention.shutil.rmtree",
        failing_rmtree,
    )

    with app.app_context():
        with pytest.raises(
            BackupRetentionError,
            match="Unable to delete expired backup",
        ):
            apply_backup_retention(
                backup_root=backup_root,
                retention_days=30,
                minimum_recovery_points=0,
                now=now,
            )

    assert first.exists() is False

    assert second.exists() is True

    assert calls == [
        first,
        second,
    ]

    remaining = sorted(
        path.name
        for path in backup_root.iterdir()
        if path.is_dir()
    )

    assert remaining == [
        "backup-old-002"
    ]
