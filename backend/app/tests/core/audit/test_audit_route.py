import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


BASE_URL = "/api/v1/audit-logs"


def make_audit_log(
    db_session,
    *,
    clinic_id,
    user_id=None,
    action=AuditAction.UPDATE,
    entity_type="User",
    entity_id=100,
    description="Audit event",
    old_value=None,
    new_value=None,
    ip_address=None,
):
    log = AuditLog(
        clinic_id=clinic_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )

    db_session.add(log)
    db_session.flush()

    return log


def test_list_audit_logs_requires_authentication(
    client,
):
    response = client.get(BASE_URL)

    assert response.status_code == 401


def test_list_audit_logs_allows_admin(
    client,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user)

    response = client.get(
        BASE_URL,
        headers=headers,
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["success"] is True
    assert "items" in payload["data"]
    assert "total" in payload["data"]


def test_list_audit_logs_allows_super_admin(
    client,
    auth_headers_for,
    make_user,
):
    super_admin = make_user(
        None,
        role=Role.SUPER_ADMIN,
    )

    headers = auth_headers_for(
        super_admin,
    )

    response = client.get(
        BASE_URL,
        headers=headers,
    )

    assert response.status_code == 200


def test_list_audit_logs_rejects_non_admin(
    client,
    auth_headers_for,
    make_user,
    clinic,
):
    doctor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    headers = auth_headers_for(
        doctor,
    )

    response = client.get(
        BASE_URL,
        headers=headers,
    )

    assert response.status_code == 403


def test_list_audit_logs_is_tenant_scoped(
    client,
    auth_headers_for,
    user,
    clinic,
    make_clinic,
    make_user,
    db_session,
):
    other_clinic = make_clinic()

    other_user = make_user(
        other_clinic,
        role=Role.ADMIN,
    )

    local_log = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        entity_id=101,
    )

    make_audit_log(
        db_session,
        clinic_id=other_clinic.id,
        user_id=other_user.id,
        entity_id=202,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        headers=headers,
    )

    assert response.status_code == 200

    payload = response.get_json()

    ids = [
        item["id"]
        for item in payload["data"]["items"]
    ]

    assert local_log.id in ids
    assert len(ids) == 1


def test_list_audit_logs_filters_user(
    client,
    auth_headers_for,
    user,
    clinic,
    make_user,
    db_session,
):
    other_user = make_user(
        clinic,
        role=Role.ADMIN,
    )

    matching = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=other_user.id,
        entity_id=101,
    )

    make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        entity_id=202,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "user_id": other_user.id,
        },
        headers=headers,
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == matching.id


def test_list_audit_logs_filters_action(
    client,
    auth_headers_for,
    user,
    clinic,
    db_session,
):
    matching = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        action=AuditAction.LOGIN,
        entity_id=101,
    )

    make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        action=AuditAction.UPDATE,
        entity_id=202,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "action": "login",
        },
        headers=headers,
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == matching.id


def test_list_audit_logs_filters_entity(
    client,
    auth_headers_for,
    user,
    clinic,
    db_session,
):
    matching = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        entity_type="Patient",
        entity_id=500,
    )

    make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        entity_type="Patient",
        entity_id=600,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "entity_type": "Patient",
            "entity_id": 500,
        },
        headers=headers,
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == matching.id


def test_list_audit_logs_paginates(
    client,
    auth_headers_for,
    user,
    clinic,
    db_session,
):
    for index in range(5):
        make_audit_log(
            db_session,
            clinic_id=clinic.id,
            user_id=user.id,
            entity_id=100 + index,
        )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "page": "2",
            "per_page": "2",
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["page"] == 2
    assert data["per_page"] == 2
    assert data["total"] == 5
    assert len(data["items"]) == 2


@pytest.mark.parametrize(
    "query_string",
    [
        {"page": "0"},
        {"page": "-1"},
        {"per_page": "0"},
        {"per_page": "101"},
        {"user_id": "0"},
        {"entity_id": "0"},
    ],
)
def test_list_audit_logs_rejects_invalid_filters(
    client,
    auth_headers_for,
    user,
    query_string,
):
    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string=query_string,
        headers=headers,
    )

    assert response.status_code == 422


def test_list_audit_logs_rejects_unknown_filter(
    client,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "clinic_id": 999,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_list_audit_logs_rejects_invalid_action(
    client,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        query_string={
            "action": "invalid",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_list_audit_logs_redacts_sensitive_payloads(
    client,
    auth_headers_for,
    user,
    clinic,
    db_session,
):
    log = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
        new_value={
            "password": "secret",
            "status": "active",
        },
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        BASE_URL,
        headers=headers,
    )

    assert response.status_code == 200

    item = next(
        item
        for item in response.get_json()["data"]["items"]
        if item["id"] == log.id
    )

    assert item["new_value"] == {
        "password": "[REDACTED]",
        "status": "active",
    }


def test_get_single_audit_log_returns_record(
    client,
    auth_headers_for,
    user,
    clinic,
    db_session,
):
    log = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        f"{BASE_URL}/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["success"] is True
    assert payload["data"]["id"] == log.id


def test_admin_cannot_get_other_clinic_audit_log(
    client,
    auth_headers_for,
    user,
    make_clinic,
    db_session,
):
    other_clinic = make_clinic()

    log = make_audit_log(
        db_session,
        clinic_id=other_clinic.id,
        entity_id=999,
    )

    headers = auth_headers_for(
        user,
    )

    response = client.get(
        f"{BASE_URL}/{log.id}",
        headers=headers,
    )

    assert response.status_code == 404


def test_super_admin_can_get_other_clinic_audit_log(
    client,
    auth_headers_for,
    make_user,
    make_clinic,
    db_session,
):
    other_clinic = make_clinic()

    log = make_audit_log(
        db_session,
        clinic_id=other_clinic.id,
        entity_id=999,
    )

    super_admin = make_user(
        None,
        role=Role.SUPER_ADMIN,
    )

    headers = auth_headers_for(
        super_admin,
    )

    response = client.get(
        f"{BASE_URL}/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        response.get_json()["data"]["id"]
        == log.id
    )


def test_get_single_audit_log_returns_404_when_missing(
    client,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
    )

    response = client.get(
        f"{BASE_URL}/999999",
        headers=headers,
    )

    assert response.status_code == 404


def test_get_single_audit_log_rejects_non_admin(
    client,
    auth_headers_for,
    make_user,
    clinic,
    db_session,
):
    doctor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    log = make_audit_log(
        db_session,
        clinic_id=clinic.id,
        user_id=doctor.id,
    )

    headers = auth_headers_for(
        doctor,
    )

    response = client.get(
        f"{BASE_URL}/{log.id}",
        headers=headers,
    )

    assert response.status_code == 403