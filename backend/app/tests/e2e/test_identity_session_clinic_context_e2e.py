from __future__ import annotations

from flask_jwt_extended import decode_token

from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role


def test_identity_session_clinic_context_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    e2e_login,
):
    # ================================================================
    # CLINICS + USERS
    # ================================================================

    second_clinic = make_clinic(
        name="Gate 12 Context Clinic",
    )

    super_admin = make_user(
        role=Role.SUPER_ADMIN,
        email="e2e-g12-super-admin@test.com",
    )

    regular_user = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
        email="e2e-g12-receptionist@test.com",
    )

    assert super_admin.id > 0
    assert regular_user.id > 0
    assert clinic.id != second_clinic.id

    # ================================================================
    # NORMAL USER LOGIN + ASSIGNED CLINIC CONTEXT
    # ================================================================

    regular_login = e2e_login(
        "e2e-g12-receptionist@test.com",
    )

    assert regular_login["user_id"] == regular_user.id
    assert regular_login["role"] == Role.RECEPTIONIST.value
    assert regular_login["clinic_context_id"] is None

    regular_headers = {
        "Authorization": (
            f"Bearer {regular_login['access_token']}"
        ),
    }

    regular_context_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=regular_headers,
    )

    assert regular_context_response.status_code == 200

    regular_context_body = (
        regular_context_response.get_json()
    )

    assert regular_context_body["success"] is True
    assert regular_context_body["data"] == {
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "source": "assigned",
    }

    # ================================================================
    # NORMAL USER CANNOT SWITCH TO ANOTHER CLINIC
    # ================================================================

    unauthorized_context_response = client.post(
        "/api/v1/auth/clinic-context",
        headers=regular_headers,
        json={
            "clinic_id": second_clinic.id,
        },
    )

    assert unauthorized_context_response.status_code == 403

    unauthorized_context_body = (
        unauthorized_context_response.get_json()
    )

    assert unauthorized_context_body["success"] is False
    assert unauthorized_context_body["error"] == (
        "Only a super administrator can select a clinic context"
    )

    # The failed attempt must not alter the user's assigned context.
    regular_context_after_denial = client.get(
        "/api/v1/auth/clinic-context",
        headers=regular_headers,
    )

    assert regular_context_after_denial.status_code == 200
    assert (
        regular_context_after_denial.get_json()["data"]["clinic_id"]
        == clinic.id
    )

    # ================================================================
    # SUPER ADMIN LOGIN + SYSTEM CONTEXT
    # ================================================================

    super_login = e2e_login(
        "e2e-g12-super-admin@test.com",
    )

    assert super_login["user_id"] == super_admin.id
    assert super_login["role"] == Role.SUPER_ADMIN.value
    assert super_login["clinic_context_id"] is None
    assert super_login["access_token"]
    assert super_login["refresh_token"]

    super_access_headers = {
        "Authorization": (
            f"Bearer {super_login['access_token']}"
        ),
    }

    super_refresh_headers = {
        "Authorization": (
            f"Bearer {super_login['refresh_token']}"
        ),
    }

    # ================================================================
    # AUTHENTICATED PROTECTED REQUEST
    # ================================================================

    system_context_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=super_access_headers,
    )

    assert system_context_response.status_code == 200

    system_context_body = system_context_response.get_json()

    assert system_context_body["success"] is True
    assert system_context_body["data"] == {
        "clinic_id": None,
        "clinic_name": None,
        "source": "system",
    }

    # ================================================================
    # PRIVILEGED CONTEXT SELECTION
    # ================================================================

    select_response = client.post(
        "/api/v1/auth/clinic-context",
        headers=super_access_headers,
        json={
            "clinic_id": second_clinic.id,
        },
    )

    assert select_response.status_code == 200, (
        select_response.get_json()
    )

    select_body = select_response.get_json()

    assert select_body["success"] is True
    assert select_body["data"]["user_id"] == super_admin.id
    assert select_body["data"]["role"] == Role.SUPER_ADMIN.value
    assert (
        select_body["data"]["clinic_context_id"]
        == second_clinic.id
    )

    selected_access_token = (
        select_body["data"]["access_token"]
    )
    selected_refresh_token = (
        select_body["data"]["refresh_token"]
    )

    selected_access_payload = decode_token(
        selected_access_token,
    )
    selected_refresh_payload = decode_token(
        selected_refresh_token,
    )

    assert (
        selected_access_payload["clinic_context_id"]
        == second_clinic.id
    )
    assert (
        selected_refresh_payload["clinic_context_id"]
        == second_clinic.id
    )

    selected_access_headers = {
        "Authorization": (
            f"Bearer {selected_access_token}"
        ),
    }

    selected_refresh_headers = {
        "Authorization": (
            f"Bearer {selected_refresh_token}"
        ),
    }

    # ================================================================
    # SELECTED CONTEXT RESOLUTION
    # ================================================================

    selected_context_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=selected_access_headers,
    )

    assert selected_context_response.status_code == 200

    selected_context_body = (
        selected_context_response.get_json()
    )

    assert selected_context_body["success"] is True
    assert selected_context_body["data"] == {
        "clinic_id": second_clinic.id,
        "clinic_name": second_clinic.name,
        "source": "selected",
    }

    # ================================================================
    # REFRESH SESSION WITH CONTEXT PRESERVED
    # ================================================================

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers=selected_refresh_headers,
    )

    assert refresh_response.status_code == 200, (
        refresh_response.get_json()
    )

    refresh_body = refresh_response.get_json()

    assert refresh_body["success"] is True
    assert refresh_body["data"]["user_id"] == super_admin.id
    assert refresh_body["data"]["role"] == Role.SUPER_ADMIN.value
    assert (
        refresh_body["data"]["clinic_context_id"]
        == second_clinic.id
    )
    assert refresh_body["data"]["access_token"]
    assert refresh_body["data"]["refresh_token"]

    refreshed_access_token = (
        refresh_body["data"]["access_token"]
    )
    refreshed_refresh_token = (
        refresh_body["data"]["refresh_token"]
    )

    refreshed_access_payload = decode_token(
        refreshed_access_token,
    )
    refreshed_refresh_payload = decode_token(
        refreshed_refresh_token,
    )

    assert (
        refreshed_access_payload["clinic_context_id"]
        == second_clinic.id
    )
    assert (
        refreshed_refresh_payload["clinic_context_id"]
        == second_clinic.id
    )

    refreshed_access_headers = {
        "Authorization": (
            f"Bearer {refreshed_access_token}"
        ),
    }

    refreshed_refresh_headers = {
        "Authorization": (
            f"Bearer {refreshed_refresh_token}"
        ),
    }

    # ================================================================
    # OLD REFRESH TOKEN MUST NOT BE REUSABLE
    # ================================================================

    old_refresh_reuse_response = client.post(
        "/api/v1/auth/refresh",
        headers=selected_refresh_headers,
    )

    assert old_refresh_reuse_response.status_code == 401

    old_refresh_reuse_body = (
        old_refresh_reuse_response.get_json()
    )

    assert old_refresh_reuse_body["msg"] == (
        "Token has been revoked"
    )

    # ================================================================
    # STALE SELECTED CONTEXT
    # ================================================================

    second_clinic.status = ClinicStatus.INACTIVE
    db.session.commit()

    stale_context_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=refreshed_access_headers,
    )

    assert stale_context_response.status_code == 422

    stale_context_body = stale_context_response.get_json()

    assert stale_context_body["success"] is False
    assert stale_context_body["error"] == (
        "Selected clinic is not active"
    )

    # ================================================================
    # CLEAR STALE CONTEXT
    # ================================================================

    clear_response = client.delete(
        "/api/v1/auth/clinic-context",
        headers=refreshed_access_headers,
    )

    assert clear_response.status_code == 200, (
        clear_response.get_json()
    )

    clear_body = clear_response.get_json()

    assert clear_body["success"] is True
    assert clear_body["data"]["user_id"] == super_admin.id
    assert clear_body["data"]["role"] == Role.SUPER_ADMIN.value
    assert clear_body["data"]["clinic_context_id"] is None

    cleared_access_token = (
        clear_body["data"]["access_token"]
    )
    cleared_refresh_token = (
        clear_body["data"]["refresh_token"]
    )

    cleared_access_payload = decode_token(
        cleared_access_token,
    )
    cleared_refresh_payload = decode_token(
        cleared_refresh_token,
    )

    assert "clinic_context_id" not in cleared_access_payload
    assert "clinic_context_id" not in cleared_refresh_payload

    cleared_access_headers = {
        "Authorization": (
            f"Bearer {cleared_access_token}"
        ),
    }

    cleared_refresh_headers = {
        "Authorization": (
            f"Bearer {cleared_refresh_token}"
        ),
    }

    # ================================================================
    # CONTEXT MUST RETURN TO SYSTEM
    # ================================================================

    cleared_context_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=cleared_access_headers,
    )

    assert cleared_context_response.status_code == 200

    cleared_context_body = (
        cleared_context_response.get_json()
    )

    assert cleared_context_body["success"] is True
    assert cleared_context_body["data"] == {
        "clinic_id": None,
        "clinic_name": None,
        "source": "system",
    }

    # ================================================================
    # LOGOUT
    # ================================================================

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers=cleared_access_headers,
        json={
            "refresh_token": cleared_refresh_token,
        },
    )

    assert logout_response.status_code == 200

    logout_body = logout_response.get_json()

    assert logout_body["success"] is True
    assert logout_body["message"] == (
        "Successfully logged out"
    )

    # ================================================================
    # REVOKED ACCESS TOKEN MUST FAIL
    # ================================================================

    revoked_access_response = client.get(
        "/api/v1/auth/clinic-context",
        headers=cleared_access_headers,
    )

    assert revoked_access_response.status_code == 401

    revoked_access_body = (
        revoked_access_response.get_json()
    )

    assert revoked_access_body["msg"] == (
        "Token has been revoked"
    )

    # ================================================================
    # REVOKED REFRESH TOKEN MUST FAIL
    # ================================================================

    revoked_refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers=cleared_refresh_headers,
    )

    assert revoked_refresh_response.status_code == 401

    revoked_refresh_body = (
        revoked_refresh_response.get_json()
    )

    assert revoked_refresh_body["msg"] == (
        "Token has been revoked"
    )

    print(
        "PHASE8_E2E_GATE12_IDENTITY_SESSION_CONTEXT=PASS"
    )
