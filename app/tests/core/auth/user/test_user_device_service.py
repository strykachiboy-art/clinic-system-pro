from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.auth.user.models.user_device_model import UserDevice
from app.core.auth.user.services import user_device_service as service
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


# ============================================================================
# HELPERS
# ============================================================================


def make_device(
    db,
    user_id: int,
    *,
    token: str = "test-device-token-001",
    platform: str = "android",
    device_name: str | None = "Test Phone",
    is_active: bool = True,
    last_seen_at: datetime | None = None,
):
    if last_seen_at is None:
        last_seen_at = datetime.now(timezone.utc)

    device = UserDevice(
        user_id=user_id,
        device_token=token,
        platform=platform,
        device_name=device_name,
        is_active=is_active,
        last_seen_at=last_seen_at,
    )

    db.session.add(device)
    db.session.flush()

    return device


# ============================================================================
# CONSTANTS
# ============================================================================


def test_pagination_defaults():
    assert service.DEFAULT_PAGE == 1
    assert service.DEFAULT_PER_PAGE == 20
    assert service.MAX_PER_PAGE == 100


def test_allowed_device_platforms():
    assert service.ALLOWED_DEVICE_PLATFORMS == {
        "android",
        "ios",
        "web",
    }


# ============================================================================
# POSITIVE ID VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        True,
        False,
        "1",
        None,
        1.5,
    ],
)
def test_validate_positive_id_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError,
        match="must be a positive integer",
    ):
        service._validate_positive_id(
            value,
            "User ID",
        )


@pytest.mark.parametrize(
    "value",
    [
        1,
        10,
        999,
    ],
)
def test_validate_positive_id_accepts_positive_integers(
    value,
):
    assert (
        service._validate_positive_id(
            value,
            "User ID",
        )
        is None
    )


# ============================================================================
# PAGINATION VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 20),
        (-1, 20),
        (True, 20),
        ("1", 20),
        (1, 0),
        (1, -1),
        (1, False),
        (1, "20"),
    ],
)
def test_validate_pagination_rejects_invalid_values(
    page,
    per_page,
):
    with pytest.raises(
        ValidationError,
    ):
        service._validate_pagination(
            page,
            per_page,
        )


def test_validate_pagination_rejects_excessive_per_page():
    with pytest.raises(
        ValidationError,
        match="cannot exceed 100",
    ):
        service._validate_pagination(
            1,
            101,
        )


def test_validate_pagination_accepts_valid_values():
    assert service._validate_pagination(
        1,
        20,
    ) == (
        1,
        20,
    )


# ============================================================================
# PLATFORM NORMALIZATION
# ============================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        ("android", "android"),
        (" ANDROID ", "android"),
        ("IOS", "ios"),
        (" Web ", "web"),
    ],
)
def test_normalize_platform(
    value,
    expected,
):
    assert (
        service._normalize_platform(value)
        == expected
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        "",
        "windows",
        "windows-phone",
    ],
)
def test_normalize_platform_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError,
    ):
        service._normalize_platform(
            value
        )


# ============================================================================
# DEVICE NAME NORMALIZATION
# ============================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        (" Phone ", "Phone"),
        ("My Android", "My Android"),
    ],
)
def test_normalize_device_name(
    value,
    expected,
):
    assert (
        service._normalize_device_name(value)
        == expected
    )


def test_normalize_device_name_rejects_non_string():
    with pytest.raises(
        ValidationError,
        match="Device name must be a string",
    ):
        service._normalize_device_name(
            123
        )


# ============================================================================
# DEVICE TOKEN NORMALIZATION
# ============================================================================


def test_normalize_device_token_trims_whitespace():
    assert (
        service._normalize_device_token(
            "   test-token   "
        )
        == "test-token"
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        "",
        "   ",
    ],
)
def test_normalize_device_token_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValidationError
    ):
        service._normalize_device_token(
            value
        )


def test_normalize_device_token_rejects_long_token():
    with pytest.raises(
        ValidationError,
        match="cannot exceed 500 characters",
    ):
        service._normalize_device_token(
            "x" * 501
        )


def test_normalize_device_token_accepts_500_characters():
    token = "x" * 500

    assert (
        service._normalize_device_token(
            token
        )
        == token
    )


# ============================================================================
# USER LOOKUP
# ============================================================================


def test_get_user_returns_existing_user(
    user,
):
    result = service._get_user(
        user.id
    )

    assert result is user


def test_get_user_raises_for_missing_user(
    app,
):
    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="User 999999 not found",
        ):
            service._get_user(
                999999
            )


def test_get_user_rejects_invalid_user_id():
    with pytest.raises(
        ValidationError
    ):
        service._get_user(
            0
        )


# ============================================================================
# USER VALIDATION
# ============================================================================


def test_validate_user_for_device_accepts_active_user(
    user,
):
    result = service._validate_user_for_device(
        user.id
    )

    assert result is user


def test_validate_user_for_device_rejects_inactive_user(
    make_user,
    clinic,
):
    inactive_user = make_user(
        clinic=clinic,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="is inactive",
    ):
        service._validate_user_for_device(
            inactive_user.id
        )


# ============================================================================
# DEVICE LOOKUP
# ============================================================================


def test_get_device_returns_device(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="lookup-device-token",
    )

    result = service._get_device(
        device.id
    )

    assert result is device


def test_get_device_raises_for_missing_device(
    app,
):
    with app.app_context():
        with pytest.raises(
            NotFoundError,
            match="User device 999999 not found",
        ):
            service._get_device(
                999999
            )


def test_get_device_enforces_user_ownership(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="ownership-device-token",
    )

    with pytest.raises(
        NotFoundError
    ):
        service._get_device(
            device.id,
            user_id=user.id,
        )


def test_get_device_allows_correct_owner(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="owner-device-token",
    )

    result = service._get_device(
        device.id,
        user_id=user.id,
    )

    assert result is device


# ============================================================================
# TOKEN LOOKUP
# ============================================================================


def test_get_device_by_token_returns_existing_device(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="token-lookup-test",
    )

    result = service._get_device_by_token(
        "  token-lookup-test  "
    )

    assert result is device


def test_get_device_by_token_returns_none_when_missing(
    app,
):
    with app.app_context():
        result = service._get_device_by_token(
            "does-not-exist"
        )

        assert result is None


# ============================================================================
# REGISTER DEVICE
# ============================================================================


def test_register_device_creates_new_device(
    db,
    user,
    monkeypatch,
):
    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    device = service.register_device(
        user.id,
        device_token="new-device-token",
        platform="ANDROID",
        device_name="  Pixel  ",
    )

    assert device.id is not None
    assert device.user_id == user.id
    assert device.device_token == (
        "new-device-token"
    )
    assert device.platform == "android"
    assert device.device_name == "Pixel"
    assert device.is_active is True
    assert device.last_seen_at is not None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.CREATE
    )
    assert kwargs["entity_type"] == (
        "UserDevice"
    )
    assert kwargs["entity_id"] == device.id
    assert kwargs["new_value"] == {
        "user_id": user.id,
        "platform": "android",
        "device_name": "Pixel",
        "is_active": True,
    }


def test_register_device_normalizes_platform_and_name(
    db,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    device = service.register_device(
        user.id,
        device_token="normalization-token",
        platform="  IOS ",
        device_name="  iPhone  ",
    )

    assert device.platform == "ios"
    assert device.device_name == "iPhone"


def test_register_device_rejects_missing_user(
    app,
):
    with app.app_context():
        with pytest.raises(
            NotFoundError
        ):
            service.register_device(
                999999,
                device_token="missing-user-token",
                platform="android",
            )


def test_register_device_rejects_inactive_user(
    make_user,
    clinic,
):
    inactive_user = make_user(
        clinic=clinic,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="is inactive",
    ):
        service.register_device(
            inactive_user.id,
            device_token="inactive-user-token",
            platform="android",
        )


def test_register_device_rejects_invalid_platform(
    user,
):
    with pytest.raises(
        ValidationError,
        match="Unsupported device platform",
    ):
        service.register_device(
            user.id,
            device_token="invalid-platform-token",
            platform="windows",
        )


def test_register_device_reactivates_existing_device(
    db,
    user,
    monkeypatch,
):
    audit = Mock()

    device = make_device(
        db,
        user.id,
        token="reactivate-token",
        platform="android",
        device_name="Old Phone",
        is_active=False,
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.register_device(
        user.id,
        device_token="reactivate-token",
        platform="ios",
        device_name="New Phone",
    )

    assert result is device
    assert result.user_id == user.id
    assert result.platform == "ios"
    assert result.device_name == "New Phone"
    assert result.is_active is True
    assert result.last_seen_at is not None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.UPDATE
    )


def test_register_device_same_user_same_data_updates_last_seen(
    db,
    user,
    monkeypatch,
):
    audit = Mock()

    old_seen = datetime.now(
        timezone.utc
    ) - timedelta(
        minutes=10
    )

    device = make_device(
        db,
        user.id,
        token="same-data-token",
        platform="android",
        device_name="Same Phone",
        is_active=True,
        last_seen_at=old_seen,
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.register_device(
        user.id,
        device_token="same-data-token",
        platform="android",
        device_name="Same Phone",
    )

    assert result is device
    assert result.last_seen_at is not None

    old_seen_naive = old_seen.replace(
        tzinfo=None
    )

    new_seen_naive = result.last_seen_at.replace(
        tzinfo=None
    )

    assert new_seen_naive >= old_seen_naive

    audit.assert_not_called()


def test_register_device_currently_reassigns_token_between_users(
    db,
    user,
    make_user,
    monkeypatch,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="reassignment-token",
        platform="android",
        device_name="Old Owner Device",
        is_active=True,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.register_device(
        user.id,
        device_token="reassignment-token",
        platform="ios",
        device_name="New Owner Device",
    )

    assert result is device
    assert result.user_id == user.id
    assert result.platform == "ios"
    assert result.device_name == (
        "New Owner Device"
    )
    assert result.is_active is True

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.UPDATE
    )


# ============================================================================
# INTEGRITY ERROR FALLBACK
# ============================================================================


def test_register_device_integrity_error_with_existing_same_user(
    db,
    user,
    monkeypatch,
):
    existing = make_device(
        db,
        user.id,
        token="race-condition-token",
        platform="android",
        device_name="Old Device",
        is_active=False,
    )

    flush = Mock(
        side_effect=IntegrityError(
            "INSERT",
            {},
            Exception("unique violation"),
        )
    )

    rollback = Mock()
    commit = Mock()

    monkeypatch.setattr(
        service.db.session,
        "flush",
        flush,
    )

    monkeypatch.setattr(
        service.db.session,
        "rollback",
        rollback,
    )

    monkeypatch.setattr(
        service.db.session,
        "commit",
        commit,
    )

    token_lookup = Mock(
        side_effect=[
            None,
            existing,
        ],
    )

    monkeypatch.setattr(
        service,
        "_get_device_by_token",
        token_lookup,
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    result = service.register_device(
        user.id,
        device_token="race-condition-token",
        platform="ios",
        device_name="Updated Device",
    )

    assert result is existing
    assert result.user_id == user.id
    assert result.platform == "ios"
    assert result.device_name == (
        "Updated Device"
    )
    assert result.is_active is True
    assert result.last_seen_at is not None

    flush.assert_called_once()
    rollback.assert_called_once()
    commit.assert_called_once()

    assert token_lookup.call_count == 2


def test_register_device_integrity_error_with_no_existing_device(
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        service.db.session,
        "flush",
        Mock(
            side_effect=IntegrityError(
                "INSERT",
                {},
                Exception("unique violation"),
            )
        ),
    )

    monkeypatch.setattr(
        service.db.session,
        "rollback",
        Mock(),
    )

    monkeypatch.setattr(
        service,
        "_get_device_by_token",
        Mock(return_value=None),
    )

    with pytest.raises(
        ConflictError,
        match="Unable to register device",
    ):
        service.register_device(
            user.id,
            device_token="failed-registration-token",
            platform="android",
        )


def test_register_device_integrity_error_existing_other_user(
    user,
    monkeypatch,
):
    existing = SimpleNamespace(
        id=10,
        user_id=user.id + 1,
        platform="android",
        device_name="Existing Device",
        is_active=True,
        last_seen_at=datetime.now(
            timezone.utc
        ),
    )

    monkeypatch.setattr(
        service.db.session,
        "flush",
        Mock(
            side_effect=IntegrityError(
                "INSERT",
                {},
                Exception("unique violation"),
            )
        ),
    )

    monkeypatch.setattr(
        service.db.session,
        "rollback",
        Mock(),
    )

    token_lookup = Mock(
        side_effect=[
            None,
            existing,
        ],
    )

    monkeypatch.setattr(
        service,
        "_get_device_by_token",
        token_lookup,
    )

    with pytest.raises(
        ConflictError,
        match="Device token is already registered",
    ):
        service.register_device(
            user.id,
            device_token="foreign-race-token",
            platform="android",
        )

    assert token_lookup.call_count == 2


# ============================================================================
# GET DEVICE
# ============================================================================


def test_get_device_returns_owned_device(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="get-owned-device",
    )

    result = service.get_device(
        device.id,
        user_id=user.id,
    )

    assert result is device


def test_get_device_rejects_wrong_owner(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="wrong-owner-device",
    )

    with pytest.raises(
        NotFoundError
    ):
        service.get_device(
            device.id,
            user_id=user.id,
        )


# ============================================================================
# LIST USER DEVICES
# ============================================================================


def test_list_user_devices_returns_only_owned_devices(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    own_device = make_device(
        db,
        user.id,
        token="list-own-device",
    )

    make_device(
        db,
        other_user.id,
        token="list-other-device",
    )

    result = service.list_user_devices(
        user.id
    )

    assert result["total"] == 1
    assert result["items"] == [
        own_device
    ]


def test_list_user_devices_returns_pagination_metadata(
    db,
    user,
):
    for index in range(5):
        make_device(
            db,
            user.id,
            token=f"pagination-device-{index}",
        )

    result = service.list_user_devices(
        user.id,
        page=1,
        per_page=2,
    )

    assert result["page"] == 1
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert result["pages"] == 3
    assert result["has_next"] is True
    assert result["has_prev"] is False
    assert len(result["items"]) == 2


def test_list_user_devices_returns_empty_page_after_last_page(
    db,
    user,
):
    make_device(
        db,
        user.id,
        token="single-pagination-device",
    )

    result = service.list_user_devices(
        user.id,
        page=2,
        per_page=20,
    )

    assert result["items"] == []
    assert result["page"] == 2
    assert result["total"] == 1
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_prev"] is True


def test_list_user_devices_filters_active_devices(
    db,
    user,
):
    active = make_device(
        db,
        user.id,
        token="active-list-device",
        is_active=True,
    )

    make_device(
        db,
        user.id,
        token="inactive-list-device",
        is_active=False,
    )

    result = service.list_user_devices(
        user.id,
        active_only=True,
    )

    assert result["total"] == 1
    assert result["items"] == [active]


def test_list_user_devices_filters_platform(
    db,
    user,
):
    make_device(
        db,
        user.id,
        token="android-filter-device",
        platform="android",
    )

    ios = make_device(
        db,
        user.id,
        token="ios-filter-device",
        platform="ios",
    )

    result = service.list_user_devices(
        user.id,
        platform="IOS",
    )

    assert result["total"] == 1
    assert result["items"] == [ios]


def test_list_user_devices_filters_ios_platform(
    db,
    user,
):
    ios = make_device(
        db,
        user.id,
        token="ios-exact-filter-device",
        platform="ios",
    )

    make_device(
        db,
        user.id,
        token="android-exact-filter-device",
        platform="android",
    )

    result = service.list_user_devices(
        user.id,
        platform="IOS",
    )

    assert result["total"] == 1
    assert result["items"] == [ios]


def test_list_user_devices_orders_by_last_seen_then_id(
    db,
    user,
):
    first_time = datetime.now(
        timezone.utc
    ) - timedelta(
        minutes=10
    )

    second_time = datetime.now(
        timezone.utc
    ) - timedelta(
        minutes=5
    )

    oldest = make_device(
        db,
        user.id,
        token="ordering-oldest",
        last_seen_at=first_time,
    )

    newest = make_device(
        db,
        user.id,
        token="ordering-newest",
        last_seen_at=second_time,
    )

    result = service.list_user_devices(
        user.id
    )

    assert result["items"][0] is newest
    assert result["items"][1] is oldest


def test_list_user_devices_rejects_invalid_user():
    with pytest.raises(
        ValidationError
    ):
        service.list_user_devices(
            0
        )


def test_list_user_devices_rejects_inactive_user(
    make_user,
    clinic,
):
    inactive_user = make_user(
        clinic=clinic,
        is_active=False,
    )

    with pytest.raises(
        ValidationError
    ):
        service.list_user_devices(
            inactive_user.id
        )


def test_list_user_devices_rejects_invalid_platform(
    user,
):
    with pytest.raises(
        ValidationError,
        match="Unsupported device platform",
    ):
        service.list_user_devices(
            user.id,
            platform="windows",
        )


# ============================================================================
# UPDATE
# ============================================================================


def test_update_device_updates_metadata(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="update-metadata-device",
        platform="android",
        device_name="Old Phone",
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.update_device(
        device.id,
        user.id,
        device_name="  New Phone  ",
        platform=" IOS ",
    )

    assert result is device
    assert result.device_name == (
        "New Phone"
    )
    assert result.platform == "ios"

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.UPDATE
    )
    assert kwargs["entity_type"] == (
        "UserDevice"
    )
    assert kwargs["entity_id"] == device.id
    assert kwargs["new_value"] == {
        "device_name": "New Phone",
        "platform": "ios",
    }


def test_update_device_noop_does_not_audit(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="noop-update-device",
        platform="android",
        device_name="Phone",
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.update_device(
        device.id,
        user.id,
        device_name="Phone",
        platform="android",
    )

    assert result is device

    audit.assert_not_called()


def test_update_device_rejects_wrong_owner(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="update-wrong-owner",
    )

    with pytest.raises(
        NotFoundError
    ):
        service.update_device(
            device.id,
            user.id,
            device_name="Hijacked",
        )


def test_update_device_rejects_invalid_platform(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="update-invalid-platform",
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported device platform",
    ):
        service.update_device(
            device.id,
            user.id,
            platform="windows",
        )


def test_update_device_does_not_modify_token(
    db,
    user,
):
    device = make_device(
        db,
        user.id,
        token="immutable-service-token",
    )

    result = service.update_device(
        device.id,
        user.id,
        device_name="Updated",
    )

    assert result.device_token == (
        "immutable-service-token"
    )


# ============================================================================
# TOUCH
# ============================================================================


def test_touch_device_updates_last_seen(
    db,
    user,
):
    old_seen = datetime.now(
        timezone.utc
    ) - timedelta(
        minutes=10
    )

    device = make_device(
        db,
        user.id,
        token="touch-service-device",
        last_seen_at=old_seen,
    )

    result = service.touch_device(
        device.id,
        user.id,
    )

    assert result is device

    assert result.last_seen_at is not None

    old_naive = old_seen.replace(
        tzinfo=None
    )

    new_naive = result.last_seen_at.replace(
        tzinfo=None
    )

    assert new_naive >= old_naive


def test_touch_device_rejects_wrong_owner(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="touch-wrong-owner",
    )

    with pytest.raises(
        NotFoundError
    ):
        service.touch_device(
            device.id,
            user.id,
        )


# ============================================================================
# ACTIVATE
# ============================================================================


def test_activate_device_changes_inactive_device(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="activate-service-device",
        is_active=False,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.activate_device(
        device.id,
        user.id,
    )

    assert result is device
    assert result.is_active is True
    assert result.last_seen_at is not None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.STATUS_CHANGE
    )
    assert kwargs["entity_type"] == (
        "UserDevice"
    )


def test_activate_device_is_idempotent(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="activate-idempotent-device",
        is_active=True,
    )

    old_seen = device.last_seen_at

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.activate_device(
        device.id,
        user.id,
    )

    assert result is device
    assert result.is_active is True

    old_seen_naive = old_seen.replace(
        tzinfo=None
    )

    result_seen_naive = (
        result.last_seen_at.replace(
            tzinfo=None
        )
    )

    assert result_seen_naive == old_seen_naive

    audit.assert_not_called()


# ============================================================================
# DEACTIVATE
# ============================================================================


def test_deactivate_device_changes_active_device(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="deactivate-service-device",
        is_active=True,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.deactivate_device(
        device.id,
        user.id,
    )

    assert result is device
    assert result.is_active is False

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.STATUS_CHANGE
    )


def test_deactivate_device_is_idempotent(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="deactivate-idempotent-device",
        is_active=False,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    result = service.deactivate_device(
        device.id,
        user.id,
    )

    assert result is device
    assert result.is_active is False

    audit.assert_not_called()


def test_deactivate_device_rejects_wrong_owner(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="deactivate-wrong-owner",
    )

    with pytest.raises(
        NotFoundError
    ):
        service.deactivate_device(
            device.id,
            user.id,
        )


# ============================================================================
# DELETE
# ============================================================================


def test_delete_device_removes_device(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="delete-service-device",
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    device_id = device.id

    result = service.delete_device(
        device_id,
        user.id,
    )

    assert result is None

    assert db.session.get(
        UserDevice,
        device_id,
    ) is None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == (
        AuditAction.DELETE
    )
    assert kwargs["entity_type"] == (
        "UserDevice"
    )
    assert kwargs["entity_id"] == device_id


def test_delete_device_rejects_wrong_owner(
    db,
    user,
    make_user,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="delete-wrong-owner",
    )

    with pytest.raises(
        NotFoundError
    ):
        service.delete_device(
            device.id,
            user.id,
        )


def test_delete_device_missing_device(
    app,
):
    with app.app_context():
        with pytest.raises(
            NotFoundError
        ):
            service.delete_device(
                999999,
                1,
            )


# ============================================================================
# TRANSACTION / PERSISTENCE VERIFICATION
# ============================================================================


def test_register_device_persists_to_database(
    db,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    device = service.register_device(
        user.id,
        device_token="persisted-device-token",
        platform="android",
        device_name="Persisted Device",
    )

    db.session.expire_all()

    persisted = db.session.get(
        UserDevice,
        device.id,
    )

    assert persisted is not None
    assert persisted.user_id == user.id
    assert persisted.device_token == (
        "persisted-device-token"
    )
    assert persisted.platform == "android"
    assert persisted.device_name == (
        "Persisted Device"
    )
    assert persisted.is_active is True


def test_update_device_persists_changes(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="persist-update-device",
        device_name="Old Name",
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    service.update_device(
        device.id,
        user.id,
        device_name="New Name",
    )

    db.session.expire_all()

    persisted = db.session.get(
        UserDevice,
        device.id,
    )

    assert persisted is not None
    assert persisted.device_name == (
        "New Name"
    )


def test_delete_device_persists_removal(
    db,
    user,
    monkeypatch,
):
    device = make_device(
        db,
        user.id,
        token="persist-delete-device",
    )

    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    device_id = device.id

    service.delete_device(
        device_id,
        user.id,
    )

    db.session.expire_all()

    assert db.session.get(
        UserDevice,
        device_id,
    ) is None