from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.core.exceptions import ValidationError
from app.core.storage import storage_service


def make_upload(
    payload: bytes,
    *,
    filename: str = "profile.png",
    mimetype: str = "image/png",
) -> FileStorage:
    return FileStorage(
        stream=BytesIO(payload),
        filename=filename,
        content_type=mimetype,
        content_length=len(payload),
    )


def test_resolve_storage_path_rejects_parent_traversal(
    app,
):
    with pytest.raises(
        ValidationError,
        match="Invalid storage key",
    ):
        storage_service._resolve_storage_path(
            "../outside.txt"
        )


def test_resolve_storage_path_rejects_absolute_path(
    app,
    tmp_path,
):
    absolute_path = str(
        tmp_path / "outside.txt"
    )

    with pytest.raises(
        ValidationError,
        match="Invalid storage key",
    ):
        storage_service._resolve_storage_path(
            absolute_path
        )


def test_resolve_storage_path_keeps_dot_segment_inside_storage_root(
    app,
    tmp_path,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    resolved = storage_service._resolve_storage_path(
        "profile_images/./image.png"
    )

    assert resolved == (
        storage_root
        / "profile_images"
        / "image.png"
    ).resolve()

    assert resolved.is_relative_to(
        storage_root.resolve()
    )


def test_resolve_storage_path_stays_inside_storage_root(
    app,
    tmp_path,
):
    storage_root = (
        tmp_path / "storage"
    )

    app.config["STORAGE_ROOT"] = str(
        storage_root
    )

    resolved = (
        storage_service._resolve_storage_path(
            "profile_images/image.png"
        )
    )

    assert resolved == (
        storage_root
        / "profile_images"
        / "image.png"
    ).resolve()

    assert (
        resolved.is_relative_to(
            storage_root.resolve()
        )
    )


def test_build_storage_key_rejects_path_injection(
    app,
):
    with pytest.raises(
        ValidationError,
        match="Invalid storage category",
    ):
        storage_service._build_storage_key(
            category="../outside",
            extension=".png",
        )


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.png",
        "..\\outside.png",
        "/absolute.png",
        "C:/absolute.png",
    ],
)
def test_save_profile_image_does_not_use_client_filename_as_storage_path(
    app,
    tmp_path,
    filename,
):
    storage_root = (
        tmp_path / "storage"
    )

    app.config["STORAGE_ROOT"] = str(
        storage_root
    )

    upload = make_upload(
        b"\x89PNG\r\n\x1a\npayload",
        filename=filename,
        mimetype="image/png",
    )

    storage_key = (
        storage_service.save_profile_image(
            upload
        )
    )

    target = (
        storage_root
        / Path(storage_key)
    ).resolve()

    assert target.is_file()

    assert (
        target.read_bytes()
        == b"\x89PNG\r\n\x1a\npayload"
    )

    assert (
        target.is_relative_to(
            storage_root.resolve()
        )
    )

    assert "outside" not in storage_key


def test_validate_upload_rejects_unsupported_mime_type(
    app,
):
    upload = make_upload(
        b"\x89PNG\r\n\x1a\npayload",
        filename="profile.exe",
        mimetype="application/octet-stream",
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported profile image type",
    ):
        storage_service._validate_upload(
            upload
        )


def test_validate_upload_rejects_mime_content_mismatch(
    app,
):
    upload = make_upload(
        b"\x89PNG\r\n\x1a\npayload",
        filename="profile.jpg",
        mimetype="image/jpeg",
    )

    with pytest.raises(
        ValidationError,
        match=(
            "Uploaded file MIME type does not "
            "match its actual content"
        ),
    ):
        storage_service._validate_upload(
            upload
        )


def test_validate_upload_rejects_non_image_content(
    app,
):
    upload = make_upload(
        b"not-an-image",
        filename="profile.png",
        mimetype="image/png",
    )

    with pytest.raises(
        ValidationError,
        match="Uploaded file is not a supported image",
    ):
        storage_service._validate_upload(
            upload
        )


def test_validate_upload_rejects_empty_file(
    app,
):
    upload = make_upload(
        b"",
        filename="profile.png",
        mimetype="image/png",
    )

    with pytest.raises(
        ValidationError,
        match="Profile image cannot be empty",
    ):
        storage_service._validate_upload(
            upload
        )


def test_validate_upload_enforces_configured_size_limit(
    app,
):
    app.config["MAX_PROFILE_IMAGE_SIZE_BYTES"] = 8

    upload = make_upload(
        b"\x89PNG\r\n\x1a\nX",
        filename="profile.png",
        mimetype="image/png",
    )

    with pytest.raises(
        ValidationError,
        match="Profile image exceeds the maximum allowed size",
    ):
        storage_service._validate_upload(
            upload
        )


def test_save_profile_image_writes_under_storage_root(
    app,
    tmp_path,
):
    storage_root = (
        tmp_path / "storage"
    )

    app.config["STORAGE_ROOT"] = str(
        storage_root
    )

    upload = make_upload(
        b"\x89PNG\r\n\x1a\nvalid-payload",
    )

    storage_key = (
        storage_service.save_profile_image(
            upload
        )
    )

    target = (
        storage_root
        / Path(storage_key)
    ).resolve()

    assert target.exists()
    assert target.is_file()

    assert (
        target.read_bytes()
        == b"\x89PNG\r\n\x1a\nvalid-payload"
    )


def test_delete_file_rejects_parent_traversal(
    app,
):
    with pytest.raises(
        ValidationError,
        match="Invalid storage key",
    ):
        storage_service.delete_file(
            "../outside.txt"
        )


def test_delete_file_removes_only_target_file(
    app,
    tmp_path,
):
    storage_root = (
        tmp_path / "storage"
    )

    app.config["STORAGE_ROOT"] = str(
        storage_root
    )

    target = (
        storage_root
        / "profile_images"
        / "image.png"
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_bytes(
        b"stored-image"
    )

    storage_service.delete_file(
        "profile_images/image.png"
    )

    assert not target.exists()