import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


# ============================================================================
# LIST ROUTE
# ============================================================================


def test_get_audit_logs_requires_authentication(
    client,
    assert_unauthorized,
):
    response = client.get(
        "/api/audit-logs"
    )

    assert_unauthorized(response)


def test_get_audit_logs_requires_admin_role(
    client,
    make_authenticated_staff,
    clinic,
):
    _, headers = make_authenticated_staff(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/audit-logs",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_get_audit_logs_allows_admin(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs",
        headers=headers,
    )

    assert response.status_code == 200


def test_get_audit_logs_returns_empty_list_for_no_records(
    client,
    user,
    auth_headers_for,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 20
    assert body["data"]["pages"] == 0
    assert body["data"]["has_next"] is False
    assert body["data"]["has_prev"] is False


def test_get_audit_logs_returns_records(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user=user,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="Patient created",
        new_value={
            "status": "active",
        },
        ip_address="192.168.1.10",
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert len(body["data"]["items"]) == 1
    assert body["data"]["has_next"] is False
    assert body["data"]["has_prev"] is False

    item = body["data"]["items"][0]

    assert item["user_id"] == user.id
    assert item["action"] == AuditAction.CREATE.value
    assert item["entity_type"] == "Patient"
    assert item["entity_id"] == 100
    assert item["description"] == "Patient created"
    assert item["ip_address"] == "192.168.1.10"


# ============================================================================
# FILTERING
# ============================================================================


def test_get_audit_logs_filters_by_user_id(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user=user,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=999,
        entity_type="Patient",
        entity_id=101,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs?user_id={user.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["user_id"] == user.id


def test_get_audit_logs_filters_by_action(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=user.id,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=101,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?action=update",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1
    assert (
        body["data"]["items"][0]["action"]
        == AuditAction.UPDATE.value
    )


def test_get_audit_logs_filters_by_entity_type(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=user.id,
        entity_type="Appointment",
        entity_id=200,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?entity_type=Patient",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1
    assert (
        body["data"]["items"][0]["entity_type"]
        == "Patient"
    )


def test_get_audit_logs_filters_by_entity_id(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=101,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?entity_id=100",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1
    assert (
        body["data"]["items"][0]["entity_id"]
        == 100
    )


def test_get_audit_logs_combines_filters(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=user.id,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
    )

    make_audit_log(
        user_id=999,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs"
        f"?user_id={user.id}"
        "&action=update"
        "&entity_type=Patient"
        "&entity_id=100",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1

    item = body["data"]["items"][0]

    assert item["user_id"] == user.id
    assert item["action"] == AuditAction.UPDATE.value
    assert item["entity_type"] == "Patient"
    assert item["entity_id"] == 100


# ============================================================================
# PAGINATION
# ============================================================================


def test_get_audit_logs_supports_pagination(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    for entity_id in range(100, 105):
        make_audit_log(
            user_id=user.id,
            entity_id=entity_id,
        )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?page=1&per_page=2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 5
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 2
    assert body["data"]["pages"] == 3
    assert len(body["data"]["items"]) == 2
    assert body["data"]["has_next"] is True
    assert body["data"]["has_prev"] is False


def test_get_audit_logs_returns_second_page(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    for entity_id in range(100, 105):
        make_audit_log(
            user_id=user.id,
            entity_id=entity_id,
        )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?page=2&per_page=2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 2
    assert len(body["data"]["items"]) == 2
    assert body["data"]["has_next"] is True
    assert body["data"]["has_prev"] is True


def test_get_audit_logs_returns_last_page(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    for entity_id in range(100, 105):
        make_audit_log(
            user_id=user.id,
            entity_id=entity_id,
        )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?page=3&per_page=2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["page"] == 3
    assert body["data"]["per_page"] == 2
    assert len(body["data"]["items"]) == 1
    assert body["data"]["has_next"] is False
    assert body["data"]["has_prev"] is True


def test_get_audit_logs_returns_empty_page(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        entity_id=100,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?page=2&per_page=1",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["items"] == []
    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 1
    assert body["data"]["pages"] == 1
    assert body["data"]["has_next"] is False
    assert body["data"]["has_prev"] is True


# ============================================================================
# INVALID QUERY PARAMETERS
# ============================================================================


def test_get_audit_logs_rejects_invalid_action(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?action=not-a-real-action",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "Invalid audit action"


def test_get_audit_logs_rejects_empty_action(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?action=",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "Action cannot be empty"


def test_get_audit_logs_rejects_invalid_user_id(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?user_id=abc",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "user_id must be an integer"


def test_get_audit_logs_rejects_invalid_entity_id(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?entity_id=abc",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "entity_id must be an integer"


def test_get_audit_logs_rejects_invalid_page(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?page=abc",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "page must be an integer"


def test_get_audit_logs_rejects_invalid_per_page(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?per_page=abc",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "per_page must be an integer"


@pytest.mark.parametrize(
    "query",
    [
        "?page=0",
        "?page=-1",
        "?page=true",
    ],
)
def test_get_audit_logs_rejects_invalid_page_values(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
    query,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs{query}",
        headers=headers,
    )

    assert_domain_error(
        response,
        422,
    )


@pytest.mark.parametrize(
    "query",
    [
        "?per_page=0",
        "?per_page=-1",
        "?per_page=101",
    ],
)
def test_get_audit_logs_rejects_invalid_per_page_values(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
    query,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs{query}",
        headers=headers,
    )

    assert_domain_error(
        response,
        422,
    )


def test_get_audit_logs_rejects_empty_integer_parameter(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?user_id=",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == "user_id must be an integer"


# ============================================================================
# DETAIL ROUTE
# ============================================================================


def test_get_audit_log_requires_authentication(
    client,
    assert_unauthorized,
):
    response = client.get(
        "/api/audit-logs/1"
    )

    assert_unauthorized(response)


def test_get_audit_log_requires_admin_role(
    client,
    make_authenticated_staff,
    clinic,
    make_audit_log,
):
    log = make_audit_log(
        entity_type="Patient",
        entity_id=100,
    )

    _, headers = make_authenticated_staff(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/audit-logs/{log.id}",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_get_audit_log_returns_record(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    log = make_audit_log(
        user_id=user.id,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        description="Patient updated",
        old_value={
            "status": "pending",
        },
        new_value={
            "status": "active",
        },
        ip_address="10.0.0.15",
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == log.id
    assert body["data"]["user_id"] == user.id
    assert body["data"]["action"] == AuditAction.UPDATE.value
    assert body["data"]["entity_type"] == "Patient"
    assert body["data"]["entity_id"] == 100
    assert body["data"]["description"] == "Patient updated"
    assert body["data"]["ip_address"] == "10.0.0.15"


def test_get_audit_log_returns_json_values(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    log = make_audit_log(
        user_id=user.id,
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=500,
        old_value={
            "status": "scheduled",
        },
        new_value={
            "status": "completed",
        },
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["old_value"] == {
        "status": "scheduled",
    }

    assert body["data"]["new_value"] == {
        "status": "completed",
    }


def test_get_audit_log_returns_not_found(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs/999999",
        headers=headers,
    )

    body = assert_domain_error(
        response,
        404,
    )

    assert body["error"] == (
        "Audit log 999999 not found"
    )


@pytest.mark.parametrize(
    "log_id",
    [
        0,
        -1,
    ],
)
def test_get_audit_log_rejects_invalid_positive_id(
    client,
    user,
    auth_headers_for,
    assert_domain_error,
    log_id,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs/{log_id}",
        headers=headers,
    )

    # Negative integers do not match Flask's <int:log_id> route,
    # so Flask returns 404 before the service is reached.
    if log_id < 0:
        assert response.status_code == 404
        return

    body = assert_domain_error(
        response,
        422,
    )

    assert body["error"] == (
        "Audit log ID must be a positive integer"
    )


# ============================================================================
# RESPONSE SHAPE
# ============================================================================


def test_get_audit_logs_response_has_expected_structure(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=100,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert body["success"] is True

    assert set(body["data"].keys()) == {
        "items",
        "total",
        "page",
        "per_page",
        "pages",
        "has_next",
        "has_prev",
    }


def test_get_audit_log_response_has_expected_structure(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    log = make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=100,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert body["success"] is True
    assert isinstance(
        body["data"],
        dict,
    )


def test_get_audit_log_response_includes_ip_address(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    log = make_audit_log(
        user_id=user.id,
        entity_type="Patient",
        entity_id=100,
        ip_address="203.0.113.25",
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        f"/api/audit-logs/{log.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["ip_address"] == "203.0.113.25"


# ============================================================================
# QUERY PARAMETER EDGE CASES
# ============================================================================


def test_get_audit_logs_accepts_valid_integer_parameters(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        entity_id=100,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs"
        "?user_id=1"
        "&entity_id=100"
        "&page=1"
        "&per_page=20",
        headers=headers,
    )

    assert response.status_code == 200


def test_get_audit_logs_accepts_action_enum_values(
    client,
    user,
    auth_headers_for,
    make_audit_log,
):
    make_audit_log(
        user_id=user.id,
        action=AuditAction.LOGIN,
        entity_type="User",
        entity_id=user.id,
    )

    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = client.get(
        "/api/audit-logs?action=login",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["total"] == 1
    assert (
        body["data"]["items"][0]["action"]
        == AuditAction.LOGIN.value
    )