from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.modules.profile.routes import profile_route
from app.modules.profile.schemas.profile_schema import ProfileResponseSchema


# ============================================================================
# TEST CONTEXT
# ============================================================================


@pytest.fixture(autouse=True)
def profile_app_context(app):
    yield


@pytest.fixture()
def profile_routes():
    """
    Return the Profile route module for direct helper/service patching.
    """
    return profile_route


# ============================================================================
# PROFILE RESPONSE HELPERS
# ============================================================================


def make_profile_response(
    *,
    user_id=1,
    email="profile@test.com",
    clinic_id=1,
    staff_id=10,
    first_name="Test",
    last_name="Staff",
):
    """
    Build a valid ProfileResponseSchema for route-level service mocks.
    """
    return ProfileResponseSchema(
        user={
            "id": user_id,
            "email": email,
            "is_active": True,
            "clinic_id": clinic_id,
        },
        staff={
            "id": staff_id,
            "clinic_id": clinic_id,
            "user_id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "specialty": "General Medicine",
            "phone": "08000000000",
            "email": email,
            "status": "active",
            "hired_at": None,
        },
        clinic={
            "id": clinic_id,
            "name": "Test Clinic",
            "clinic_type": "general",
            "status": "active",
            "parent_clinic_id": None,
            "is_headquarters": False,
            "address": None,
            "city": None,
            "country": None,
            "phone": None,
            "email": None,
            "timezone": None,
            "opening_time": None,
            "closing_time": None,
        },
    )


# ============================================================================
# AUTHENTICATION
# ============================================================================


def test_get_my_profile_requires_authentication(
    client,
    assert_unauthorized,
):
    response = client.get(
        "/api/profile/me",
    )

    assert_unauthorized(response)


def test_update_my_profile_requires_authentication(
    client,
    assert_unauthorized,
):
    response = client.patch(
        "/api/profile/me",
        json={
            "email": "new@example.com",
        },
    )

    assert_unauthorized(response)


def test_get_my_profile_rejects_invalid_role(
    client,
    user,
    auth_headers_for,
    assert_forbidden,
):
    headers = auth_headers_for(
        user,
        role="invalid-role",
    )

    response = client.get(
        "/api/profile/me",
        headers=headers,
    )

    assert_forbidden(response)


def test_update_my_profile_rejects_invalid_role(
    client,
    user,
    auth_headers_for,
    assert_forbidden,
):
    headers = auth_headers_for(
        user,
        role="invalid-role",
    )

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "email": "new@example.com",
        },
    )

    assert_forbidden(response)


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
        Role.OTHER,
        Role.DRIVER,
        Role.EMT,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
    ],
)
def test_get_my_profile_accepts_supported_roles(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
    role,
):
    profile = make_profile_response(
        user_id=user.id,
        email=user.email,
        clinic_id=user.clinic_id,
    )

    get_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "get_profile",
        get_profile_mock,
    )

    headers = auth_headers_for(
        user,
        role=role,
    )

    response = client.get(
        "/api/profile/me",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["user"]["id"] == user.id

    get_profile_mock.assert_called_once_with(
        user_id=user.id,
    )


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
        Role.OTHER,
        Role.DRIVER,
        Role.EMT,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
    ],
)
def test_update_my_profile_accepts_supported_roles(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
    role,
):
    profile = make_profile_response(
        user_id=user.id,
        email="updated@example.com",
        clinic_id=user.clinic_id,
    )

    update_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        update_profile_mock,
    )

    headers = auth_headers_for(
        user,
        role=role,
    )

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == "Profile updated successfully"
    assert body["data"]["user"]["email"] == "updated@example.com"

    update_profile_mock.assert_called_once_with(
        user_id=user.id,
        email="updated@example.com",
    )


# ============================================================================
# CURRENT USER IDENTITY
# ============================================================================


def test_current_user_id_resolves_authenticated_identity(
    profile_routes,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_routes,
        "get_jwt_identity",
        Mock(
            return_value=str(user.id),
        ),
    )

    assert profile_routes._current_user_id() == user.id


def test_current_user_id_accepts_integer_identity(
    profile_routes,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_routes,
        "get_jwt_identity",
        Mock(
            return_value=123,
        ),
    )

    assert profile_routes._current_user_id() == 123


@pytest.mark.parametrize(
    "identity",
    [
        None,
        "",
        "not-an-integer",
        "abc",
        0,
        -1,
        True,
        False,
    ],
)
def test_current_user_id_rejects_invalid_identity(
    profile_routes,
    monkeypatch,
    identity,
):
    monkeypatch.setattr(
        profile_routes,
        "get_jwt_identity",
        Mock(
            return_value=identity,
        ),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid authentication identity",
    ):
        profile_routes._current_user_id()


# ============================================================================
# PAYLOAD HANDLING
# ============================================================================


def test_payload_returns_valid_dictionary(
    app,
    profile_routes,
):
    payload = {
        "email": "updated@example.com",
    }

    with app.test_request_context(
        "/api/profile/me",
        method="PATCH",
        json=payload,
    ):
        assert profile_routes._payload() == payload


def test_payload_rejects_missing_json(
    app,
    profile_routes,
):
    with app.test_request_context(
        "/api/profile/me",
        method="PATCH",
    ):
        with pytest.raises(
            ValidationError,
            match="Request body must contain valid JSON",
        ):
            profile_routes._payload()


def test_payload_rejects_null_json(
    app,
    profile_routes,
):
    with app.test_request_context(
        "/api/profile/me",
        method="PATCH",
        json=None,
    ):
        with pytest.raises(
            ValidationError,
            match="Request body must contain valid JSON",
        ):
            profile_routes._payload()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        ["email", "test@example.com"],
        "invalid",
        123,
        1.5,
        True,
        False,
    ],
)
def test_payload_rejects_non_dictionary_json(
    app,
    profile_routes,
    payload,
):
    with app.test_request_context(
        "/api/profile/me",
        method="PATCH",
        json=payload,
    ):
        with pytest.raises(
            ValidationError,
            match="Request body must be a JSON object",
        ):
            profile_routes._payload()


# ============================================================================
# GET MY PROFILE
# ============================================================================


def test_get_my_profile_returns_profile(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    profile = make_profile_response(
        user_id=user.id,
        email=user.email,
        clinic_id=user.clinic_id,
    )

    get_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "get_profile",
        get_profile_mock,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/profile/me",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert "data" in body

    assert body["data"]["user"]["id"] == user.id
    assert body["data"]["user"]["email"] == user.email
    assert body["data"]["user"]["clinic_id"] == user.clinic_id

    assert body["data"]["staff"] is not None
    assert body["data"]["clinic"] is not None

    get_profile_mock.assert_called_once_with(
        user_id=user.id,
    )


def test_get_my_profile_uses_jwt_identity_not_query_parameter(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    profile = make_profile_response(
        user_id=user.id,
        email=user.email,
        clinic_id=user.clinic_id,
    )

    get_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "get_profile",
        get_profile_mock,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/profile/me?user_id=999999",
        headers=headers,
    )

    assert response.status_code == 200

    get_profile_mock.assert_called_once_with(
        user_id=user.id,
    )


def test_get_my_profile_does_not_accept_user_id_in_route(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.get(
        f"/api/profile/{user.id}",
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# UPDATE MY PROFILE — SUCCESS
# ============================================================================


def test_update_my_profile_updates_email(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    profile = make_profile_response(
        user_id=user.id,
        email="updated@example.com",
        clinic_id=user.clinic_id,
    )

    update_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        update_profile_mock,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == "Profile updated successfully"
    assert body["data"]["user"]["email"] == (
        "updated@example.com"
    )

    update_profile_mock.assert_called_once_with(
        user_id=user.id,
        email="updated@example.com",
    )


def test_update_my_profile_updates_staff_fields(
    client,
    staff,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    profile = make_profile_response(
        user_id=staff.user.id,
        email=staff.user.email,
        clinic_id=staff.clinic_id,
        staff_id=staff.id,
        first_name="Updated",
        last_name="Profile",
    )

    update_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        update_profile_mock,
    )

    headers = auth_headers_for(
        staff.user,
    )

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "first_name": "Updated",
            "last_name": "Profile",
            "phone": "08000000000",
            "specialty": "Cardiology",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["staff"]["first_name"] == "Updated"
    assert body["data"]["staff"]["last_name"] == "Profile"

    update_profile_mock.assert_called_once_with(
        user_id=staff.user.id,
        first_name="Updated",
        last_name="Profile",
        phone="08000000000",
        specialty="Cardiology",
    )


def test_update_my_profile_can_update_multiple_allowed_fields(
    client,
    staff,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    profile = make_profile_response(
        user_id=staff.user.id,
        email="updated@example.com",
        clinic_id=staff.clinic_id,
        staff_id=staff.id,
        first_name="Updated",
        last_name="User",
    )

    update_profile_mock = Mock(
        return_value=profile,
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        update_profile_mock,
    )

    headers = auth_headers_for(
        staff.user,
    )

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "email": "updated@example.com",
            "first_name": "Updated",
            "last_name": "User",
            "phone": "08000000000",
            "specialty": "Surgery",
        },
    )

    assert response.status_code == 200

    update_profile_mock.assert_called_once_with(
        user_id=staff.user.id,
        email="updated@example.com",
        first_name="Updated",
        last_name="User",
        phone="08000000000",
        specialty="Surgery",
    )


# ============================================================================
# UPDATE MY PROFILE — SCHEMA VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "payload",
    [
        {
            "unknown_field": "value",
        },
        {
            "role": "doctor",
        },
        {
            "user_id": 999999,
        },
        {
            "staff_id": 999999,
        },
        {
            "clinic_id": 999999,
        },
        {
            "status": "active",
        },
    ],
)
def test_update_my_profile_rejects_forbidden_or_unknown_fields(
    client,
    user,
    auth_headers_for,
    payload,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "details" in body


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "",
        },
        {
            "first_name": "",
        },
        {
            "last_name": "",
        },
        {
            "phone": "",
        },
        {
            "specialty": "",
        },
    ],
)
def test_update_my_profile_rejects_blank_text(
    client,
    user,
    auth_headers_for,
    payload,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "details" in body


def test_update_my_profile_rejects_non_object_body(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json=[
            "email",
            "updated@example.com",
        ],
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body
    assert body["error"] == (
        "Request body must be a JSON object"
    )


def test_update_my_profile_rejects_missing_json_body(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Request body must contain valid JSON"
    )


def test_update_my_profile_rejects_null_json_body(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json=None,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Request body must contain valid JSON"
    )


# ============================================================================
# UPDATE MY PROFILE — IDENTITY BOUNDARY
# ============================================================================


def test_update_my_profile_uses_authenticated_identity(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    update_profile_mock = Mock(
        return_value=make_profile_response(
            user_id=user.id,
            email="updated@example.com",
            clinic_id=user.clinic_id,
        ),
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        update_profile_mock,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me?user_id=999999",
        headers=headers,
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code == 200

    update_profile_mock.assert_called_once_with(
        user_id=user.id,
        email="updated@example.com",
    )


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "staff_id",
        "clinic_id",
    ],
)
def test_update_my_profile_cannot_change_identity_fields(
    client,
    user,
    auth_headers_for,
    field,
):
    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            field: 999999,
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# SERVICE ERROR PROPAGATION
# ============================================================================


def test_get_my_profile_propagates_service_error(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    service_mock = Mock(
        side_effect=ValidationError(
            "Authenticated user is inactive",
        ),
    )

    monkeypatch.setattr(
        profile_routes,
        "get_profile",
        service_mock,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/profile/me",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Authenticated user is inactive"
    )


def test_update_my_profile_propagates_service_error(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    service_mock = Mock(
        side_effect=ValidationError(
            "This user is not linked to a staff record",
        ),
    )

    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        service_mock,
    )

    headers = auth_headers_for(user)

    response = client.patch(
        "/api/profile/me",
        headers=headers,
        json={
            "first_name": "Updated",
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "This user is not linked to a staff record"
    )


# ============================================================================
# ROUTE CONTRACT
# ============================================================================


def test_profile_get_route_exists(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_routes,
        "get_profile",
        Mock(
            return_value=make_profile_response(
                user_id=user.id,
                email=user.email,
                clinic_id=user.clinic_id,
            ),
        ),
    )

    response = client.get(
        "/api/profile/me",
        headers=auth_headers_for(user),
    )

    assert response.status_code != 404


def test_profile_patch_route_exists(
    client,
    user,
    auth_headers_for,
    profile_routes,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_routes,
        "update_profile",
        Mock(
            return_value=make_profile_response(
                user_id=user.id,
                email="updated@example.com",
                clinic_id=user.clinic_id,
            ),
        ),
    )

    response = client.patch(
        "/api/profile/me",
        headers=auth_headers_for(user),
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code != 404