from pathlib import Path

import pytest

from app.core.backup.backup_storage import (
    BackupStorageError,
    read_artifact,
)


def test_read_artifact_wraps_filesystem_failure(
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(
        b"backup-payload"
    )

    def fail_read_bytes(self):
        raise OSError(
            "synthetic read denial"
        )

    monkeypatch.setattr(
        Path,
        "read_bytes",
        fail_read_bytes,
    )

    with pytest.raises(
        BackupStorageError,
        match="Unable to read backup artifact",
    ) as exc_info:
        read_artifact(
            artifact
        )

    assert isinstance(
        exc_info.value.__cause__,
        OSError,
    )
    assert "synthetic read denial" in str(
        exc_info.value.__cause__
    )
