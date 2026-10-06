from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from flask import request
from werkzeug.datastructures import FileStorage, MultiDict

from app.core.storage import storage_service
from app.extensions import db
from app.modules.profile.routes import profile_route


PNG_PAYLOAD = (
    b"\x89PNG\r\n\x1a\n"
    b"profile-consistency-payload"
)


def _write_file(
    storage_root: Path,
    storage_key: str,
    payload: bytes,
) -> Path:
    target = (
        storage_root
        / storage_key
    ).resolve()

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_bytes(
        payload
    )

    return target


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


def _call_profile_upload(
    app,
    user_id: int,
    *,
    filename: str = "profile.png",
):
    upload = FileStorage(
        stream=BytesIO(PNG_PAYLOAD),
        filename=filename,
        content_type="image/png",
        content_length=len(PNG_PAYLOAD),
    )

    with app.test_request_context(
        "/profile/me/image",
        method="POST",
    ):
        request.files = MultiDict(
            {
                "image": upload,
            }
        )

        return profile_route.upload_my_profile_image.__wrapped__()


def test_profile_upload_db_failure_rolls_back_metadata_and_cleans_new_file(
    app,
    user,
    tmp_path,
    monkeypatch,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    old_key = "profile_images/current.png"
    old_file = _write_file(
        storage_root,
        old_key,
        b"old-profile-image",
    )

    user.profile_image_storage_key = old_key
    db.session.commit()

    monkeypatch.setattr(
        profile_route,
        "_current_user_id",
        lambda: user.id,
    )

    real_commit = db.session.commit
    fail_once = {
        "armed": True,
    }

    def fail_metadata_commit():
        if fail_once["armed"]:
            fail_once["armed"] = False

            raise RuntimeError(
                "simulated profile metadata database failure"
            )

        real_commit()

    monkeypatch.setattr(
        db.session,
        "commit",
        fail_metadata_commit,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated profile metadata database failure",
    ):
        _call_profile_upload(
            app,
            user.id,
            filename="failed-profile.png",
        )

    monkeypatch.setattr(
        db.session,
        "commit",
        real_commit,
    )

    db.session.expire_all()

    stored_user = db.session.get(
        type(user),
        user.id,
    )

    assert stored_user is not None
    assert stored_user.profile_image_storage_key == old_key

    assert old_file.exists()
    assert old_file.read_bytes() == (
        b"old-profile-image"
    )

    files_after_failure = _storage_files(
        storage_root
    )

    assert files_after_failure == [
        old_file,
    ]

    retry_response = _call_profile_upload(
        app,
        user.id,
        filename="retry-profile.png",
    )

    assert retry_response[1] == 200

    db.session.expire_all()

    final_user = db.session.get(
        type(user),
        user.id,
    )

    assert final_user is not None

    new_key = final_user.profile_image_storage_key

    assert new_key is not None
    assert new_key != old_key
    assert new_key.startswith(
        "profile_images/"
    )

    new_file = (
        storage_root
        / new_key
    ).resolve()

    assert new_file.exists()
    assert new_file.read_bytes() == (
        PNG_PAYLOAD
    )

    assert not old_file.exists()

    final_files = _storage_files(
        storage_root
    )

    assert final_files == [
        new_file,
    ]


def test_profile_upload_old_file_delete_failure_leaves_reconcilable_orphan(
    app,
    user,
    tmp_path,
    monkeypatch,
):
    storage_root = tmp_path / "storage"
    app.config["STORAGE_ROOT"] = str(storage_root)

    old_key = "profile_images/current.png"
    old_file = _write_file(
        storage_root,
        old_key,
        b"old-profile-image",
    )

    user.profile_image_storage_key = old_key
    db.session.commit()

    monkeypatch.setattr(
        profile_route,
        "_current_user_id",
        lambda: user.id,
    )

    real_delete_file = profile_route.delete_file

    def fail_old_file_delete(storage_key):
        if storage_key == old_key:
            raise OSError(
                "simulated old profile file deletion failure"
            )

        return real_delete_file(
            storage_key
        )

    monkeypatch.setattr(
        profile_route,
        "delete_file",
        fail_old_file_delete,
    )

    with pytest.raises(
        OSError,
        match="simulated old profile file deletion failure",
    ):
        _call_profile_upload(
            app,
            user.id,
            filename="replacement-profile.png",
        )

    db.session.expire_all()

    stored_user = db.session.get(
        type(user),
        user.id,
    )

    assert stored_user is not None

    new_key = stored_user.profile_image_storage_key

    assert new_key is not None
    assert new_key != old_key

    new_file = (
        storage_root
        / new_key
    ).resolve()

    assert new_file.exists()
    assert new_file.read_bytes() == (
        PNG_PAYLOAD
    )

    assert old_file.exists()
    assert old_file.read_bytes() == (
        b"old-profile-image"
    )

    files_after_cleanup_failure = _storage_files(
        storage_root
    )

    assert sorted(files_after_cleanup_failure) == sorted(
        [
            old_file,
            new_file,
        ]
    )

    monkeypatch.setattr(
        profile_route,
        "delete_file",
        real_delete_file,
    )

    storage_service.delete_file(
        old_key
    )

    assert not old_file.exists()
    assert new_file.exists()

    final_files = _storage_files(
        storage_root
    )

    assert final_files == [
        new_file,
    ]

    db.session.expire_all()

    final_user = db.session.get(
        type(user),
        user.id,
    )

    assert final_user is not None
    assert final_user.profile_image_storage_key == new_key