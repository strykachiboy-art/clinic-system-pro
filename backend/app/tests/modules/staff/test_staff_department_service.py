from __future__ import annotations

from sqlalchemy.exc import IntegrityError

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.staff_department_enums import StaffDepartmentStatus
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.department.models.department_model import Department
from app.modules.staff.models.staff_department_model import StaffDepartment
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


def test_assign_staff_to_department_creates_primary_membership(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    department = make_department(
        db,
        clinic,
    )

    membership = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )
    )

    assert membership.id is not None
    assert membership.clinic_id == clinic.id
    assert membership.staff_id == staff.id
    assert membership.department_id == department.id
    assert membership.status == StaffDepartmentStatus.ACTIVE
    assert membership.is_primary is True
    assert membership.assigned_at is not None
    assert membership.ended_at is None


def test_assign_staff_to_multiple_departments(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    cardiology = make_department(
        db,
        clinic,
        name="Cardiology",
        code="CARD",
    )

    emergency = make_department(
        db,
        clinic,
        name="Emergency",
        code="ER",
    )

    first = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=cardiology.id,
        )
    )

    second = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=emergency.id,
        )
    )

    assert first.is_primary is True
    assert second.is_primary is False

    memberships = (
        staff_department_service.get_staff_departments(
            staff_id=staff.id,
            clinic_id=clinic.id,
        )
    )

    assert [
        item.department_id
        for item in memberships
    ] == [
        cardiology.id,
        emergency.id,
    ]


def test_assign_staff_to_department_rejects_duplicate_active_membership(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    department = make_department(
        db,
        clinic,
    )

    staff_department_service.assign_staff_to_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=department.id,
    )

    with pytest.raises(ConflictError):
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_assign_staff_to_department_rejects_cross_clinic_department(
    clinic,
    make_clinic,
    make_staff,
    db,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        other_clinic,
        name="Emergency",
        code="ER",
    )

    with pytest.raises(NotFoundError):
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_assign_staff_to_department_rejects_inactive_staff(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.SUSPENDED,
    )

    department = make_department(
        db,
        clinic,
    )

    with pytest.raises(ValidationError):
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_assign_staff_to_department_rejects_inactive_department(
    clinic,
    make_staff,
    db,
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
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_set_primary_department_switches_primary(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    cardiology = make_department(
        db,
        clinic,
        name="Cardiology",
        code="CARD",
    )

    emergency = make_department(
        db,
        clinic,
        name="Emergency",
        code="ER",
    )

    first = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=cardiology.id,
        )
    )

    second = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=emergency.id,
        )
    )

    result = (
        staff_department_service.set_primary_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=emergency.id,
        )
    )

    db.session.expire_all()

    assert result.id == second.id
    assert result.is_primary is True

    refreshed_first = db.session.get(
        StaffDepartment,
        first.id,
    )

    refreshed_second = db.session.get(
        StaffDepartment,
        second.id,
    )

    assert refreshed_first.is_primary is False
    assert refreshed_second.is_primary is True


def test_set_primary_department_rejects_unassigned_department(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    department = make_department(
        db,
        clinic,
    )

    with pytest.raises(NotFoundError):
        staff_department_service.set_primary_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )


def test_remove_staff_from_department_ends_membership(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    department = make_department(
        db,
        clinic,
    )

    membership = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )
    )

    result = (
        staff_department_service.remove_staff_from_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )
    )

    assert result.id == membership.id
    assert result.status == StaffDepartmentStatus.ENDED
    assert result.is_primary is False
    assert result.ended_at is not None


def test_remove_primary_promotes_remaining_membership(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    first_department = make_department(
        db,
        clinic,
        name="Cardiology",
        code="CARD",
    )

    second_department = make_department(
        db,
        clinic,
        name="Emergency",
        code="ER",
    )

    first = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=first_department.id,
        )
    )

    second = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=second_department.id,
        )
    )

    staff_department_service.remove_staff_from_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=first_department.id,
    )

    db.session.expire_all()

    remaining = db.session.get(
        StaffDepartment,
        second.id,
    )

    ended = db.session.get(
        StaffDepartment,
        first.id,
    )

    assert ended.status == StaffDepartmentStatus.ENDED
    assert ended.is_primary is False
    assert remaining.status == StaffDepartmentStatus.ACTIVE
    assert remaining.is_primary is True


def test_get_staff_departments_excludes_ended_by_default(
    clinic,
    make_staff,
    db,
):
    staff = make_staff(clinic=clinic)

    department = make_department(
        db,
        clinic,
    )

    staff_department_service.assign_staff_to_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=department.id,
    )

    staff_department_service.remove_staff_from_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=department.id,
    )

    active_only = (
        staff_department_service.get_staff_departments(
            staff_id=staff.id,
            clinic_id=clinic.id,
        )
    )

    with_ended = (
        staff_department_service.get_staff_departments(
            staff_id=staff.id,
            clinic_id=clinic.id,
            include_ended=True,
        )
    )

    assert active_only == []
    assert len(with_ended) == 1
    assert (
        with_ended[0].status
        == StaffDepartmentStatus.ENDED
    )


def test_list_department_staff_is_clinic_scoped(
    clinic,
    make_clinic,
    make_staff,
    db,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
    )

    other_staff = make_staff(
        clinic=other_clinic,
    )

    department = make_department(
        db,
        clinic,
    )

    other_department = make_department(
        db,
        other_clinic,
        name="Emergency",
        code="ER",
    )

    staff_department_service.assign_staff_to_department(
        staff_id=staff.id,
        clinic_id=clinic.id,
        department_id=department.id,
    )

    staff_department_service.assign_staff_to_department(
        staff_id=other_staff.id,
        clinic_id=other_clinic.id,
        department_id=other_department.id,
    )

    result = staff_department_service.list_department_staff(
        department_id=department.id,
        clinic_id=clinic.id,
    )

    assert len(result) == 1
    assert result[0].staff_id == staff.id
    assert result[0].department_id == department.id


def test_database_rejects_cross_clinic_membership(
    clinic,
    make_clinic,
    make_staff,
    db,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        other_clinic,
    )

    membership = StaffDepartment(
        clinic_id=clinic.id,
        staff_id=staff.id,
        department_id=department.id,
        is_primary=True,
        status=StaffDepartmentStatus.ACTIVE,
    )

    db.session.add(membership)

    with pytest.raises(IntegrityError):
        db.session.flush()

    db.session.rollback()


def test_assign_creates_audit_record(
    clinic,
    make_staff,
    db,
):
    from app.core.audit.models.audit_model import AuditLog

    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        clinic,
    )

    membership = (
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )
    )

    audit = db.session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.clinic_id == clinic.id,
            AuditLog.entity_type == "StaffDepartment",
            AuditLog.entity_id == membership.id,
        )
        .order_by(
            AuditLog.id.desc()
        )
    ).scalars().first()

    assert audit is not None
    assert audit.action.value == "create"
    assert audit.new_value["staff_id"] == staff.id
    assert (
        audit.new_value["department_id"]
        == department.id
    )


def test_assignment_rolls_back_on_audit_failure(
    clinic,
    make_staff,
    db,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
    )

    department = make_department(
        db,
        clinic,
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError(
            "forced audit failure"
        )

    monkeypatch.setattr(
        staff_department_service,
        "create_audit_log",
        fail_audit,
    )

    with pytest.raises(RuntimeError):
        staff_department_service.assign_staff_to_department(
            staff_id=staff.id,
            clinic_id=clinic.id,
            department_id=department.id,
        )

    memberships = db.session.execute(
        db.select(StaffDepartment).where(
            StaffDepartment.clinic_id == clinic.id,
            StaffDepartment.staff_id == staff.id,
            StaffDepartment.department_id == department.id,
        )
    ).scalars().all()

    assert memberships == []
