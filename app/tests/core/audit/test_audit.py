import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role

BASE_URL = "/api/audit-logs"


class BaseAuditTest:
    """Base class providing shared helper methods for audit log tests."""

    def _create_log(
        self,
        db,
        *,
        user_id=None,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=1,
        description="Test audit log",
    ):
        log = create_audit_log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            user_id=user_id,
        )
        db.session.commit()
        return log


class TestGetAuditLogs(BaseAuditTest):
    def test_admin_can_list_audit_logs(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        log = self._create_log(
            db,
            user_id=user.id,
            description="Created patient",
        )

        response = client.get(
            BASE_URL,
            headers=auth_headers_for(user, Role.ADMIN),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert "data" in body
        assert body["data"]["total"] == 1
        assert body["data"]["page"] == 1
        assert body["data"]["per_page"] == 20
        assert body["data"]["pages"] == 1

        assert len(body["data"]["items"]) == 1
        assert body["data"]["items"][0]["id"] == log.id
        assert body["data"]["items"][0]["description"] == "Created patient"

    def test_non_admin_is_forbidden(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        staff_user = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        response = client.get(
            BASE_URL,
            headers=auth_headers_for(staff_user, Role.DOCTOR),
        )

        assert response.status_code == 403
        assert response.get_json()["error"] == "Insufficient permissions"

    def test_missing_authentication_is_rejected(
        self,
        client,
    ):
        response = client.get(BASE_URL)

        assert response.status_code in (401, 422)

        body = response.get_json()
        assert "msg" in body

    def test_filters_by_user_id(
        self,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        db,
    ):
        other_user = make_user(
            clinic,
            role=Role.ADMIN,
        )

        matching = self._create_log(
            db,
            user_id=user.id,
            description="Matching user",
        )

        self._create_log(
            db,
            user_id=other_user.id,
            description="Other user",
        )

        response = client.get(
            f"{BASE_URL}?user_id={user.id}",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        items = body["data"]["items"]

        assert body["data"]["total"] == 1
        assert len(items) == 1
        assert items[0]["id"] == matching.id
        assert items[0]["user_id"] == user.id

    def test_filters_by_action(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        matching = self._create_log(
            db,
            user_id=user.id,
            action=AuditAction.CREATE,
            description="Create action",
        )

        self._create_log(
            db,
            user_id=user.id,
            action=AuditAction.UPDATE,
            description="Update action",
        )

        response = client.get(
            f"{BASE_URL}?action={AuditAction.CREATE.value}",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        items = body["data"]["items"]

        assert body["data"]["total"] == 1
        assert len(items) == 1
        assert items[0]["id"] == matching.id
        assert items[0]["action"] == AuditAction.CREATE.value

    def test_filters_by_entity_type(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        matching = self._create_log(
            db,
            user_id=user.id,
            entity_type="Patient",
            entity_id=10,
        )

        self._create_log(
            db,
            user_id=user.id,
            entity_type="Appointment",
            entity_id=20,
        )

        response = client.get(
            f"{BASE_URL}?entity_type=Patient",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        items = body["data"]["items"]

        assert body["data"]["total"] == 1
        assert len(items) == 1
        assert items[0]["id"] == matching.id
        assert items[0]["entity_type"] == "Patient"

    def test_filters_by_entity_id(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        matching = self._create_log(
            db,
            user_id=user.id,
            entity_type="Patient",
            entity_id=100,
        )

        self._create_log(
            db,
            user_id=user.id,
            entity_type="Patient",
            entity_id=200,
        )

        response = client.get(
            f"{BASE_URL}?entity_id=100",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        items = body["data"]["items"]

        assert body["data"]["total"] == 1
        assert len(items) == 1
        assert items[0]["id"] == matching.id
        assert items[0]["entity_id"] == 100

    def test_combines_multiple_filters(
        self,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        db,
    ):
        other_user = make_user(
            clinic,
            role=Role.ADMIN,
        )

        matching = self._create_log(
            db,
            user_id=user.id,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=55,
            description="Exact match",
        )

        self._create_log(
            db,
            user_id=user.id,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=55,
        )

        self._create_log(
            db,
            user_id=other_user.id,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=55,
        )

        response = client.get(
            (
                f"{BASE_URL}"
                f"?user_id={user.id}"
                f"&action={AuditAction.UPDATE.value}"
                f"&entity_type=Patient"
                f"&entity_id=55"
            ),
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        items = body["data"]["items"]

        assert body["data"]["total"] == 1
        assert len(items) == 1
        assert items[0]["id"] == matching.id

    def test_pagination_parameters_are_forwarded(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        for index in range(5):
            self._create_log(
                db,
                user_id=user.id,
                entity_id=index + 1,
                description=f"Log {index + 1}",
            )

        response = client.get(
            f"{BASE_URL}?page=2&per_page=2",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()
        data = body["data"]

        assert data["total"] == 5
        assert data["page"] == 2
        assert data["per_page"] == 2
        assert data["pages"] == 3
        assert len(data["items"]) == 2

    def test_default_pagination_is_used(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        self._create_log(
            db,
            user_id=user.id,
        )

        response = client.get(
            BASE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["page"] == 1
        assert data["per_page"] == 20

    def test_empty_result_returns_successful_empty_page(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            f"{BASE_URL}?entity_id=999999",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 0
        assert body["data"]["page"] == 1
        assert body["data"]["pages"] == 0

    def test_invalid_action_returns_error(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            f"{BASE_URL}?action=NOT_A_REAL_ACTION",
            headers=auth_headers_for(user),
        )

        assert response.status_code >= 400

    def test_invalid_page_value_uses_flask_default_behavior(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            f"{BASE_URL}?page=invalid",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()["data"]
        assert data["page"] == 1

    def test_response_contains_expected_audit_fields(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        log = self._create_log(
            db,
            user_id=user.id,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=123,
            description="Patient created",
        )

        response = client.get(
            BASE_URL,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        item = response.get_json()["data"]["items"][0]

        assert item["id"] == log.id
        assert item["user_id"] == user.id
        assert item["action"] == AuditAction.CREATE.value
        assert item["entity_type"] == "Patient"
        assert item["entity_id"] == 123
        assert item["description"] == "Patient created"


class TestGetAuditLog(BaseAuditTest):
    def test_admin_can_get_audit_log_by_id(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        log = self._create_log(
            db,
            user_id=user.id,
            entity_type="Patient",
            entity_id=123,
            description="Patient created",
        )

        response = client.get(
            f"{BASE_URL}/{log.id}",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert "data" in body

        data = body["data"]

        assert data["id"] == log.id
        assert data["user_id"] == user.id
        assert data["action"] == AuditAction.CREATE.value
        assert data["entity_type"] == "Patient"
        assert data["entity_id"] == 123
        assert data["description"] == "Patient created"

    def test_non_admin_is_forbidden(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
        db,
    ):
        admin = make_user(
            clinic,
            role=Role.ADMIN,
        )

        log = self._create_log(
            db,
            user_id=admin.id,
        )

        doctor = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        response = client.get(
            f"{BASE_URL}/{log.id}",
            headers=auth_headers_for(doctor, Role.DOCTOR),
        )

        assert response.status_code == 403
        assert response.get_json()["error"] == "Insufficient permissions"

    def test_missing_authentication_is_rejected(
        self,
        client,
        user,
        db,
    ):
        log = self._create_log(
            db,
            user_id=user.id,
        )

        response = client.get(f"{BASE_URL}/{log.id}")

        assert response.status_code in (401, 422)

        body = response.get_json()
        assert "msg" in body

    def test_nonexistent_audit_log_returns_not_found(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            f"{BASE_URL}/999999",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["success"] is False
        assert "error" in body
        assert "Audit log 999999 not found" in body["error"]

    def test_returns_requested_log_when_multiple_exist(
        self,
        client,
        user,
        auth_headers_for,
        db,
    ):
        first = self._create_log(
            db,
            user_id=user.id,
            entity_id=1,
            description="First",
        )

        second = self._create_log(
            db,
            user_id=user.id,
            entity_id=2,
            description="Second",
        )

        response = client.get(
            f"{BASE_URL}/{second.id}",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["id"] == second.id
        assert data["id"] != first.id
        assert data["description"] == "Second"

    def test_integer_log_id_route_constraint(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.get(
            f"{BASE_URL}/not-an-integer",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 404