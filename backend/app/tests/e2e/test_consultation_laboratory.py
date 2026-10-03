from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.lab.models.lab_model import (
    LabOrder,
    LabOrderItem,
    LabTest,
)
from app.modules.patient.models.patient_model import Patient


def test_consultation_laboratory_e2e(
    client,
    db,
    clinic,
    make_user,
    make_staff,
    e2e_login,
):
    admin = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        email="e2e-lab-admin@test.com",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-lab-doctor@test.com",
        },
    )

    lab_staff = make_staff(
        clinic=clinic,
        role=Role.LAB_TECHNICIAN,
        user_overrides={
            "email": "e2e-lab-tech@test.com",
        },
    )

    receptionist = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
        email="e2e-lab-receptionist@test.com",
    )

    admin_login = e2e_login(
        "e2e-lab-admin@test.com",
    )

    doctor_login = e2e_login(
        "e2e-lab-doctor@test.com",
    )

    lab_login = e2e_login(
        "e2e-lab-tech@test.com",
    )

    receptionist_login = e2e_login(
        "e2e-lab-receptionist@test.com",
    )

    assert admin_login["role"] == Role.ADMIN.value
    assert doctor_login["role"] == Role.DOCTOR.value
    assert lab_login["role"] == Role.LAB_TECHNICIAN.value
    assert receptionist_login["role"] == Role.RECEPTIONIST.value

    patient_response = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Lab",
            "last_name": "Patient",
        },
        headers={
            "Authorization": (
                f"Bearer {receptionist_login['access_token']}"
            ),
        },
    )

    assert patient_response.status_code == 201, (
        patient_response.get_json()
    )

    patient_id = patient_response.get_json()["data"]["id"]

    persisted_patient = db.session.get(
        Patient,
        patient_id,
    )

    assert persisted_patient is not None
    assert persisted_patient.clinic_id == clinic.id

    scheduled_start = (
        datetime.now(timezone.utc)
        + timedelta(days=1)
    )

    scheduled_end = (
        scheduled_start
        + timedelta(minutes=30)
    )

    appointment_response = client.post(
        "/api/v1/appointments/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "scheduled_start": scheduled_start.isoformat(),
            "scheduled_end": scheduled_end.isoformat(),
            "appointment_type": "in_person",
            "reason": "Phase 8 laboratory workflow",
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert appointment_response.status_code == 201, (
        appointment_response.get_json()
    )

    appointment_id = appointment_response.get_json()["data"]["id"]

    consultation_response = client.post(
        "/api/v1/consultations/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "appointment_id": appointment_id,
            "consultation_type": "general",
            "chief_complaint": "Laboratory workflow",
            "symptoms": "Phase 8 E2E",
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert consultation_response.status_code == 201, (
        consultation_response.get_json()
    )

    consultation_id = consultation_response.get_json()["data"]["id"]

    persisted_consultation = db.session.get(
        Consultation,
        consultation_id,
    )

    assert persisted_consultation is not None
    assert persisted_consultation.clinic_id == clinic.id
    assert persisted_consultation.patient_id == patient_id
    assert persisted_consultation.appointment_id == appointment_id

    lab_test_response = client.post(
        "/api/v1/lab/tests",
        json={
            "name": "Complete Blood Count",
            "loinc_code": "57021-8",
            "code": "CBC-E2E",
            "sample_type": "blood",
            "reference_range": "4.0-11.0",
            "unit": "10^9/L",
            "price": "25.00",
            "critical_low": "2.0",
            "critical_high": "20.0",
            "is_active": True,
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert lab_test_response.status_code == 201, (
        lab_test_response.get_json()
    )

    lab_test_body = lab_test_response.get_json()

    assert lab_test_body["success"] is True
    assert lab_test_body["data"]["clinic_id"] == clinic.id
    assert lab_test_body["data"]["name"] == "Complete Blood Count"

    lab_test_id = lab_test_body["data"]["id"]

    persisted_lab_test = db.session.get(
        LabTest,
        lab_test_id,
    )

    assert persisted_lab_test is not None
    assert persisted_lab_test.clinic_id == clinic.id
    assert persisted_lab_test.is_active is True

    lab_order_response = client.post(
        "/api/v1/lab/orders",
        json={
            "patient_id": patient_id,
            "test_ids": [lab_test_id],
            "consultation_id": consultation_id,
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert lab_order_response.status_code == 201, (
        lab_order_response.get_json()
    )

    lab_order_body = lab_order_response.get_json()

    assert lab_order_body["success"] is True
    assert lab_order_body["data"]["clinic_id"] == clinic.id
    assert lab_order_body["data"]["patient_id"] == patient_id
    assert lab_order_body["data"]["consultation_id"] == consultation_id
    assert lab_order_body["data"]["ordered_by_id"] == doctor_staff.id
    assert lab_order_body["data"]["status"] == "ordered"
    assert lab_order_body["data"]["items"]

    lab_order_id = lab_order_body["data"]["id"]
    order_item_id = lab_order_body["data"]["items"][0]["id"]

    persisted_order = db.session.get(
        LabOrder,
        lab_order_id,
    )

    assert persisted_order is not None
    assert persisted_order.clinic_id == clinic.id
    assert persisted_order.patient_id == patient_id
    assert persisted_order.consultation_id == consultation_id
    assert persisted_order.ordered_by_id == doctor_staff.id

    persisted_item = db.session.get(
        LabOrderItem,
        order_item_id,
    )

    assert persisted_item is not None
    assert persisted_item.order_id == lab_order_id
    assert persisted_item.test_id == lab_test_id

    qr_code = lab_order_body["data"]["qr_code"]

    collect_response = client.post(
        f"/api/v1/lab/orders/{lab_order_id}/collect-sample",
        json={
            "scanned_qr_code": qr_code,
        },
        headers={
            "Authorization": (
                f"Bearer {lab_login['access_token']}"
            ),
        },
    )

    assert collect_response.status_code == 200, (
        collect_response.get_json()
    )

    assert (
        collect_response.get_json()["data"]["status"]
        == "sample_collected"
    )

    process_response = client.post(
        f"/api/v1/lab/orders/{lab_order_id}/process",
        json={},
        headers={
            "Authorization": (
                f"Bearer {lab_login['access_token']}"
            ),
        },
    )

    assert process_response.status_code == 200, (
        process_response.get_json()
    )

    assert (
        process_response.get_json()["data"]["status"]
        == "in_progress"
    )

    result_response = client.post(
        f"/api/v1/lab/order-items/{order_item_id}/result",
        json={
            "result_value": "7.2",
            "flag": "normal",
            "result_notes": "Phase 8 E2E result",
        },
        headers={
            "Authorization": (
                f"Bearer {lab_login['access_token']}"
            ),
        },
    )

    assert result_response.status_code == 200, (
        result_response.get_json()
    )

    result_body = result_response.get_json()

    assert result_body["success"] is True
    assert result_body["data"]["id"] == order_item_id
    assert result_body["data"]["result_value"] == "7.2"
    assert result_body["data"]["flag"] == "normal"

    verify_response = client.post(
        f"/api/v1/lab/orders/{lab_order_id}/verify",
        json={},
        headers={
            "Authorization": (
                f"Bearer {lab_login['access_token']}"
            ),
        },
    )

    assert verify_response.status_code == 200, (
        verify_response.get_json()
    )

    assert (
        verify_response.get_json()["data"]["verified_by_id"]
        == lab_staff.id
    )

    complete_response = client.post(
        f"/api/v1/lab/orders/{lab_order_id}/complete",
        json={},
        headers={
            "Authorization": (
                f"Bearer {lab_login['access_token']}"
            ),
        },
    )

    assert complete_response.status_code == 200, (
        complete_response.get_json()
    )

    complete_body = complete_response.get_json()

    assert complete_body["success"] is True
    assert complete_body["data"]["status"] == "completed"
    assert complete_body["data"]["completed_at"] is not None

    persisted_order = db.session.get(
        LabOrder,
        lab_order_id,
    )

    assert persisted_order is not None
    assert persisted_order.status.value == "completed"
    assert persisted_order.ordered_by_id == doctor_staff.id
    assert persisted_order.collected_by_id == lab_staff.id
    assert persisted_order.processed_by_id == lab_staff.id
    assert persisted_order.verified_by_id == lab_staff.id
    assert persisted_order.completed_at is not None

    persisted_item = db.session.get(
        LabOrderItem,
        order_item_id,
    )

    assert persisted_item is not None
    assert persisted_item.result_value == "7.2"
    assert persisted_item.resulted_at is not None

    audit_rows = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_id.in_(
                    [
                        lab_test_id,
                        lab_order_id,
                        order_item_id,
                    ]
                )
            )
            .order_by(
                AuditLog.id.asc(),
            )
        ).scalars()
    )

    assert audit_rows
    assert all(
        row.clinic_id == clinic.id
        for row in audit_rows
    )

    assert any(
        row.entity_type == "LabTest"
        and row.entity_id == lab_test_id
        and row.action is AuditAction.CREATE
        for row in audit_rows
    )

    assert any(
        row.entity_type == "LabOrder"
        and row.entity_id == lab_order_id
        and row.action is AuditAction.CREATE
        for row in audit_rows
    )

    assert any(
        row.entity_type == "LabOrder"
        and row.entity_id == lab_order_id
        and row.action is AuditAction.STATUS_CHANGE
        for row in audit_rows
    )

    second_clinic = clinic.__class__(
        name="E2E Lab Clinic 2",
        ai_credits=5,
        status=clinic.status,
    )

    db.session.add(second_clinic)
    db.session.flush()

    second_doctor = make_staff(
        clinic=second_clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-lab-doctor-clinic-2@test.com",
        },
    )

    second_doctor_login = e2e_login(
        "e2e-lab-doctor-clinic-2@test.com",
    )

    assert second_doctor_login["role"] == Role.DOCTOR.value

    cross_tenant_order_response = client.post(
        "/api/v1/lab/orders",
        json={
            "patient_id": patient_id,
            "test_ids": [lab_test_id],
            "consultation_id": consultation_id,
        },
        headers={
            "Authorization": (
                f"Bearer {second_doctor_login['access_token']}"
            ),
        },
    )

    assert cross_tenant_order_response.status_code in (404, 422)

    cross_tenant_get_response = client.get(
        f"/api/v1/lab/orders/{lab_order_id}",
        headers={
            "Authorization": (
                f"Bearer {second_doctor_login['access_token']}"
            ),
        },
    )

    assert cross_tenant_get_response.status_code == 404

    print("PHASE8_E2E_CONSULTATION_LABORATORY=PASS")
