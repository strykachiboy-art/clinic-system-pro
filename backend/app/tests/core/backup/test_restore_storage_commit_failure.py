from __future__ import annotations

from pathlib import Path

import pytest

from app.core.backup import restore_service
from app.core.backup.restore_service import RestoreError


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


def test_commit_storage_restore_rolls_back_existing_storage_on_commit_failure(
    tmp_path,
    monkeypatch,
):
    storage_root = (
        tmp_path
        / "storage"
    )

    staging_root = (
        tmp_path
        / "storage.restore-stage"
    )

    _write_file(
        storage_root
        / "existing.txt",
        b"existing-data",
    )

    _write_file(
        staging_root
        / "restored.txt",
        b"restored-data",
    )

    original_move = restore_service.shutil.move
    calls = {
        "count": 0,
    }

    def fail_final_move(
        source,
        destination,
    ):
        calls["count"] += 1

        if calls["count"] == 2:
            raise OSError(
                "synthetic storage commit failure"
            )

        return original_move(
            source,
            destination,
        )

    monkeypatch.setattr(
        restore_service.shutil,
        "move",
        fail_final_move,
    )

    with pytest.raises(
        RestoreError,
        match="Unable to commit storage restore",
    ):
        restore_service._commit_storage_restore(
            staging_root=staging_root,
            storage_root=storage_root,
            replace_existing=True,
        )

    assert calls["count"] == 3

    assert (
        storage_root
        / "existing.txt"
    ).read_bytes() == (
        b"existing-data"
    )

    assert not (
        storage_root
        / "restored.txt"
    ).exists()

    assert list(
        tmp_path.glob(
            "storage.restore-old-*"
        )
    ) == []

    assert staging_root.exists()


def test_commit_storage_restore_reports_rollback_failure_without_false_success(
    tmp_path,
    monkeypatch,
):
    storage_root = (
        tmp_path
        / "storage"
    )

    staging_root = (
        tmp_path
        / "storage.restore-stage"
    )

    _write_file(
        storage_root
        / "existing.txt",
        b"existing-data",
    )

    _write_file(
        staging_root
        / "restored.txt",
        b"restored-data",
    )

    original_move = restore_service.shutil.move
    calls = {
        "count": 0,
    }

    def fail_rollback_move(
        source,
        destination,
    ):
        calls["count"] += 1

        if calls["count"] in {
            2,
            3,
        }:
            raise OSError(
                "synthetic storage move failure"
            )

        return original_move(
            source,
            destination,
        )

    monkeypatch.setattr(
        restore_service.shutil,
        "move",
        fail_rollback_move,
    )

    with pytest.raises(
        RestoreError,
        match="rollback was unsuccessful",
    ):
        restore_service._commit_storage_restore(
            staging_root=staging_root,
            storage_root=storage_root,
            replace_existing=True,
        )

    assert calls["count"] == 3

    assert not storage_root.exists()

    rollback_paths = list(
        tmp_path.glob(
            "storage.restore-old-*"
        )
    )

    assert len(rollback_paths) == 1

    rollback_root = rollback_paths[0]

    assert (
        rollback_root
        / "existing.txt"
    ).read_bytes() == (
        b"existing-data"
    )

    assert staging_root.exists()
