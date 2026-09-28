from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.auth.user.models.user_device_model import UserDevice
from app.core.auth.user.services import user_device_service
from app.core.enums.audit_enums import AuditAction
from app.extensions import db
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


def _make_device(
    db_session,
    user_id: int,
    *,
    token: str,
    is_active: bool,
) -> UserDevice:
    device = UserDevice(
        user_id=user_id,
        device_token=token,
        platform="android",
        device_name="Resilience Device",
        is_active=is_active,
        last_seen_at=datetime.now(timezone.utc),
    )
    db_session.add(device)
    db_session.flush()
    return device


def test_duplicate_activation_is_idempotent(
    db_session,
    user,
    monkeypatch,
):
    device = _make_device(
        db_session,
        user.id,
        token="resilience-idempotent-activate",
        is_active=True,
    )

    db_session.commit()
    db_session.expire_all()

    persisted_before = db_session.get(
        UserDevice,
        device.id,
    )
    assert persisted_before is not None

    original_last_seen = persisted_before.last_seen_at
    audit = []

    def record_audit(**kwargs):
        audit.append(kwargs)

    monkeypatch.setattr(
        user_device_service,
        "create_audit_log",
        record_audit,
    )

    first = user_device_service.activate_device(
        device.id,
        user.id,
    )
    second = user_device_service.activate_device(
        device.id,
        user.id,
    )

    assert first is second
    assert first.id == device.id
    assert first.is_active is True
    assert first.last_seen_at == original_last_seen
    assert audit == []

    db_session.expire_all()

    persisted_after = db_session.get(
        UserDevice,
        device.id,
    )
    assert persisted_after is not None
    assert persisted_after.is_active is True
    assert persisted_after.last_seen_at == original_last_seen


def test_failed_deactivation_recovers_without_duplicate_transition(
    db_session,
    user,
    monkeypatch,
):
    device = _make_device(
        db_session,
        user.id,
        token="resilience-deactivate-recovery",
        is_active=True,
    )

    db_session.commit()
    db_session.expire_all()

    injector = FaultInjector(
        seed=600,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

    original_audit = user_device_service.create_audit_log

    monkeypatch.setattr(
        user_device_service,
        "create_audit_log",
        _raise_audit_failure(
            injector,
        ),
    )

    with pytest.raises(
        InjectedFault,
        match="Injected partial_failure",
    ):
        user_device_service.deactivate_device(
            device.id,
            user.id,
        )

    db_session.expire_all()

    failed_device = db_session.get(
        UserDevice,
        device.id,
    )

    assert failed_device is not None
    assert failed_device.is_active is True

    failed_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "UserDevice",
            AuditLog.entity_id == device.id,
            AuditLog.action == AuditAction.STATUS_CHANGE,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert failed_audits == []

    injector.recover(
        "postgres",
    )

    monkeypatch.setattr(
        user_device_service,
        "create_audit_log",
        original_audit,
    )

    recovered = user_device_service.deactivate_device(
        device.id,
        user.id,
    )

    assert recovered.id == device.id
    assert recovered.is_active is False

    db_session.expire_all()

    persisted_device = db_session.get(
        UserDevice,
        device.id,
    )

    assert persisted_device is not None
    assert persisted_device.is_active is False

    persisted_audits = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.entity_type == "UserDevice",
            AuditLog.entity_id == device.id,
            AuditLog.action == AuditAction.STATUS_CHANGE,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_audits) == 1
    assert persisted_audits[0].old_value == {
        "is_active": True,
    }
    assert persisted_audits[0].new_value == {
        "is_active": False,
    }