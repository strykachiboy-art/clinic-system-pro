from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.staff_department_enums import StaffDepartmentStatus
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.models.clinic_model import Clinic
from app.modules.department.models.department_model import Department
from app.modules.staff.models.staff_department_model import StaffDepartment
from app.modules.staff.models.staff_model import Staff


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(
        tzinfo=None
    )


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
    require_active: bool = False,
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

    if (
        require_active
        and staff.status != StaffStatus.ACTIVE
    ):
        raise ValidationError(
            f"Staff {staff_id} is not active"
        )

    return staff


def _get_department(
    department_id: int,
    clinic_id: int,
    *,
    lock: bool = False,
    require_active: bool = False,
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

    if (
        require_active
        and department.status != DepartmentStatus.ACTIVE
    ):
        raise ValidationError(
            f"Department {department_id} is not active"
        )

    return department


def _get_active_memberships(
    staff_id: int,
    clinic_id: int,
    *,
    lock: bool = False,
) -> list[StaffDepartment]:
    statement = (
        select(StaffDepartment)
        .where(
            StaffDepartment.staff_id == staff_id,
            StaffDepartment.clinic_id == clinic_id,
            StaffDepartment.status
            == StaffDepartmentStatus.ACTIVE,
        )
        .order_by(
            StaffDepartment.assigned_at.asc(),
            StaffDepartment.id.asc(),
        )
    )

    if lock:
        statement = statement.with_for_update()

    return list(
        db.session.execute(statement).scalars()
    )


def _set_primary_membership(
    membership: StaffDepartment,
    active_memberships: list[StaffDepartment],
) -> None:
    for item in active_memberships:
        item.is_primary = (
            item.id == membership.id
        )

    membership.is_primary = True


def _ensure_primary_membership(
    active_memberships: list[StaffDepartment],
) -> StaffDepartment | None:
    if not active_memberships:
        return None

    primary = next(
        (
            item
            for item in active_memberships
            if item.is_primary
        ),
        None,
    )

    if primary is not None:
        return primary

    primary = active_memberships[0]

    for item in active_memberships:
        item.is_primary = (
            item.id == primary.id
        )

    return primary


@transactional
def assign_staff_to_department(
    staff_id: int,
    clinic_id: int,
    department_id: int,
    *,
    is_primary: bool = False,
) -> StaffDepartment:
    clinic = _get_active_clinic(
        clinic_id
    )

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic.id,
        lock=True,
        require_active=True,
    )

    department = _get_department(
        department_id=department_id,
        clinic_id=clinic.id,
        lock=True,
        require_active=True,
    )

    active_memberships = _get_active_memberships(
        staff_id=staff.id,
        clinic_id=clinic.id,
        lock=True,
    )

    existing = next(
        (
            item
            for item in active_memberships
            if item.department_id == department.id
        ),
        None,
    )

    if existing is not None:
        raise ConflictError(
            "Staff is already actively assigned "
            "to this department"
        )

    membership = StaffDepartment(
        clinic_id=clinic.id,
        staff_id=staff.id,
        department_id=department.id,
        is_primary=(
            is_primary
            or not active_memberships
        ),
        status=StaffDepartmentStatus.ACTIVE,
        assigned_at=_utcnow(),
    )

    db.session.add(membership)
    db.session.flush()

    if membership.is_primary:
        active_memberships.append(
            membership
        )
        _set_primary_membership(
            membership,
            active_memberships,
        )

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="StaffDepartment",
        entity_id=membership.id,
        clinic_id=clinic.id,
        description=(
            f"Staff {staff.id} assigned to "
            f"department '{department.name}'"
        ),
        old_value=None,
        new_value={
            "staff_id": staff.id,
            "department_id": department.id,
            "is_primary": membership.is_primary,
            "status": membership.status.value,
        },
    )

    return membership


@transactional
def remove_staff_from_department(
    staff_id: int,
    clinic_id: int,
    department_id: int,
) -> StaffDepartment:
    clinic = _get_active_clinic(
        clinic_id
    )

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic.id,
        lock=True,
    )

    department = _get_department(
        department_id=department_id,
        clinic_id=clinic.id,
        lock=True,
        require_active=False,
    )

    active_memberships = _get_active_memberships(
        staff_id=staff.id,
        clinic_id=clinic.id,
        lock=True,
    )

    membership = next(
        (
            item
            for item in active_memberships
            if item.department_id == department.id
        ),
        None,
    )

    if membership is None:
        raise NotFoundError(
            f"Active membership for staff {staff.id} "
            f"and department {department.id} not found"
        )

    was_primary = membership.is_primary

    membership.status = StaffDepartmentStatus.ENDED
    membership.is_primary = False
    membership.ended_at = _utcnow()
    membership.updated_at = _utcnow()

    if was_primary:
        remaining = [
            item
            for item in active_memberships
            if item.id != membership.id
        ]

        _ensure_primary_membership(
            remaining
        )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="StaffDepartment",
        entity_id=membership.id,
        clinic_id=clinic.id,
        description=(
            f"Staff {staff.id} membership ended "
            f"for department '{department.name}'"
        ),
        old_value={
            "status": StaffDepartmentStatus.ACTIVE.value,
            "is_primary": was_primary,
            "ended_at": None,
        },
        new_value={
            "status": membership.status.value,
            "is_primary": False,
            "ended_at": membership.ended_at.isoformat(),
        },
    )

    return membership


@transactional
def set_primary_department(
    staff_id: int,
    clinic_id: int,
    department_id: int,
) -> StaffDepartment:
    clinic = _get_active_clinic(
        clinic_id
    )

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic.id,
        lock=True,
        require_active=True,
    )

    department = _get_department(
        department_id=department_id,
        clinic_id=clinic.id,
        lock=True,
        require_active=True,
    )

    active_memberships = _get_active_memberships(
        staff_id=staff.id,
        clinic_id=clinic.id,
        lock=True,
    )

    membership = next(
        (
            item
            for item in active_memberships
            if item.department_id == department.id
        ),
        None,
    )

    if membership is None:
        raise NotFoundError(
            f"Active membership for staff {staff.id} "
            f"and department {department.id} not found"
        )

    old_primary = next(
        (
            item
            for item in active_memberships
            if item.is_primary
        ),
        None,
    )

    if old_primary is not None:
        for item in active_memberships:
            item.is_primary = (
                item.id == membership.id
            )
    else:
        _set_primary_membership(
            membership,
            active_memberships,
        )

    if (
        old_primary is not None
        and old_primary.id == membership.id
    ):
        return membership

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="StaffDepartment",
        entity_id=membership.id,
        clinic_id=clinic.id,
        description=(
            f"Staff {staff.id} primary department changed "
            f"to '{department.name}'"
        ),
        old_value={
            "primary_department_id": (
                old_primary.department_id
                if old_primary is not None
                else None
            ),
        },
        new_value={
            "primary_department_id": department.id,
        },
    )

    return membership


def get_staff_departments(
    staff_id: int,
    clinic_id: int,
    *,
    include_ended: bool = False,
) -> list[StaffDepartment]:
    _get_active_clinic(
        clinic_id
    )

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
    )

    statement = (
        select(StaffDepartment)
        .where(
            StaffDepartment.staff_id == staff.id,
            StaffDepartment.clinic_id == clinic_id,
        )
        .order_by(
            StaffDepartment.is_primary.desc(),
            StaffDepartment.status.asc(),
            StaffDepartment.assigned_at.asc(),
            StaffDepartment.id.asc(),
        )
    )

    if not include_ended:
        statement = statement.where(
            StaffDepartment.status
            != StaffDepartmentStatus.ENDED
        )

    return list(
        db.session.execute(statement).scalars()
    )


def list_department_staff(
    department_id: int,
    clinic_id: int,
    *,
    include_ended: bool = False,
) -> list[StaffDepartment]:
    _get_active_clinic(
        clinic_id
    )

    department = _get_department(
        department_id=department_id,
        clinic_id=clinic_id,
    )

    statement = (
        select(StaffDepartment)
        .where(
            StaffDepartment.department_id
            == department.id,
            StaffDepartment.clinic_id
            == clinic_id,
        )
        .order_by(
            StaffDepartment.status.asc(),
            StaffDepartment.is_primary.desc(),
            StaffDepartment.assigned_at.asc(),
            StaffDepartment.id.asc(),
        )
    )

    if not include_ended:
        statement = statement.where(
            StaffDepartment.status
            != StaffDepartmentStatus.ENDED
        )

    return list(
        db.session.execute(statement).scalars()
    )
