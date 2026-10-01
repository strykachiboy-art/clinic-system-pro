from __future__ import annotations

import pytest

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.role_enums import Role
from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardChatSummarySchema,
)
from app.modules.dashboard.services import (
    clinical_dashboard_service,
    management_dashboard_service,
    operations_dashboard_service,
    super_admin_dashboard_service,
)
from app.modules.dashboard.services.clinical_dashboard_service import (
    get_clinical_dashboard,
)
from app.modules.dashboard.services.management_dashboard_service import (
    get_management_dashboard,
)
from app.modules.dashboard.services.operations_dashboard_service import (
    get_operations_dashboard,
)
from app.modules.dashboard.services.super_admin_dashboard_service import (
    get_super_admin_dashboard,
)
from app.modules.department.models.department_model import Department
from app.modules.staff.services.staff_department_service import (
    assign_staff_to_department,
    remove_staff_from_department,
)


@pytest.fixture
def dashboard_helpers(monkeypatch):
    chat = DashboardChatSummarySchema(
        unread_messages=0,
        unread_conversations=0,
        mentions=0,
        priority_messages=0,
        recent_messages=0,
    )

    activity = []

    for service in (
        management_dashboard_service,
        clinical_dashboard_service,
        operations_dashboard_service,
    ):
        monkeypatch.setattr(
            service,
            "build_chat_summary",
            lambda **_: chat,
        )
        monkeypatch.setattr(
            service,
            "build_recent_activity",
            lambda **_: activity,
        )

    monkeypatch.setattr(
        super_admin_dashboard_service,
        "build_recent_activity",
        lambda **_: activity,
    )

    return chat


def _make_department(
    db_session,
    clinic,
    *,
    code,
    name,
    status=DepartmentStatus.ACTIVE,
):
    department = Department(
        clinic_id=clinic.id,
        code=code,
        name=name,
        status=status,
    )
    db_session.add(department)
    db_session.flush()
    return department


def test_management_dashboard_displays_department_staffing(
    clinic,
    make_clinic,
    make_staff,
    make_user,
    db_session,
    dashboard_helpers,
):
    admin = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    cardiology = _make_department(
        db_session,
        clinic,
        code="CARD",
        name="Cardiology",
    )

    _make_department(
        db_session,
        clinic,
        code="ER",
        name="Emergency",
        status=DepartmentStatus.INACTIVE,
    )

    _make_department(
        db_session,
        clinic,
        code="RAD",
        name="Radiology",
        status=DepartmentStatus.SUSPENDED,
    )

    staff_one = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    staff_two = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    assign_staff_to_department(
        staff_one.id,
        clinic.id,
        cardiology.id,
    )

    assign_staff_to_department(
        staff_two.id,
        clinic.id,
        cardiology.id,
    )

    other_clinic = make_clinic()

    other_department = _make_department(
        db_session,
        other_clinic,
        code="OTHER",
        name="Other Clinic",
    )

    other_staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    assign_staff_to_department(
        other_staff.id,
        other_clinic.id,
        other_department.id,
    )

    result = get_management_dashboard(
        actor=admin,
    )

    assert result.departments.total_departments == 3
    assert result.departments.active_departments == 1
    assert result.departments.inactive_departments == 1
    assert result.departments.suspended_departments == 1

    summary = next(
        item
        for item in result.departments.departments
        if item.id == cardiology.id
    )

    assert summary.code == "CARD"
    assert summary.name == "Cardiology"
    assert summary.status is DepartmentStatus.ACTIVE
    assert summary.active_staff_count == 2
    assert summary.primary_staff_count == 2

    assert all(
        item.id != other_department.id
        for item in result.departments.departments
    )


def test_clinical_dashboard_displays_my_staff_departments(
    clinic,
    make_staff,
    db_session,
    dashboard_helpers,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    primary = _make_department(
        db_session,
        clinic,
        code="ER",
        name="Emergency",
    )

    secondary = _make_department(
        db_session,
        clinic,
        code="TRM",
        name="Trauma",
    )

    ended = _make_department(
        db_session,
        clinic,
        code="OLD",
        name="Old Unit",
    )

    assign_staff_to_department(
        staff.id,
        clinic.id,
        primary.id,
    )

    assign_staff_to_department(
        staff.id,
        clinic.id,
        secondary.id,
    )

    ended_membership = assign_staff_to_department(
        staff.id,
        clinic.id,
        ended.id,
    )

    remove_staff_from_department(
        staff.id,
        clinic.id,
        ended_membership.department_id,
    )

    result = get_clinical_dashboard(
        actor=staff.user,
    )

    assert [
        item.department_id
        for item in result.my_departments
    ] == [
        primary.id,
        secondary.id,
    ]

    assert result.my_departments[0].is_primary is True
    assert result.my_departments[1].is_primary is False

    assert all(
        item.department_id != ended.id
        for item in result.my_departments
    )


def test_operations_dashboard_displays_department_coverage(
    clinic,
    make_user,
    make_staff,
    db_session,
    dashboard_helpers,
):
    actor = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
    )

    active_department = _make_department(
        db_session,
        clinic,
        code="ER",
        name="Emergency",
    )

    _make_department(
        db_session,
        clinic,
        code="LAB",
        name="Laboratory",
        status=DepartmentStatus.INACTIVE,
    )

    assigned = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    assign_staff_to_department(
        assigned.id,
        clinic.id,
        active_department.id,
    )

    result = get_operations_dashboard(
        actor=actor,
    )

    assert result.overview.active_departments == 1
    assert result.overview.unassigned_active_staff == 1


def test_super_admin_dashboard_displays_departments_by_clinic(
    make_user,
    clinic,
    make_clinic,
    db_session,
    dashboard_helpers,
):
    super_admin = make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
    )

    _make_department(
        db_session,
        clinic,
        code="CARD",
        name="Cardiology",
        status=DepartmentStatus.INACTIVE,
    )

    _make_department(
        db_session,
        clinic,
        code="RAD",
        name="Radiology",
        status=DepartmentStatus.SUSPENDED,
    )
    other_clinic = make_clinic()

    _make_department(
        db_session,
        other_clinic,
        code="LAB",
        name="Laboratory",
    )

    result = get_super_admin_dashboard(
        actor=super_admin,
    )

    assert result.departments.total_departments == 3
    assert result.departments.active_departments == 1

    clinic_summary = next(
        item
        for item in result.departments.by_clinic
        if item.clinic_id == clinic.id
    )

    other_summary = next(
        item
        for item in result.departments.by_clinic
        if item.clinic_id == other_clinic.id
    )

    assert clinic_summary.total_departments == 2
    assert clinic_summary.active_departments == 0
    assert other_summary.total_departments == 1
    assert other_summary.active_departments == 1

