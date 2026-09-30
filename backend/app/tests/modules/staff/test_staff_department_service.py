from __future__ import annotations

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.department.models.department_model import Department
from app.modules.staff.services import staff_department_service


def make_department(
    db,
    clinic,
    *,
    name="Cardiology",
    code="CARD",
    status=DepartmentStatus.ACTIVE,
):
    department = Department(
        clinic_id=clinic.id,
        name=name,
        code=code,
        status=status,
    )

    db.session.add(department)
    db.session.flush()

    return department


def test_set_staff_department_assigns_same_clinic(
    db,
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        clinic,
    )

    result = staff_department_service.set_staff_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=department.id,
    )

    assert result.department_id == department.id


def test_set_staff_department_rejects_cross_clinic(
    db,
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        other_clinic,
    )

    with pytest.raises(NotFoundError):
        staff_department_service.set_staff_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_set_staff_department_rejects_inactive_department(
    db,
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        clinic,
        status=DepartmentStatus.INACTIVE,
    )

    with pytest.raises(ValidationError):
        staff_department_service.set_staff_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_set_staff_department_can_clear_assignment(
    db,
    clinic,
    make_staff,
):
    department = make_department(
        db,
        clinic,
    )

    staff = make_staff(
        clinic=clinic,
        department_id=department.id,
    )

    result = staff_department_service.set_staff_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=None,
    )

    assert result.department_id is None


def test_get_staff_department_is_clinic_scoped(
    db,
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    department = make_department(
        db,
        other_clinic,
        name="Emergency",
        code="ER",
    )

    staff = make_staff(
        clinic=clinic,
    )

    staff.department_id = department.id
    db.session.flush()

    with pytest.raises(NotFoundError):
        staff_department_service.get_staff_department(
            staff_id=staff.id,
            clinic_id=other_clinic.id,
        )
