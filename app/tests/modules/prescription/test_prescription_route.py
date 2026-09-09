from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.prescription_enums import (
    DrugInteractionSeverity,
    PrescriptionStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.prescription.routes import prescription_routes


# ============================================================================
# Helpers
# ============================================================================

def _utcnow():
    return datetime.now(timezone.utc)


def _future():
    return _utcnow() + timedelta(days=30)


def _prescription_item(
    *,
    item_id=10,
    prescription_id=1,
    drug_id=7,
    dosage="500 mg",
    frequency="twice daily",
    duration="7 days",
    quantity=14,
    instructions="Take after meals",
):
    return SimpleNamespace(
        id=item_id,
        prescription_id=prescription_id,
        drug_id=drug_id,
        dosage=dosage,
        frequency=frequency,
        duration=duration,
        quantity=quantity,
        instructions=instructions,
    )


def _prescription(
    *,
    prescription_id=1,
    clinic_id=1,
    patient_id=2,
    consultation_id=3,
    prescribed_by_id=4,
    status=PrescriptionStatus.ACTIVE,
    notes="Take as directed",
    issued_at=None,
    expires_at=None,
    items=None,
):
    return SimpleNamespace(
        id=prescription_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        consultation_id=consultation_id,
        prescribed_by_id=prescribed_by_id,
        status=status,
        notes=notes,
        issued_at=issued_at or _utcnow(),
        expires_at=expires_at,
        items=items or [
            _prescription_item(
                prescription_id=prescription_id
            )
        ],
    )


def _interaction(
    *,
    interaction_id=20,
    drug_a_id=7,
    drug_b_id=8,
    severity=DrugInteractionSeverity.SEVERE,
    description="Known serious interaction",
):
    return SimpleNamespace(
        id=interaction_id,
        drug_a_id=drug_a_id,
        drug_b_id=drug_b_id,
        severity=severity,
        description=description,
    )


def _json_headers(make_authenticated_staff, clinic, role):
    staff, headers = make_authenticated_staff(
        clinic,
        role,
    )

    headers = dict(headers)
    headers["Content-Type"] = "application/json"

    return headers, staff


# ============================================================================
# CREATE PRESCRIPTION
# ============================================================================

def test_create_prescription_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    expires_at = _future()

    prescription = _prescription(
        clinic_id=clinic.id,
        patient_id=2,
        prescribed_by_id=staff.id,
    )

    create_mock = Mock(
        return_value=(
            prescription,
            [],
        )
    )

    monkeypatch.setattr(
        prescription_routes,
        "create_prescription",
        create_mock,
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 2,
            "prescribed_by_id": staff.id,
            "consultation_id": 3,
            "items": [
                {
                    "drug_id": 7,
                    "dosage": "500 mg",
                    "frequency": "twice daily",
                    "duration": "7 days",
                    "quantity": 14,
                    "instructions": "Take after meals",
                }
            ],
            "expires_at": expires_at.isoformat(),
            "notes": "Take as directed",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == (
        "Prescription created successfully"
    )
    assert body["data"]["id"] == prescription.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["patient_id"] == prescription.patient_id
    assert body["data"]["prescribed_by_id"] == staff.id
    assert body["data"]["status"] == "active"
    assert body["interaction_warnings"] == []

    create_mock.assert_called_once_with(
        clinic_id=clinic.id,
        patient_id=2,
        prescribed_by_id=staff.id,
        items=[
            {
                "drug_id": 7,
                "dosage": "500 mg",
                "frequency": "twice daily",
                "duration": "7 days",
                "quantity": 14,
                "instructions": "Take after meals",
            }
        ],
        consultation_id=3,
        expires_at=expires_at,
        notes="Take as directed",
    )


def test_create_prescription_returns_interaction_warnings(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        prescribed_by_id=staff.id,
    )

    warnings = [
        {
            "drug_a_id": 7,
            "drug_b_id": 8,
            "severity": "severe",
            "description": "Known serious interaction",
        }
    ]

    monkeypatch.setattr(
        prescription_routes,
        "create_prescription",
        Mock(
            return_value=(
                prescription,
                warnings,
            )
        ),
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 2,
            "prescribed_by_id": staff.id,
            "items": [
                {"drug_id": 7},
                {"drug_id": 8},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["interaction_warnings"] == warnings


def test_create_prescription_rejects_different_prescribing_staff(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 2,
            "prescribed_by_id": staff.id + 999,
            "items": [
                {"drug_id": 7},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert (
        "Authenticated doctor must be the prescribing staff member"
        in body["error"]
    )


def test_create_prescription_does_not_trust_client_clinic_id(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        prescribed_by_id=staff.id,
    )

    create_mock = Mock(
        return_value=(
            prescription,
            [],
        )
    )

    monkeypatch.setattr(
        prescription_routes,
        "create_prescription",
        create_mock,
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id + 999,
            "patient_id": 2,
            "prescribed_by_id": staff.id,
            "items": [
                {"drug_id": 7},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201

    create_mock.assert_called_once()

    assert (
        create_mock.call_args.kwargs["clinic_id"]
        == clinic.id
    )


def test_create_prescription_requires_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions",
        json=[
            {
                "patient_id": 2,
            }
        ],
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_create_prescription_rejects_extra_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 2,
            "prescribed_by_id": staff.id,
            "items": [
                {
                    "drug_id": 7,
                    "unexpected": "forbidden",
                }
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# GET PRESCRIPTION
# ============================================================================

def test_get_prescription_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
    )

    get_mock = Mock(
        return_value=prescription
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        get_mock,
    )

    response = client.get(
        f"/prescriptions/{prescription.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == prescription.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["status"] == "active"

    get_mock.assert_called_once_with(
        prescription.id
    )


def test_get_prescription_rejects_cross_clinic_access(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id + 999,
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        Mock(
            return_value=prescription
        ),
    )

    response = client.get(
        f"/prescriptions/{prescription.id}",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert (
        "does not belong to clinic"
        in body["error"]
    )


def test_get_prescription_allows_historical_read_for_inactive_clinic(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        status=PrescriptionStatus.COMPLETED,
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        Mock(
            return_value=prescription
        ),
    )

    response = client.get(
        f"/prescriptions/{prescription.id}",
        headers=headers,
    )

    assert response.status_code == 200


def test_get_prescription_not_found(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        Mock(
            side_effect=NotFoundError(
                "Prescription 999 not found"
            )
        ),
    )

    response = client.get(
        "/prescriptions/999",
        headers=headers,
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# LIST PATIENT PRESCRIPTIONS
# ============================================================================

def test_list_patient_prescriptions_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescriptions = [
        _prescription(
            prescription_id=1,
            clinic_id=clinic.id,
        ),
        _prescription(
            prescription_id=2,
            clinic_id=clinic.id,
            status=PrescriptionStatus.COMPLETED,
        ),
    ]

    list_mock = Mock(
        return_value=prescriptions
    )

    monkeypatch.setattr(
        prescription_routes,
        "list_prescriptions_for_patient",
        list_mock,
    )

    response = client.get(
        "/prescriptions/patients/2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2

    list_mock.assert_called_once_with(
        patient_id=2,
        clinic_id=clinic.id,
        active_only=False,
    )


def test_list_patient_prescriptions_active_only(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    list_mock = Mock(
        return_value=[]
    )

    monkeypatch.setattr(
        prescription_routes,
        "list_prescriptions_for_patient",
        list_mock,
    )

    response = client.get(
        "/prescriptions/patients/2?active_only=true",
        headers=headers,
    )

    assert response.status_code == 200

    list_mock.assert_called_once_with(
        patient_id=2,
        clinic_id=clinic.id,
        active_only=True,
    )


def test_list_patient_prescriptions_active_only_is_case_insensitive(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    list_mock = Mock(
        return_value=[]
    )

    monkeypatch.setattr(
        prescription_routes,
        "list_prescriptions_for_patient",
        list_mock,
    )

    response = client.get(
        "/prescriptions/patients/2?active_only=TRUE",
        headers=headers,
    )

    assert response.status_code == 200

    list_mock.assert_called_once_with(
        patient_id=2,
        clinic_id=clinic.id,
        active_only=True,
    )


# ============================================================================
# CANCEL
# ============================================================================

def test_cancel_prescription_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        status=PrescriptionStatus.CANCELLED,
        notes="Existing notes",
    )

    cancel_mock = Mock(
        return_value=prescription
    )

    monkeypatch.setattr(
        prescription_routes,
        "cancel_prescription",
        cancel_mock,
    )

    response = client.post(
        f"/prescriptions/{prescription.id}/cancel",
        json={
            "reason": "Patient requested cancellation",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == (
        "Prescription cancelled successfully"
    )
    assert body["data"]["id"] == prescription.id

    cancel_mock.assert_called_once_with(
        prescription_id=prescription.id,
        clinic_id=clinic.id,
        reason="Patient requested cancellation",
    )


def test_cancel_prescription_without_reason(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        status=PrescriptionStatus.CANCELLED,
    )

    cancel_mock = Mock(
        return_value=prescription
    )

    monkeypatch.setattr(
        prescription_routes,
        "cancel_prescription",
        cancel_mock,
    )

    response = client.post(
        f"/prescriptions/{prescription.id}/cancel",
        json={},
        headers=headers,
    )

    assert response.status_code == 200

    cancel_mock.assert_called_once_with(
        prescription_id=prescription.id,
        clinic_id=clinic.id,
        reason=None,
    )


def test_cancel_prescription_rejects_extra_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions/1/cancel",
        json={
            "reason": "No longer required",
            "status": "cancelled",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# COMPLETE
# ============================================================================

def test_complete_prescription_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    prescription = _prescription(
        clinic_id=clinic.id,
        status=PrescriptionStatus.COMPLETED,
    )

    complete_mock = Mock(
        return_value=prescription
    )

    monkeypatch.setattr(
        prescription_routes,
        "complete_prescription",
        complete_mock,
    )

    response = client.post(
        f"/prescriptions/{prescription.id}/complete",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == (
        "Prescription completed successfully"
    )
    assert body["data"]["id"] == prescription.id
    assert body["data"]["status"] == "completed"

    complete_mock.assert_called_once_with(
        prescription_id=prescription.id,
        clinic_id=clinic.id,
    )


# ============================================================================
# DRUG INTERACTION CHECK
# ============================================================================

def test_check_drug_interactions_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    warnings = [
        {
            "drug_a_id": 7,
            "drug_b_id": 8,
            "severity": "severe",
            "description": "Known interaction",
        }
    ]

    check_mock = Mock(
        return_value=warnings
    )

    monkeypatch.setattr(
        prescription_routes,
        "check_interactions",
        check_mock,
    )

    response = client.post(
        "/prescriptions/interactions/check",
        json={
            "drug_ids": [7, 8],
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["drug_ids"] == [7, 8]
    assert body["data"]["has_interactions"] is True
    assert body["data"]["interaction_warnings"] == warnings

    check_mock.assert_called_once_with(
        drug_ids=[7, 8],
        clinic_id=clinic.id,
    )


def test_check_drug_interactions_no_interactions(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    check_mock = Mock(
        return_value=[]
    )

    monkeypatch.setattr(
        prescription_routes,
        "check_interactions",
        check_mock,
    )

    response = client.post(
        "/prescriptions/interactions/check",
        json={
            "drug_ids": [7, 8],
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["has_interactions"] is False
    assert body["data"]["interaction_warnings"] == []


def test_check_drug_interactions_requires_at_least_two_drugs(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions/interactions/check",
        json={
            "drug_ids": [7],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_check_drug_interactions_rejects_duplicate_drugs(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions/interactions/check",
        json={
            "drug_ids": [7, 7],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_check_drug_interactions_rejects_zero_id(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    response = client.post(
        "/prescriptions/interactions/check",
        json={
            "drug_ids": [0, 7],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# CREATE DRUG INTERACTION
# ============================================================================

def test_create_drug_interaction_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    interaction = _interaction()

    create_mock = Mock(
        return_value=interaction
    )

    monkeypatch.setattr(
        prescription_routes,
        "create_drug_interaction",
        create_mock,
    )

    response = client.post(
        "/prescriptions/interactions",
        json={
            "drug_a_id": 7,
            "drug_b_id": 8,
            "severity": "severe",
            "description": "Known serious interaction",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["message"] == (
        "Drug interaction created successfully"
    )
    assert body["data"]["id"] == interaction.id
    assert body["data"]["drug_a_id"] == 7
    assert body["data"]["drug_b_id"] == 8
    assert body["data"]["severity"] == "severe"
    assert body["data"]["description"] == (
        "Known serious interaction"
    )

    create_mock.assert_called_once_with(
        drug_a_id=7,
        drug_b_id=8,
        severity=DrugInteractionSeverity.SEVERE,
        description="Known serious interaction",
    )


def test_create_drug_interaction_rejects_self_interaction(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        "/prescriptions/interactions",
        json={
            "drug_a_id": 7,
            "drug_b_id": 7,
            "severity": "severe",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_create_drug_interaction_rejects_invalid_severity(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        "/prescriptions/interactions",
        json={
            "drug_a_id": 7,
            "drug_b_id": 8,
            "severity": "critical",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_create_drug_interaction_rejects_extra_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    response = client.post(
        "/prescriptions/interactions",
        json={
            "drug_a_id": 7,
            "drug_b_id": 8,
            "severity": "severe",
            "unexpected": "forbidden",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


# ============================================================================
# ERROR PROPAGATION
# ============================================================================

def test_create_prescription_service_validation_error(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    monkeypatch.setattr(
        prescription_routes,
        "create_prescription",
        Mock(
            side_effect=ValidationError(
                "Patient does not belong to clinic"
            )
        ),
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 999,
            "prescribed_by_id": staff.id,
            "items": [
                {"drug_id": 7},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert (
        "Patient does not belong to clinic"
        in body["error"]
    )


def test_create_prescription_unexpected_exception_is_generic_500(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    monkeypatch.setattr(
        prescription_routes,
        "create_prescription",
        Mock(
            side_effect=RuntimeError(
                "SECRET INTERNAL PRESCRIPTION DETAIL"
            )
        ),
    )

    response = client.post(
        "/prescriptions",
        json={
            "clinic_id": clinic.id,
            "patient_id": 2,
            "prescribed_by_id": staff.id,
            "items": [
                {"drug_id": 7},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 500

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Internal server error"

    assert (
        "SECRET INTERNAL PRESCRIPTION DETAIL"
        not in response.get_data(
            as_text=True
        )
    )


# ============================================================================
# SERIALIZATION
# ============================================================================

def test_serialize_prescription_includes_items(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    item = _prescription_item(
        item_id=55,
        prescription_id=10,
        drug_id=77,
    )

    prescription = _prescription(
        prescription_id=10,
        clinic_id=clinic.id,
        items=[item],
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        Mock(
            return_value=prescription
        ),
    )

    response = client.get(
        "/prescriptions/10",
        headers=headers,
    )

    assert response.status_code == 200

    item_data = response.get_json()["data"]["items"][0]

    assert item_data == {
        "id": 55,
        "prescription_id": 10,
        "drug_id": 77,
        "dosage": "500 mg",
        "frequency": "twice daily",
        "duration": "7 days",
        "quantity": 14,
        "instructions": "Take after meals",
    }


def test_serialize_prescription_handles_nullable_dates(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    issued_at = _utcnow()

    prescription = _prescription(
        clinic_id=clinic.id,
        issued_at=issued_at,
        expires_at=None,
    )

    monkeypatch.setattr(
        prescription_routes,
        "get_prescription",
        Mock(
            return_value=prescription
        ),
    )

    response = client.get(
        "/prescriptions/1",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["issued_at"] == issued_at.isoformat()
    assert data["expires_at"] is None


# ============================================================================
# ROUTE EXISTENCE
# ============================================================================

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/prescriptions/1"),
        ("GET", "/prescriptions/patients/1"),
        ("POST", "/prescriptions"),
        ("POST", "/prescriptions/1/cancel"),
        ("POST", "/prescriptions/1/complete"),
        ("POST", "/prescriptions/interactions/check"),
        ("POST", "/prescriptions/interactions"),
    ],
)
def test_prescription_routes_exist(
    client,
    method,
    path,
):
    if method == "GET":
        response = client.get(path)
    else:
        response = client.post(path)

    assert response.status_code != 404