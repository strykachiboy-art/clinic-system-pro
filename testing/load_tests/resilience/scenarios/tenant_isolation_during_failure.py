from __future__ import annotations

import pytest

from app.core.enums.role_enums import Role
from app.core.auth.user.models.user_model import User
from app.extensions import db
from app.modules.patient.models.patient_model import Patient
from app.modules.patient.routes import patient_route
from load_tests.resilience.common.faults import (
    FaultInjector,
    FaultType,
    InjectedConnectionError,
)


def _headers(
    make_authenticated_staff,
    clinic,
    role,
):
    _, headers = make_authenticated_staff(
        clinic,
        role,
    )

    return headers


def _raise_downstream_failure(
    injector: FaultInjector,
    operation: str,
    original,
):
    def _failure(*args, **kwargs):
        injector.inject(
            "postgres",
            operation=operation,
        )

        return original(
            *args,
            **kwargs,
        )

    return _failure


def test_cross_clinic_patient_read_fails_closed_during_dependency_failure(
    client,
    clinic,
    make_clinic,
    make_patient,
    make_authenticated_staff,
    monkeypatch,
):
    other_clinic = make_clinic(
        name="Tenant Failure Other Clinic",
    )

    other_patient = make_patient(
        other_clinic,
        first_name="Foreign",
        last_name="Patient",
    )

    headers = _headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    injector = FaultInjector(
        seed=900,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.CONNECTION_FAILURE,
        operation="patient_read",
        max_occurrences=1,
    )

    original_get_patient = (
        patient_route.get_patient
    )

    monkeypatch.setattr(
        patient_route,
        "get_patient",
        _raise_downstream_failure(
            injector,
            "patient_read",
            original_get_patient,
        ),
    )

    response = client.get(
        f"/api/v1/patients/{other_patient.id}",
        headers=headers,
    )

    assert response.status_code == 422

    assert injector.rules[0].occurrences == 0


def test_same_clinic_patient_read_recovers_after_dependency_failure(
    client,
    clinic,
    make_patient,
    make_authenticated_staff,
    monkeypatch,
):
    patient = make_patient(
        clinic,
        first_name="Recovery",
        last_name="Patient",
    )

    headers = _headers(
        make_authenticated_staff,
        clinic,
        Role.DOCTOR,
    )

    injector = FaultInjector(
        seed=901,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.CONNECTION_FAILURE,
        operation="patient_read",
        max_occurrences=1,
    )

    original_get_patient = (
        patient_route.get_patient
    )

    monkeypatch.setattr(
        patient_route,
        "get_patient",
        _raise_downstream_failure(
            injector,
            "patient_read",
            original_get_patient,
        ),
    )

    failed_response = client.get(
        f"/api/v1/patients/{patient.id}",
        headers=headers,
    )

    assert failed_response.status_code == 500

    failed_body = failed_response.get_json()

    assert failed_body == {
        "success": False,
        "error": "Internal server error",
    }

    assert injector.rules[0].occurrences == 1

    injector.recover(
        "postgres",
    )

    monkeypatch.setattr(
        patient_route,
        "get_patient",
        original_get_patient,
    )

    recovered_response = client.get(
        f"/api/v1/patients/{patient.id}",
        headers=headers,
    )

    assert recovered_response.status_code == 200

    data = recovered_response.get_json()["data"]

    assert data["id"] == patient.id
    assert data["clinic_id"] == clinic.id


def test_cross_clinic_patient_mutation_remains_isolated_during_dependency_failure(
    db_session,
    client,
    clinic,
    make_clinic,
    make_patient,
    make_authenticated_staff,
    monkeypatch,
):
    other_clinic = make_clinic(
        name="Tenant Mutation Other Clinic",
    )

    other_patient = make_patient(
        other_clinic,
        first_name="Protected",
        last_name="Patient",
    )

    db_session.commit()
    db_session.expire_all()

    persisted_before = db_session.get(
        Patient,
        other_patient.id,
    )

    assert persisted_before is not None

    before_active = (
        persisted_before.is_active
    )

    headers = _headers(
        make_authenticated_staff,
        clinic,
        Role.RECEPTIONIST,
    )

    injector = FaultInjector(
        seed=902,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="patient_status_write",
        max_occurrences=1,
    )

    original_set_status = (
        patient_route.set_active_status
    )

    monkeypatch.setattr(
        patient_route,
        "set_active_status",
        _raise_downstream_failure(
            injector,
            "patient_status_write",
            original_set_status,
        ),
    )

    response = client.patch(
        f"/api/v1/patients/{other_patient.id}/status",
        json={
            "is_active": not before_active,
        },
        headers=headers,
    )

    assert response.status_code == 422

    assert injector.rules[0].occurrences == 0

    db_session.expire_all()

    persisted_after = db_session.get(
        Patient,
        other_patient.id,
    )

    assert persisted_after is not None
    assert persisted_after.is_active == (
        before_active
    )