import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.services.audit_writer import write_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import ValidationError


def test_write_audit_log_creates_record(
    db_session,
    user,
    clinic,
):
    log = write_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="Patient created",
        user_id=user.id,
        clinic_id=clinic.id,
        new_value={"status": "active"},
        ip_address="127.0.0.1",
    )

    db_session.flush()

    assert isinstance(log, AuditLog)
    assert log.id is not None
    assert log.user_id == user.id
    assert log.clinic_id == clinic.id
    assert log.action == AuditAction.CREATE
    assert log.entity_type == "Patient"
    assert log.entity_id == 100
    assert log.description == "Patient created"
    assert log.new_value == {"status": "active"}
    assert log.ip_address == "127.0.0.1"


def test_write_audit_log_derives_clinic_from_user(
    db_session,
    user,
    clinic,
):
    log = write_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        user_id=user.id,
        new_value={"status": "active"},
    )

    db_session.flush()

    assert log.clinic_id == clinic.id


def test_write_audit_log_allows_system_event(
    db_session,
):
    log = write_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="System",
        entity_id=1,
        description="System status changed",
    )

    db_session.flush()

    assert log.user_id is None
    assert log.clinic_id is None


def test_write_audit_log_rejects_clinic_mismatch(
    user,
    make_clinic,
):
    other_clinic = make_clinic()

    with pytest.raises(
        ValidationError,
        match="Audit clinic does not match the audit actor",
    ):
        write_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=100,
            user_id=user.id,
            clinic_id=other_clinic.id,
        )


@pytest.mark.parametrize(
    "clinic_id",
    [
        0,
        -1,
        True,
        False,
        "1",
    ],
)
def test_write_audit_log_rejects_invalid_clinic_id(
    clinic_id,
):
    with pytest.raises(
        ValidationError,
        match="Clinic ID must be a positive integer",
    ):
        write_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            clinic_id=clinic_id,
        )


@pytest.mark.parametrize(
    "user_id",
    [
        0,
        -1,
        True,
        False,
        "1",
    ],
)
def test_write_audit_log_rejects_invalid_user_id(
    user_id,
):
    with pytest.raises(
        ValidationError,
        match="User ID must be a positive integer",
    ):
        write_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            user_id=user_id,
        )


@pytest.mark.parametrize(
    "entity_id",
    [
        0,
        -1,
        True,
        False,
        "100",
    ],
)
def test_write_audit_log_rejects_invalid_entity_id(
    entity_id,
):
    with pytest.raises(
        ValidationError,
        match="Audit entity ID must be a positive integer",
    ):
        write_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=entity_id,
        )


def test_write_audit_log_redacts_old_and_new_values(
    db_session,
    user,
    clinic,
):
    log = write_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=user.id,
        user_id=user.id,
        clinic_id=clinic.id,
        old_value={
            "password": "old-secret",
            "status": "active",
        },
        new_value={
            "password": "new-secret",
            "access_token": "secret-token",
            "status": "disabled",
        },
    )

    db_session.flush()

    assert log.old_value == {
        "password": "[REDACTED]",
        "status": "active",
    }

    assert log.new_value == {
        "password": "[REDACTED]",
        "access_token": "[REDACTED]",
        "status": "disabled",
    }


def test_write_audit_log_does_not_commit(
    db_session,
    user,
    clinic,
):
    log = write_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        user_id=user.id,
        clinic_id=clinic.id,
    )

    assert log in db_session.new
    assert log.id is None

    db_session.flush()

    assert log.id is not None


def test_write_audit_log_preserves_non_sensitive_data(
    db_session,
    user,
    clinic,
):
    payload = {
        "status": "active",
        "priority": "high",
        "department": "cardiology",
    }

    log = write_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        user_id=user.id,
        clinic_id=clinic.id,
        new_value=payload,
    )

    db_session.flush()

    assert log.new_value == payload