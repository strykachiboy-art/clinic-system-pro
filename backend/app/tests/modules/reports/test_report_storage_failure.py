from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.enums.reports_enums import (
    ReportFormat,
    ReportType,
)
from app.extensions import db
from app.modules.reports.services import (
    reports_service as service,
)


def _storage_files(
    storage_root: Path,
) -> list[Path]:
    if not storage_root.exists():
        return []

    return sorted(
        path
        for path in storage_root.rglob("*")
        if path.is_file()
    )


def test_report_temp_write_failure_cleans_partial_artifact(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    real_open = open

    class FailingWriter:
        def __init__(
            self,
            path,
            mode,
        ):
            self._file = real_open(
                path,
                mode,
            )

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            self._file.close()
            return False

        def write(
            self,
            data,
        ):
            partial = data[
                : max(
                    1,
                    len(data) // 2,
                )
            ]

            self._file.write(
                partial
            )

            self._file.flush()

            raise OSError(
                "simulated report temp write failure"
            )

        def __getattr__(
            self,
            name,
        ):
            return getattr(
                self._file,
                name,
            )

    def failing_open(
        path,
        mode="r",
        *args,
        **kwargs,
    ):
        if str(path).endswith(
            ".tmp"
        ):
            return FailingWriter(
                path,
                mode,
            )

        return real_open(
            path,
            mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        service,
        "open",
        failing_open,
        raising=False,
    )

    with pytest.raises(
        OSError,
        match="simulated report temp write failure",
    ):
        service._save_report_file(
            clinic_id=10,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            content=b"report-content",
        )

    storage_root = (
        tmp_path
        / service.DEFAULT_STORAGE_DIR
    )

    assert storage_root.exists()

    assert _storage_files(
        storage_root
    ) == []


def test_report_db_commit_failure_does_not_leave_persisted_artifact(
    app,
    user,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    clinic_id = user.clinic_id

    if clinic_id is None:
        pytest.fail(
            "Test user must have a clinic assignment"
        )

    requester = SimpleNamespace(
        id=user.id,
        clinic_id=clinic_id,
        user=SimpleNamespace(
            id=user.id,
            clinic_id=clinic_id,
            is_active=True,
        ),
    )

    generator = SimpleNamespace(
        id=100,
        clinic_id=clinic_id,
    )

    monkeypatch.setattr(
        service,
        "_get_requester",
        lambda requester_user_id: requester,
    )

    monkeypatch.setattr(
        service,
        "_validate_report_generator",
        lambda resolved_requester, requested_clinic_id: generator,
    )

    monkeypatch.setattr(
        service,
        "_require_active_clinic",
        lambda requested_clinic_id: SimpleNamespace(
            id=requested_clinic_id,
        ),
    )

    monkeypatch.setitem(
        service._GATHERERS,
        ReportType.PATIENTS,
        lambda requested_clinic_id, filters: [
            {
                "id": 1,
                "name": "failure-test",
            },
        ],
    )

    monkeypatch.setattr(
        service,
        "GeneratedReport",
        lambda **kwargs: SimpleNamespace(
            id=999,
            **kwargs,
        ),
    )

    monkeypatch.setattr(
        service.db.session,
        "add",
        lambda obj: None,
    )

    monkeypatch.setattr(
        service.db.session,
        "flush",
        lambda: None,
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        lambda *args, **kwargs: None,
    )

    real_commit = db.session.commit

    def fail_commit():
        raise RuntimeError(
            "simulated report database commit failure"
        )

    monkeypatch.setattr(
        db.session,
        "commit",
        fail_commit,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated report database commit failure",
    ):
        service.generate_report(
            requester_user_id=user.id,
            clinic_id=clinic_id,
            report_type=ReportType.PATIENTS,
            report_format=ReportFormat.CSV,
            filters=None,
        )

    monkeypatch.setattr(
        db.session,
        "commit",
        real_commit,
    )

    storage_root = (
        tmp_path
        / service.DEFAULT_STORAGE_DIR
    )

    assert storage_root.exists()

    files = _storage_files(
        storage_root
    )

    assert files == []