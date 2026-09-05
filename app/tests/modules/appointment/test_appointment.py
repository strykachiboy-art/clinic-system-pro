from datetime import datetime, timedelta, timezone
from app.extensions import db

import pytest

from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.enums.role_enums import Role
from app.modules.appointment.models.appointment_model import Appointment


def utcnow():
    return datetime.now(timezone.utc)

def db_datetime(dt):
    return dt.replace(tzinfo=None) if dt.tzinfo else dt

def create_route_appointment(
    db,
    clinic,
    patient,
    staff,
    *,
    start=None,
    end=None,
    status=AppointmentStatus.SCHEDULED,
    reason="Routine consultation",
    notes="Test notes",
    reminder_sent=False,
):
    start = start or (utcnow() + timedelta(days=5))
    end = end or (start + timedelta(hours=1))

    appointment = Appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=start,
        scheduled_end=end,
        appointment_type=AppointmentType.IN_PERSON,
        status=status,
        reason=reason,
        notes=notes,
        reminder_sent=reminder_sent,
    )

    db.session.add(appointment)
    db.session.commit()

    return appointment


def make_headers(make_authenticated_staff, clinic, role=Role.ADMIN):
    _, headers = make_authenticated_staff(
        clinic,
        role=role,
    )
    return headers


def appointment_payload(
    clinic,
    patient,
    staff,
    *,
    start=None,
    end=None,
):
    start = start or (utcnow() + timedelta(days=10))
    end = end or (start + timedelta(hours=1))

    return {
        "clinic_id": clinic.id,
        "patient_id": patient.id,
        "staff_id": staff.id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": end.isoformat(),
        "appointment_type": AppointmentType.IN_PERSON.value,
        "reason": "General consultation",
        "notes": "Route test",
    }


# ============================================================================
# Authentication / authorization
# ============================================================================


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
        Role.RECEPTIONIST,
    ],
)
def test_appointment_create_allows_appointment_roles(
    client,
    clinic,
    patient,
    make_staff,
    make_authenticated_staff,
    role,
):
    staff = make_staff(clinic)

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        role,
    )

    payload = appointment_payload(
        clinic,
        patient,
        staff,
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["patient_id"] == patient.id
    assert body["data"]["staff_id"] == staff.id


def test_appointment_create_requires_authentication(
    client,
    clinic,
    patient,
    staff,
):
    payload = appointment_payload(
        clinic,
        patient,
        staff,
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body


def test_appointment_create_rejects_forbidden_role(
    client,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    # Ambulance dispatcher is intentionally outside APPOINTMENT_ROLES.
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.AMBULANCE_DISPATCHER,
    )

    payload = appointment_payload(
        clinic,
        patient,
        staff,
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


# ============================================================================
# Create
# ============================================================================


def test_create_appointment_route(
    client,
    clinic,
    patient,
    make_staff,
    make_authenticated_staff,
):
    staff = make_staff(clinic)

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    payload = appointment_payload(
        clinic,
        patient,
        staff,
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert data["id"] is not None
    assert data["clinic_id"] == clinic.id
    assert data["patient_id"] == patient.id
    assert data["staff_id"] == staff.id
    assert data["status"] == AppointmentStatus.SCHEDULED.value
    assert data["appointment_type"] == AppointmentType.IN_PERSON.value
    assert data["reason"] == "General consultation"
    assert data["notes"] == "Route test"
    assert data["reminder_sent"] is False


def test_create_appointment_route_rejects_missing_required_fields(
    client,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        "/api/appointments/",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_appointment_route_rejects_invalid_schedule(
    client,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    start = utcnow() + timedelta(days=10)
    end = start - timedelta(hours=1)

    payload = appointment_payload(
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422


def test_create_appointment_route_rejects_schedule_conflict(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    start = utcnow() + timedelta(days=11)
    end = start + timedelta(hours=1)

    create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
    )

    payload = appointment_payload(
        clinic,
        patient,
        staff,
        start=start + timedelta(minutes=15),
        end=end + timedelta(minutes=15),
    )

    response = client.post(
        "/api/appointments/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


# ============================================================================
# Reschedule
# ============================================================================


def test_reschedule_appointment_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    new_start = utcnow() + timedelta(days=20)
    new_end = new_start + timedelta(hours=2)

    response = client.post(
        f"/api/appointments/{appointment.id}/reschedule",
        json={
            "scheduled_start": new_start.isoformat(),
            "scheduled_end": new_end.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == appointment.id
    assert body["data"]["scheduled_start"] == db_datetime(new_start).isoformat()
    assert body["data"]["scheduled_end"] == db_datetime(new_end).isoformat()


def test_reschedule_appointment_route_rejects_invalid_payload(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/reschedule",
        json={},
        headers=headers,
    )

    assert response.status_code == 422


def test_reschedule_appointment_route_returns_not_found(
    client,
    clinic,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    start = utcnow() + timedelta(days=20)
    end = start + timedelta(hours=1)

    response = client.post(
        "/api/appointments/999999/reschedule",
        json={
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# Confirm
# ============================================================================


def test_confirm_appointment_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/confirm",
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == AppointmentStatus.CONFIRMED.value


def test_confirm_appointment_route_returns_not_found(
    client,
    clinic,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        "/api/appointments/999999/confirm",
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# Cancel
# ============================================================================


def test_cancel_appointment_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.RECEPTIONIST,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/cancel",
        json={
            "cancellation_reason": "Patient requested cancellation",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == AppointmentStatus.CANCELLED.value
    assert (
        body["data"]["cancellation_reason"]
        == "Patient requested cancellation"
    )
    assert body["data"]["cancelled_at"] is not None


def test_cancel_appointment_route_accepts_empty_reason(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/cancel",
        json={},
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == AppointmentStatus.CANCELLED.value


# ============================================================================
# Complete
# ============================================================================


def test_complete_appointment_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/complete",
        json={
            "notes": "Consultation completed successfully.",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == AppointmentStatus.COMPLETED.value
    assert (
        body["data"]["notes"]
        == "Consultation completed successfully."
    )


def test_complete_appointment_route_rejects_scheduled_appointment(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/complete",
        json={},
        headers=headers,
    )

    assert response.status_code == 409


# ============================================================================
# No-show
# ============================================================================


def test_mark_no_show_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.CONFIRMED,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.NURSE,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/no-show",
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == AppointmentStatus.NO_SHOW.value


def test_no_show_route_rejects_scheduled_appointment(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        f"/api/appointments/{appointment.id}/no-show",
        headers=headers,
    )

    assert response.status_code == 409


# ============================================================================
# Patient appointments
# ============================================================================


def test_get_patient_appointments_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    first_start = utcnow() + timedelta(days=3)
    second_start = utcnow() + timedelta(days=5)

    first = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_start + timedelta(hours=1),
    )

    second = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=second_start,
        end=second_start + timedelta(hours=1),
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.RECEPTIONIST,
    )

    response = client.get(
        f"/api/appointments/patient/{patient.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["data"][0]["id"] == second.id
    assert body["data"][1]["id"] == first.id


def test_get_patient_appointments_route_not_found(
    client,
    clinic,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        "/api/appointments/patient/999999",
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# Staff appointments
# ============================================================================


def test_get_staff_appointments_route(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    start = utcnow() + timedelta(days=12)

    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=start + timedelta(hours=1),
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        f"/api/appointments/staff/{staff.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == appointment.id


def test_get_staff_appointments_route_filters_by_date(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    first_start = utcnow() + timedelta(days=12)
    second_start = first_start + timedelta(days=1)

    first = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=first_start,
        end=first_start + timedelta(hours=1),
    )

    create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=second_start,
        end=second_start + timedelta(hours=1),
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        f"/api/appointments/staff/{staff.id}",
        query_string={
            "date_": first_start.date().isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == first.id


def test_get_staff_appointments_route_not_found(
    client,
    clinic,
    make_authenticated_staff,
):
    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        "/api/appointments/staff/999999",
        headers=headers,
    )

    assert response.status_code == 404


# ============================================================================
# Serialization
# ============================================================================


def test_appointment_route_serializes_all_expected_fields(
    client,
    db,
    clinic,
    patient,
    staff,
    make_authenticated_staff,
):
    start = utcnow() + timedelta(days=15)
    end = start + timedelta(hours=1)

    appointment = create_route_appointment(
        db,
        clinic,
        patient,
        staff,
        start=start,
        end=end,
        reason="Follow-up",
        notes="Important notes",
    )

    headers = make_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.get(
        f"/api/appointments/patient/{patient.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()

    data = response.get_json()["data"][0]

    expected_fields = {
        "id",
        "clinic_id",
        "patient_id",
        "staff_id",
        "scheduled_start",
        "scheduled_end",
        "status",
        "appointment_type",
        "reason",
        "notes",
        "google_calendar_event_id",
        "reminder_sent",
        "created_at",
        "updated_at",
        "cancelled_at",
        "cancellation_reason",
    }

    assert expected_fields.issubset(data.keys())

    assert data["id"] == appointment.id
    assert data["clinic_id"] == clinic.id
    assert data["patient_id"] == patient.id
    assert data["staff_id"] == staff.id
    assert data["status"] == AppointmentStatus.SCHEDULED.value
    assert data["appointment_type"] == AppointmentType.IN_PERSON.value
    assert data["reason"] == "Follow-up"
    assert data["notes"] == "Important notes"
    assert data["reminder_sent"] is False
    assert data["cancelled_at"] is None
    assert data["cancellation_reason"] is None