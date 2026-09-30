import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.services import audit_service as service
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import ValidationError


def make_audit_log(
    *,
    user_id=1,
    clinic_id=None,
    action=AuditAction.CREATE,
    entity_type="Patient",
    entity_id=100,
    description="Patient created",
    old_value=None,
    new_value=None,
    ip_address=None,
):
    return AuditLog(
        user_id=user_id,
        clinic_id=clinic_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )


def test_create_audit_log_creates_record(db_session):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="Patient created",
        user_id=1,
        clinic_id=1,
        new_value={"status": "active"},
    )

    db_session.flush()

    assert log.id is not None
    assert log.user_id == 1
    assert log.clinic_id == 1
    assert log.action == AuditAction.CREATE
    assert log.entity_type == "Patient"
    assert log.entity_id == 100
    assert log.description == "Patient created"
    assert log.new_value == {"status": "active"}


def test_create_audit_log_accepts_action_value(db_session):
    log = service.create_audit_log(
        action="create",
        entity_type="Patient",
        entity_id=100,
    )

    db_session.flush()

    assert log.action == AuditAction.CREATE


def test_create_audit_log_rejects_invalid_action():
    with pytest.raises(
        ValidationError,
        match="Invalid audit action",
    ):
        service.create_audit_log(
            action="invalid-action",
            entity_type="Patient",
            entity_id=100,
        )






@pytest.mark.parametrize(
    "entity_type",
    [
        None,
        "",
        "   ",
    ],
)
def test_create_audit_log_requires_entity_type(
    entity_type,
):
    with pytest.raises(
        ValidationError,
        match="Audit entity type is required",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type=entity_type,
            entity_id=100,
        )




@pytest.mark.parametrize(
    "entity_id",
    [
        None,
        0,
        -1,
        True,
        False,
        "100",
    ],
)
def test_create_audit_log_rejects_invalid_entity_id(
    entity_id,
):
    with pytest.raises(
        ValidationError,
        match="Audit entity ID must be a positive integer",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=entity_id,
        )


def test_create_audit_log_rejects_entity_type_over_80_characters():
    with pytest.raises(
        ValidationError,
        match="Audit entity type cannot exceed 80 characters",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="A" * 81,
            entity_id=100,
        )


def test_create_audit_log_strips_entity_type(db_session):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="  Patient  ",
        entity_id=100,
    )

    db_session.flush()

    assert log.entity_type == "Patient"


def test_create_audit_log_allows_missing_user_id(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="System",
        entity_id=1,
    )

    db_session.flush()

    assert log.user_id is None


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
def test_create_audit_log_rejects_invalid_user_id(
    user_id,
):
    with pytest.raises(
        ValidationError,
        match="User ID must be a positive integer",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            user_id=user_id,
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
def test_create_audit_log_rejects_invalid_clinic_id(
    clinic_id,
):
    with pytest.raises(
        ValidationError,
        match="Clinic ID must be a positive integer",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            clinic_id=clinic_id,
        )


def test_create_audit_log_stores_clinic_id(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        clinic_id=1,
    )

    db_session.flush()

    assert log.clinic_id == 1


def test_create_audit_log_normalizes_description(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="  Patient created  ",
    )

    db_session.flush()

    assert log.description == "Patient created"


def test_create_audit_log_allows_empty_description(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="   ",
    )

    db_session.flush()

    assert log.description is None


def test_create_audit_log_rejects_long_description():
    with pytest.raises(
        ValidationError,
        match="Audit description cannot exceed 255 characters",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            description="A" * 256,
        )


def test_create_audit_log_stores_ip_address(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        ip_address="192.168.1.10",
    )

    db_session.flush()

    assert log.ip_address == "192.168.1.10"


def test_create_audit_log_normalizes_ip_address(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        ip_address=" 192.168.1.10 ",
    )

    db_session.flush()

    assert log.ip_address == "192.168.1.10"


def test_create_audit_log_allows_missing_ip_address(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="System",
        entity_id=1,
    )

    db_session.flush()

    assert log.ip_address is None


def test_create_audit_log_allows_empty_ip_address(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="System",
        entity_id=1,
        ip_address="   ",
    )

    db_session.flush()

    assert log.ip_address is None


@pytest.mark.parametrize(
    "ip_address",
    [
        123,
        True,
        False,
        [],
        {},
    ],
)
def test_create_audit_log_rejects_invalid_ip_address(
    ip_address,
):
    with pytest.raises(
        ValidationError,
        match="IP address must be a string",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            ip_address=ip_address,
        )


def test_create_audit_log_rejects_ip_address_over_45_characters():
    with pytest.raises(
        ValidationError,
        match="IP address cannot exceed 45 characters",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
            ip_address="A" * 46,
        )


def test_create_audit_log_preserves_old_and_new_values(
    db_session,
):
    old_value = {
        "status": "pending",
        "priority": "normal",
    }

    new_value = {
        "status": "completed",
        "priority": "high",
    }

    log = service.create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Appointment",
        entity_id=500,
        old_value=old_value,
        new_value=new_value,
    )

    db_session.flush()

    assert log.old_value == old_value
    assert log.new_value == new_value


def test_create_audit_log_redacts_sensitive_values(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="User",
        entity_id=100,
        old_value={
            "password": "old-secret",
            "profile": {
                "status": "active",
            },
        },
        new_value={
            "password": "new-secret",
            "access_token": "secret-token",
            "profile": {
                "status": "disabled",
            },
        },
    )

    db_session.flush()

    assert log.old_value == {
        "password": "[REDACTED]",
        "profile": {
            "status": "active",
        },
    }

    assert log.new_value == {
        "password": "[REDACTED]",
        "access_token": "[REDACTED]",
        "profile": {
            "status": "disabled",
        },
    }




