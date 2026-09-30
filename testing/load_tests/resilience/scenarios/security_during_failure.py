from __future__ import annotations

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.auth.user.models.user_model import User
from app.extensions import db
from app.modules.access_control.services import (
    access_control_service,
)
from load_tests.resilience.common.faults import (
    FaultInjector,
    FaultType,
    InjectedFault,
)


def _raise_audit_failure(
    injector: FaultInjector,
):
    def _audit_failure(**kwargs):
        injector.inject(
            "postgres",
            operation="audit_write",
        )

    return _audit_failure


def test_failed_privileged_role_change_fails_closed(
    db_session,
    clinic,
    make_user,
    monkeypatch,
):
    super_admin = make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        email="resilience-super-admin@test.com",
    )

    target = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        email="resilience-role-target@test.com",
    )

    db_session.commit()
    db_session.expire_all()

    persisted_target = db_session.get(
        User,
        target.id,
    )

    assert persisted_target is not None
    assert persisted_target.role is Role.DOCTOR

    original_token_version = (
        persisted_target.token_version
    )

    before_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "User",
            AuditLog.entity_id == target.id,
            AuditLog.action == AuditAction.UPDATE,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    injector = FaultInjector(
        seed=800,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

    monkeypatch.setattr(
        access_control_service,
        "create_audit_log",
        _raise_audit_failure(
            injector,
        ),
    )

    with pytest.raises(
        InjectedFault,
        match="Injected partial_failure",
    ):
        access_control_service.change_user_role(
            actor_id=super_admin.id,
            user_id=target.id,
            new_role=Role.NURSE,
            reason="Synthetic resilience failure",
        )

    db_session.expire_all()

    failed_target = db_session.get(
        User,
        target.id,
    )

    assert failed_target is not None
    assert failed_target.role is Role.DOCTOR
    assert failed_target.token_version == (
        original_token_version
    )

    failed_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "User",
            AuditLog.entity_id == target.id,
            AuditLog.action == AuditAction.UPDATE,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert failed_audits == before_audits


def test_authorization_recovers_without_partial_role_change(
    db_session,
    clinic,
    make_user,
    monkeypatch,
):
    super_admin = make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        email="resilience-recovery-super-admin@test.com",
    )

    target = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        email="resilience-recovery-target@test.com",
    )

    db_session.commit()
    db_session.expire_all()

    injector = FaultInjector(
        seed=801,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

    original_audit = (
        access_control_service.create_audit_log
    )

    monkeypatch.setattr(
        access_control_service,
        "create_audit_log",
        _raise_audit_failure(
            injector,
        ),
    )

    with pytest.raises(
        InjectedFault,
        match="Injected partial_failure",
    ):
        access_control_service.change_user_role(
            actor_id=super_admin.id,
            user_id=target.id,
            new_role=Role.NURSE,
            reason="Synthetic recovery failure",
        )

    db_session.expire_all()

    failed_target = db_session.get(
        User,
        target.id,
    )

    assert failed_target is not None
    assert failed_target.role is Role.DOCTOR

    injector.recover(
        "postgres",
    )

    monkeypatch.setattr(
        access_control_service,
        "create_audit_log",
        original_audit,
    )

    recovered = (
        access_control_service.change_user_role(
            actor_id=super_admin.id,
            user_id=target.id,
            new_role=Role.NURSE,
            reason="Recovered authorization transition",
        )
    )

    assert recovered.user.id == target.id
    assert recovered.previous_role is Role.DOCTOR
    assert recovered.new_role is Role.NURSE

    db_session.expire_all()

    persisted_target = db_session.get(
        User,
        target.id,
    )

    assert persisted_target is not None
    assert persisted_target.role is Role.NURSE

    persisted_audits = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.entity_type == "User",
            AuditLog.entity_id == target.id,
            AuditLog.action == AuditAction.UPDATE,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_audits) == 1

    assert persisted_audits[0].old_value["role"] == (
        Role.DOCTOR.value
    )

    assert persisted_audits[0].new_value["role"] == (
        Role.NURSE.value
    )


def test_non_super_admin_cannot_bypass_authorization_after_failure(
    db_session,
    clinic,
    make_user,
):
    actor = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        email="resilience-unauthorized-actor@test.com",
    )

    target = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        email="resilience-unauthorized-target@test.com",
    )

    db_session.commit()
    db_session.expire_all()

    with pytest.raises(
        ValidationError,
        match=(
            "Only a super administrator can "
            "access access-control administration"
        ),
    ):
        access_control_service.change_user_role(
            actor_id=actor.id,
            user_id=target.id,
            new_role=Role.NURSE,
            reason="Unauthorized resilience attempt",
        )

    db_session.expire_all()

    persisted_target = db_session.get(
        User,
        target.id,
    )

    assert persisted_target is not None
    assert persisted_target.role is Role.DOCTOR