from __future__ import annotations

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


def _headers(login: dict) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
    }


def test_audit_api_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_staff,
    e2e_login,
):
    # ================================================================
    # PRIMARY CLINIC ADMIN
    # ================================================================

    admin_staff = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
        user_overrides={
            "email": "e2e-g15c-audit-admin@test.com",
        },
    )

    admin = admin_staff.user

    admin_login = e2e_login(
        "e2e-g15c-audit-admin@test.com",
    )

    admin_headers = _headers(
        admin_login
    )

    assert admin_login["user_id"] == admin.id
    assert admin_login["role"] == Role.ADMIN.value

    # ================================================================
    # CREATE A REAL AUDITABLE RESOURCE
    # ================================================================

    patient_response = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Gate",
            "last_name": "FifteenCAudit",
        },
        headers=admin_headers,
    )

    assert patient_response.status_code == 201, (
        patient_response.get_json()
    )

    patient_body = patient_response.get_json()

    assert patient_body["success"] is True
    assert patient_body["data"]["clinic_id"] == clinic.id

    patient_id = patient_body["data"]["id"]

    # ================================================================
    # VERIFY REAL AUDIT RECORD EXISTS
    # ================================================================

    audit_rows = (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "patient",
                AuditLog.entity_id == patient_id,
                AuditLog.user_id == admin.id,
                AuditLog.action == AuditAction.CREATE,
            )
            .order_by(
                AuditLog.id.desc(),
            )
        )
        .scalars()
        .all()
    )

    assert audit_rows

    audit_log = audit_rows[0]

    assert audit_log.clinic_id == clinic.id
    assert audit_log.user_id == admin.id
    assert audit_log.entity_type == "patient"
    assert audit_log.entity_id == patient_id
    assert audit_log.action is AuditAction.CREATE

    # ================================================================
    # AUDIT LIST API — CLINIC SCOPED
    # ================================================================

    list_response = client.get(
        "/api/v1/audit-logs",
        query_string={
            "entity_type": "patient",
            "entity_id": patient_id,
        },
        headers=admin_headers,
    )

    assert list_response.status_code == 200, (
        list_response.get_json()
    )

    list_body = list_response.get_json()

    assert list_body["success"] is True
    assert list_body["data"]["total"] >= 1

    matching_items = [
        item
        for item in list_body["data"]["items"]
        if item["id"] == audit_log.id
    ]

    assert matching_items

    list_item = matching_items[0]

    assert list_item["id"] == audit_log.id
    assert list_item["clinic_id"] == clinic.id
    assert list_item["user_id"] == admin.id
    assert list_item["entity_type"] == "patient"
    assert list_item["entity_id"] == patient_id
    assert list_item["action"] == AuditAction.CREATE.value

    # ================================================================
    # AUDIT SINGLE-RECORD API
    # ================================================================

    single_response = client.get(
        f"/api/v1/audit-logs/{audit_log.id}",
        headers=admin_headers,
    )

    assert single_response.status_code == 200, (
        single_response.get_json()
    )

    single_body = single_response.get_json()

    assert single_body["success"] is True
    assert single_body["data"]["id"] == audit_log.id
    assert single_body["data"]["clinic_id"] == clinic.id
    assert single_body["data"]["user_id"] == admin.id
    assert single_body["data"]["entity_type"] == "patient"
    assert single_body["data"]["entity_id"] == patient_id

    # ================================================================
    # SECOND CLINIC
    # ================================================================

    second_clinic = make_clinic(
        name="Gate 15C Audit Foreign Clinic",
    )

    foreign_staff = make_staff(
        clinic=second_clinic,
        role=Role.ADMIN,
        user_overrides={
            "email": "e2e-g15c-audit-foreign@test.com",
        },
    )

    foreign_login = e2e_login(
        "e2e-g15c-audit-foreign@test.com",
    )

    foreign_headers = _headers(
        foreign_login
    )

    assert foreign_login["user_id"] == foreign_staff.user.id
    assert foreign_login["role"] == Role.ADMIN.value

    # ================================================================
    # CROSS-CLINIC SINGLE-LOG DENIAL
    # ================================================================

    foreign_single_response = client.get(
        f"/api/v1/audit-logs/{audit_log.id}",
        headers=foreign_headers,
    )

    assert foreign_single_response.status_code == 404

    # ================================================================
    # CROSS-CLINIC LIST MUST NOT EXPOSE PRIMARY AUDIT ROW
    # ================================================================

    foreign_list_response = client.get(
        "/api/v1/audit-logs",
        query_string={
            "entity_type": "patient",
            "entity_id": patient_id,
        },
        headers=foreign_headers,
    )

    assert foreign_list_response.status_code == 200, (
        foreign_list_response.get_json()
    )

    foreign_list_body = (
        foreign_list_response.get_json()
    )

    assert foreign_list_body["success"] is True

    foreign_ids = {
        item["id"]
        for item in foreign_list_body["data"]["items"]
    }

    assert audit_log.id not in foreign_ids

    # Foreign clinic must never receive this primary-clinic audit row.
    assert all(
        item["clinic_id"] == second_clinic.id
        for item in foreign_list_body["data"]["items"]
    )

    print(
        "PHASE8_E2E_GATE15C_AUDIT_API=PASS"
    )
