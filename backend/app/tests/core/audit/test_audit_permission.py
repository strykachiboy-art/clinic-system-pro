import pytest

from app.core.audit.security.audit_permissions import (
    can_access_audit_scope,
    can_read_audit_logs,
)
from app.core.enums.role_enums import Role


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PATIENT,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.RECEPTIONIST,
        Role.ACCOUNTANT,
        Role.PARAMEDIC,
        Role.EMT,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.OTHER,
    ],
)
def test_non_admin_roles_cannot_read_audit_logs(
    role,
):
    assert (
        can_read_audit_logs(
            actor_role=role,
            actor_clinic_id=1,
            target_clinic_id=1,
        )
        is False
    )


def test_admin_can_read_same_clinic_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            target_clinic_id=1,
        )
        is True
    )


def test_admin_cannot_read_different_clinic_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            target_clinic_id=2,
        )
        is False
    )


def test_admin_cannot_read_global_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            target_clinic_id=None,
        )
        is False
    )


def test_admin_without_clinic_cannot_read_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.ADMIN,
            actor_clinic_id=None,
            target_clinic_id=1,
        )
        is False
    )


def test_super_admin_can_read_same_clinic_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=1,
            target_clinic_id=1,
        )
        is True
    )


def test_super_admin_can_read_different_clinic_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=1,
            target_clinic_id=2,
        )
        is True
    )


def test_super_admin_can_read_global_audit():
    assert (
        can_read_audit_logs(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=None,
            target_clinic_id=None,
        )
        is True
    )


def test_string_admin_role_is_supported():
    assert (
        can_read_audit_logs(
            actor_role=Role.ADMIN.value,
            actor_clinic_id=1,
            target_clinic_id=1,
        )
        is True
    )


def test_invalid_role_is_denied():
    assert (
        can_read_audit_logs(
            actor_role="not-a-role",
            actor_clinic_id=1,
            target_clinic_id=1,
        )
        is False
    )


def test_admin_can_access_implicit_own_scope():
    assert (
        can_access_audit_scope(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            requested_clinic_id=None,
        )
        is True
    )


def test_admin_can_access_explicit_own_scope():
    assert (
        can_access_audit_scope(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            requested_clinic_id=1,
        )
        is True
    )


def test_admin_cannot_select_another_clinic():
    assert (
        can_access_audit_scope(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            requested_clinic_id=2,
        )
        is False
    )


def test_admin_without_clinic_cannot_access_scope():
    assert (
        can_access_audit_scope(
            actor_role=Role.ADMIN,
            actor_clinic_id=None,
            requested_clinic_id=None,
        )
        is False
    )


def test_super_admin_can_select_another_clinic():
    assert (
        can_access_audit_scope(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=1,
            requested_clinic_id=2,
        )
        is True
    )


def test_super_admin_can_access_global_scope():
    assert (
        can_access_audit_scope(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=None,
            requested_clinic_id=None,
        )
        is True
    )