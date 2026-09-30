from __future__ import annotations

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.clinic_enums import ClinicStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.department.models.department_model import Department
from app.modules.department.services import department_service


def test_create_department_normalizes_values(
    clinic,
):
    department = department_service.create_department(
        clinic_id=clinic.id,
        code="  cardio  ",
        name="  Cardiology  ",
        description="  Heart care  ",
    )

    assert department.code == "CARDIO"
    assert department.name == "Cardiology"
    assert department.description == "Heart care"
    assert department.status == DepartmentStatus.ACTIVE


def test_create_department_rejects_duplicate_code_in_same_clinic(
    clinic,
):
    department_service.create_department(
        clinic_id=clinic.id,
        code="CARD",
        name="Cardiology",
    )

    with pytest.raises(ConflictError):
        department_service.create_department(
            clinic_id=clinic.id,
            code="card",
            name="Cardio",
        )


def test_same_department_code_allowed_in_different_clinics(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    first = department_service.create_department(
        clinic_id=clinic.id,
        code="ER",
        name="Emergency",
    )

    second = department_service.create_department(
        clinic_id=other_clinic.id,
        code="ER",
        name="Emergency",
    )

    assert first.id != second.id
    assert first.clinic_id == clinic.id
    assert second.clinic_id == other_clinic.id


def test_get_department_enforces_clinic_isolation(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    department = department_service.create_department(
        clinic_id=other_clinic.id,
        code="CARD",
        name="Cardiology",
    )

    with pytest.raises(NotFoundError):
        department_service.get_department(
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_list_departments_filters_and_orders(
    clinic,
):
    emergency = department_service.create_department(
        clinic_id=clinic.id,
        code="ER",
        name="Emergency",
    )

    cardiology = department_service.create_department(
        clinic_id=clinic.id,
        code="CARD",
        name="Cardiology",
    )

    department_service.change_department_status(
        clinic_id=clinic.id,
        department_id=emergency.id,
        new_status=DepartmentStatus.INACTIVE,
    )

    result = department_service.list_departments(
        clinic_id=clinic.id,
        status=DepartmentStatus.INACTIVE,
    )

    assert [item.id for item in result] == [emergency.id]

    search_result = department_service.list_departments(
        clinic_id=clinic.id,
        search="card",
    )

    assert [item.id for item in search_result] == [cardiology.id]


def test_update_department_rejects_duplicate_name(
    clinic,
):
    first = department_service.create_department(
        clinic_id=clinic.id,
        code="CARD",
        name="Cardiology",
    )

    second = department_service.create_department(
        clinic_id=clinic.id,
        code="ER",
        name="Emergency",
    )

    with pytest.raises(ConflictError):
        department_service.update_department(
            clinic_id=clinic.id,
            department_id=second.id,
            name=first.name,
        )


def test_change_department_status_updates_status(
    clinic,
):
    department = department_service.create_department(
        clinic_id=clinic.id,
        code="LAB",
        name="Laboratory",
    )

    result = department_service.change_department_status(
        clinic_id=clinic.id,
        department_id=department.id,
        new_status=DepartmentStatus.SUSPENDED,
    )

    assert result.status == DepartmentStatus.SUSPENDED


def test_create_department_rejects_inactive_clinic(
    make_clinic,
):
    clinic = make_clinic(
        status=ClinicStatus.SUSPENDED,
    )

    with pytest.raises(ValidationError):
        department_service.create_department(
            clinic_id=clinic.id,
            code="ER",
            name="Emergency",
        )
