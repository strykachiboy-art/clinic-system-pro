from __future__ import annotations

from sqlalchemy import select

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.department_enums import DepartmentStatus
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.models.clinic_model import Clinic
from app.modules.department.models.department_model import Department
from app.modules.staff.models.staff_model import Staff


def _validate_positive_id(
    value,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _get_active_clinic(
    clinic_id: int,
) -> Clinic:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic


def _get_staff(
    staff_id: int,
    clinic_id: int,
    *,
    lock: bool = False,
) -> Staff:
    staff_id = _validate_positive_id(
        staff_id,
        "staff_id",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    statement = select(Staff).where(
        Staff.id == staff_id,
        Staff.clinic_id == clinic_id,
    )

    if lock:
        statement = statement.with_for_update()

    staff = db.session.execute(
        statement
    ).scalar_one_or_none()

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def _get_department(
    department_id: int,
    clinic_id: int,
    *,
    lock: bool = False,
) -> Department:
    department_id = _validate_positive_id(
        department_id,
        "department_id",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    statement = select(Department).where(
        Department.id == department_id,
        Department.clinic_id == clinic_id,
    )

    if lock:
        statement = statement.with_for_update()

    department = db.session.execute(
        statement
    ).scalar_one_or_none()

    if department is None:
        raise NotFoundError(
            f"Department {department_id} not found"
        )

    if department.status != DepartmentStatus.ACTIVE:
        raise ValidationError(
            f"Department {department_id} is not active"
        )

    return department


@transactional
def set_staff_department(
    staff_id: int,
    clinic_id: int,
    department_id: int | None,
) -> Staff:
    clinic = _get_active_clinic(
        clinic_id
    )

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic.id,
        lock=True,
    )

    if department_id is None:
        if staff.department_id is None:
            return staff

        old_department_id = staff.department_id
        staff.department_id = None

        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Staff",
            entity_id=staff.id,
            clinic_id=clinic.id,
            description=(
                f"Staff {staff.id} department cleared"
            ),
            old_value={
                "department_id": old_department_id,
            },
            new_value={
                "department_id": None,
            },
        )

        return staff

    department = _get_department(
        department_id=department_id,
        clinic_id=clinic.id,
        lock=True,
    )

    if staff.department_id == department.id:
        return staff

    old_department_id = staff.department_id
    staff.department_id = department.id

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Staff",
        entity_id=staff.id,
        clinic_id=clinic.id,
        description=(
            f"Staff {staff.id} assigned to "
            f"department '{department.name}'"
        ),
        old_value={
            "department_id": old_department_id,
        },
        new_value={
            "department_id": department.id,
        },
    )

    return staff


def get_staff_department(
    staff_id: int,
    clinic_id: int,
) -> Department | None:
    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
    )

    if staff.department_id is None:
        return None

    return db.session.get(
        Department,
        staff.department_id,
    )
