from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.core.storage import storage_service


PAYLOAD = (
    b"\x89PNG\r\n\x1a\n"
    b"storage-failure-payload"
)


class FailDuringWritePhaseRead:
    def __init__(self, payload: bytes):
        self._stream = BytesIO(payload)
        self._seek_zero_calls = 0
        self._write_phase = False
        self._write_phase_reads = 0

    def tell(self):
        return self._stream.tell()

    def seek(self, offset, whence=0):
        result = self._stream.seek(offset, whence)

        if offset == 0 and whence == 0:
            self._seek_zero_calls += 1

            if self._seek_zero_calls >= 2:
                self._write_phase = True
                self._write_phase_reads = 0

        return result

    def read(self, size=-1):
        if self._write_phase:
            self._write_phase_reads += 1

            if self._write_phase_reads == 2:
                raise OSError(
                    "simulated storage stream read failure"
                )

        return self._stream.read(size)


class FailingWriter:
    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._wrapped.__exit__(
            exc_type,
            exc,
            traceback,
        )

    def write(self, data):
        self._wrapped.write(data[:4])

        raise OSError(
            "simulated storage write failure"
        )

    def __getattr__(self, name):
        return getattr(
            self._wrapped,
            name,
        )


def make_upload(
    stream,
    *,
    filename="profile.png",
    mimetype="image/png",
    content_length=None,
):
    if content_length is None:
        content_length = len(PAYLOAD)

    return FileStorage(
        stream=stream,
        filename=filename,
        content_type=mimetype,
        content_length=content_length,
    )


def list_storage_files(
    storage_root: Path,
) -> list[Path]:
    if not storage_root.exists():
        return []

    return [
        path
        for path in storage_root.rglob("*")
        if path.is_file()
    ]


def test_profile_image_mid_stream_read_failure_cleans_partial_file(
    app,
    tmp_path,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    stream = FailDuringWritePhaseRead(
        PAYLOAD
    )

    upload = make_upload(
        stream,
    )

    with pytest.raises(
        OSError,
        match="simulated storage stream read failure",
    ):
        storage_service.save_profile_image(
            upload
        )

    assert list_storage_files(
        storage_root
    ) == []


def test_profile_image_destination_write_failure_cleans_partial_file_and_retry_is_safe(
    app,
    tmp_path,
    monkeypatch,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    real_open = Path.open

    def failing_open(
        path,
        mode="r",
        *args,
        **kwargs,
    ):
        wrapped = real_open(
            path,
            mode,
            *args,
            **kwargs,
        )

        if mode == "xb":
            return FailingWriter(
                wrapped
            )

        return wrapped

    monkeypatch.setattr(
        Path,
        "open",
        failing_open,
    )

    upload = make_upload(
        BytesIO(PAYLOAD),
    )

    with pytest.raises(
        OSError,
        match="simulated storage write failure",
    ):
        storage_service.save_profile_image(
            upload
        )

    assert list_storage_files(
        storage_root
    ) == []

    monkeypatch.undo()

    retry_upload = make_upload(
        BytesIO(PAYLOAD),
    )

    storage_key = (
        storage_service.save_profile_image(
            retry_upload
        )
    )

    target = (
        storage_root
        / Path(storage_key)
    ).resolve()

    assert target.is_file()
    assert target.read_bytes() == PAYLOAD

    files = list_storage_files(
        storage_root
    )

    assert files == [
        target,
    ]


def test_profile_image_storage_open_permission_failure_leaves_no_file(
    app,
    tmp_path,
    monkeypatch,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    real_open = Path.open

    def denied_open(
        path,
        mode="r",
        *args,
        **kwargs,
    ):
        if mode == "xb":
            raise PermissionError(
                "simulated storage permission failure"
            )

        return real_open(
            path,
            mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "open",
        denied_open,
    )

    upload = make_upload(
        BytesIO(PAYLOAD),
    )

    with pytest.raises(
        PermissionError,
        match="simulated storage permission failure",
    ):
        storage_service.save_profile_image(
            upload
        )

    assert list_storage_files(
        storage_root
    ) == []


def test_profile_image_storage_path_unavailable_leaves_no_file(
    app,
    tmp_path,
):
    storage_root = tmp_path / "storage"
    storage_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    app.config["STORAGE_ROOT"] = str(storage_root)

    profile_images_path = (
        storage_root
        / "profile_images"
    )

    profile_images_path.write_bytes(
        b"not-a-directory"
    )

    upload = make_upload(
        BytesIO(PAYLOAD),
    )

    with pytest.raises(
        FileExistsError,
    ):
        storage_service.save_profile_image(
            upload
        )

    files = [
        path
        for path in storage_root.rglob("*")
        if path.is_file()
    ]

    assert files == [
        profile_images_path,
    ]
    assert profile_images_path.read_bytes() == (
        b"not-a-directory"
    )