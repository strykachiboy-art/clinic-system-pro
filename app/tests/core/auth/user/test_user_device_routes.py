from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.auth.user.models.user_device_model import UserDevice
from app.core.auth.user.routes import user_device_routes
from app.core.enums.role_enums import Role


def make_device(
    db,
    user_id: int,
    *,
    token: str = "test-device-token-001",
    platform: str = "android",
    device_name: str = "Test Phone",
    is_active: bool = True,
):
    device = UserDevice(
        user_id=user_id,
        device_token=token,
        platform=platform,
        device_name=device_name,
        is_active=is_active,
        last_seen_at=datetime.now(
            timezone.utc
        ),
    )

    db.session.add(device)
    db.session.flush()

    return device


# ============================================================================
# AUTHENTICATION
# ============================================================================


def test_device_endpoints_require_auth(client):
    response = client.get(
        "/api/users/devices/"
    )

    assert response.status_code in (
        401,
        422,
    )


def test_get_current_user_resolves_authenticated_user(
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        user_device_routes,
        "get_jwt_identity",
        lambda: str(user.id),
    )

    assert (
        user_device_routes._get_current_user()
        is user
    )


def test_get_current_user_rejects_invalid_identity(
    monkeypatch,
):
    monkeypatch.setattr(
        user_device_routes,
        "get_jwt_identity",
        lambda: "not-an-integer",
    )

    with pytest.raises(
        Exception,
        match="Invalid authentication identity",
    ):
        user_device_routes._get_current_user()


# ============================================================================
# ROLE AUTHORIZATION
# ============================================================================


def test_device_route_allows_patient(
    client,
    user,
    auth_headers_for,
):
    patient = user
    patient.role = Role.PATIENT

    headers = auth_headers_for(
        patient,
        role=Role.PATIENT,
    )

    response = client.get(
        "/api/users/devices/",
        headers=headers,
    )

    assert response.status_code == 200


def test_device_route_allows_admin(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/users/devices/",
        headers=headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PATIENT,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.RECEPTIONIST,
        Role.ADMIN,
        Role.ACCOUNTANT,
        Role.PARAMEDIC,
        Role.EMT,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.OTHER,
    ],
)
def test_device_route_allows_supported_roles(
    client,
    make_user,
    clinic,
    auth_headers_for,
    role,
):
    test_user = make_user(
        clinic=clinic,
        role=role,
    )

    headers = auth_headers_for(
        test_user,
        role=role,
    )

    response = client.get(
        "/api/users/devices/",
        headers=headers,
    )

    assert response.status_code == 200


# ============================================================================
# REGISTER
# ============================================================================


def test_register_device_success(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json={
            "device_token": "android-token-001",
            "device_name": "My Android",
            "platform": "ANDROID",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert data["user_id"] == user.id
    assert data["device_token"] == "android-token-001"
    assert data["device_name"] == "My Android"
    assert data["platform"] == "android"
    assert data["is_active"] is True


def test_register_device_rejects_unknown_fields(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json={
            "device_token": "android-token-002",
            "platform": "android",
            "user_id": 999999,
        },
    )

    assert response.status_code == 422


def test_register_device_rejects_invalid_platform(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json={
            "device_token": "android-token-003",
            "platform": "windows-phone",
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Validation error"
    assert body["details"]


def test_register_device_requires_device_token(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json={
            "platform": "android",
        },
    )

    assert response.status_code == 422


def test_register_device_rejects_short_token(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json={
            "device_token": "short",
            "platform": "android",
        },
    )

    assert response.status_code == 422


# ============================================================================
# LIST
# ============================================================================


def test_list_devices_only_returns_authenticated_users_devices(
    client,
    db,
    user,
    make_user,
    auth_headers_for,
):
    other_user = make_user(
        clinic=None,
    )

    own_device = make_device(
        db,
        user.id,
        token="own-device-token",
    )

    make_device(
        db,
        other_user.id,
        token="other-device-token",
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True

    items = body["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == own_device.id
    assert items[0]["user_id"] == user.id


def test_list_devices_supports_pagination(
    client,
    db,
    user,
    auth_headers_for,
):
    for index in range(3):
        make_device(
            db,
            user.id,
            token=f"pagination-token-{index}",
        )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/?page=1&per_page=2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 2
    assert body["data"]["total"] == 3
    assert body["data"]["pages"] == 2
    assert body["data"]["has_next"] is True
    assert body["data"]["has_prev"] is False


def test_list_devices_returns_empty_last_page(
    client,
    db,
    user,
    auth_headers_for,
):
    make_device(
        db,
        user.id,
        token="single-device-token",
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/?page=2&per_page=20",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["items"] == []
    assert data["page"] == 2
    assert data["total"] == 1
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is True


def test_list_devices_filters_active_only(
    client,
    db,
    user,
    auth_headers_for,
):
    make_device(
        db,
        user.id,
        token="active-token-001",
        is_active=True,
    )

    make_device(
        db,
        user.id,
        token="inactive-token-001",
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/?active_only=true",
        headers=headers,
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["device_token"] == (
        "active-token-001"
    )


def test_list_devices_filters_platform(
    client,
    db,
    user,
    auth_headers_for,
):
    make_device(
        db,
        user.id,
        token="android-token-filter",
        platform="android",
    )

    make_device(
        db,
        user.id,
        token="ios-token-filter",
        platform="ios",
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/?platform=IOS",
        headers=headers,
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["platform"] == "ios"


# ============================================================================
# GET
# ============================================================================


def test_get_device_success(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="get-device-token",
    )

    headers = auth_headers_for(user)

    response = client.get(
        f"/api/users/devices/{device.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == device.id
    assert body["data"]["user_id"] == user.id


def test_get_device_prevents_idor(
    client,
    db,
    user,
    make_user,
    auth_headers_for,
):
    other_user = make_user(
        clinic=None,
    )

    device = make_device(
        db,
        other_user.id,
        token="other-owner-device",
    )

    headers = auth_headers_for(user)

    response = client.get(
        f"/api/users/devices/{device.id}",
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# UPDATE
# ============================================================================


def test_update_device_metadata(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="update-device-token",
        platform="android",
        device_name="Old Phone",
    )

    headers = auth_headers_for(user)

    response = client.patch(
        f"/api/users/devices/{device.id}",
        headers=headers,
        json={
            "device_name": "New Phone",
            "platform": "IOS",
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["device_name"] == "New Phone"
    assert data["platform"] == "ios"


def test_update_device_cannot_change_token(
    client,
    db,
    user,
    auth_headers_for,
):
    make_device(
        db,
        user.id,
        token="immutable-token",
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/users/devices/1",
        headers=headers,
        json={
            "device_token": "new-token",
        },
    )

    assert response.status_code == 422


def test_patch_can_deactivate_device(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="patch-deactivate-token",
        is_active=True,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        f"/api/users/devices/{device.id}",
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200

    assert (
        response.get_json()["data"]["is_active"]
        is False
    )


def test_patch_can_activate_device(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="patch-activate-token",
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        f"/api/users/devices/{device.id}",
        headers=headers,
        json={
            "is_active": True,
        },
    )

    assert response.status_code == 200

    assert (
        response.get_json()["data"]["is_active"]
        is True
    )


# ============================================================================
# LIFECYCLE
# ============================================================================


def test_activate_device(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="activate-device-token",
        is_active=False,
    )

    headers = auth_headers_for(user)

    response = client.post(
        f"/api/users/devices/{device.id}/activate",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        response.get_json()["data"]["is_active"]
        is True
    )


def test_deactivate_device(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="deactivate-device-token",
        is_active=True,
    )

    headers = auth_headers_for(user)

    response = client.post(
        f"/api/users/devices/{device.id}/deactivate",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        response.get_json()["data"]["is_active"]
        is False
    )


def test_touch_device_updates_last_seen(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="touch-device-token",
    )

    before = device.last_seen_at

    headers = auth_headers_for(user)

    response = client.post(
        f"/api/users/devices/{device.id}/touch",
        headers=headers,
    )

    assert response.status_code == 200

    db.session.refresh(device)

    after = device.last_seen_at

    assert before is not None
    assert after is not None

    before_naive = (
        before.replace(tzinfo=None)
        if before.tzinfo is not None
        else before
    )

    after_naive = (
        after.replace(tzinfo=None)
        if after.tzinfo is not None
        else after
    )

    assert after_naive >= before_naive


# ============================================================================
# DELETE
# ============================================================================


def test_delete_device(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="delete-device-token",
    )

    headers = auth_headers_for(user)

    response = client.delete(
        f"/api/users/devices/{device.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == (
        "Device deleted successfully"
    )

    assert db.session.get(
        UserDevice,
        device.id,
    ) is None


# ============================================================================
# QUERY VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "query",
    [
        "?page=0",
        "?page=-1",
        "?page=abc",
        "?per_page=0",
        "?per_page=-1",
        "?per_page=abc",
        "?active_only=invalid",
    ],
)
def test_invalid_device_list_query_is_rejected(
    client,
    user,
    auth_headers_for,
    query,
):
    headers = auth_headers_for(user)

    response = client.get(
        f"/api/users/devices/{query}",
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# DOMAIN / ERROR TRANSLATION
# ============================================================================


def test_get_device_invalid_id(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.get(
        "/api/users/devices/0",
        headers=headers,
    )

    assert response.status_code in (
        404,
        422,
    )


def test_update_device_rejects_unknown_field(
    client,
    db,
    user,
    auth_headers_for,
):
    device = make_device(
        db,
        user.id,
        token="unknown-field-token",
    )

    headers = auth_headers_for(user)

    response = client.patch(
        f"/api/users/devices/{device.id}",
        headers=headers,
        json={
            "something_not_allowed": "x",
        },
    )

    assert response.status_code == 422


def test_register_device_rejects_non_object_body(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.post(
        "/api/users/devices/",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422