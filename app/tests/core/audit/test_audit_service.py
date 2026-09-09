import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.services import audit_service as service
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import NotFoundError, ValidationError


# ============================================================================
# HELPERS
# ============================================================================


def make_audit_log(
    *,
    user_id=1,
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
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )


# ============================================================================
# CREATE
# ============================================================================


def test_create_audit_log_creates_record(db_session):
    log = service.create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=100,
        description="Patient created",
        user_id=1,
        new_value={"status": "active"},
    )

    db_session.flush()

    assert log.id is not None
    assert log.user_id == 1
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


def test_create_audit_log_supports_resource_aliases(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.UPDATE,
        resource_type="Patient",
        resource_id=101,
        description="Patient updated",
        details={"status": "active"},
    )

    db_session.flush()

    assert log.entity_type == "Patient"
    assert log.entity_id == 101
    assert log.new_value == {"status": "active"}


def test_create_audit_log_entity_arguments_take_precedence(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        resource_type="Appointment",
        resource_id=999,
    )

    db_session.flush()

    assert log.entity_type == "Patient"
    assert log.entity_id == 100


# ============================================================================
# ENTITY VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "entity_type, resource_type",
    [
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_create_audit_log_requires_entity_type(
    entity_type,
    resource_type,
):
    with pytest.raises(
        ValidationError,
        match="Audit entity type is required",
    ):
        service.create_audit_log(
            action=AuditAction.CREATE,
            entity_type=entity_type,
            resource_type=resource_type,
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


# ============================================================================
# OPTIONAL VALUES
# ============================================================================


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


# ============================================================================
# IP ADDRESS
# ============================================================================


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


# ============================================================================
# AUDIT VALUES
# ============================================================================


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


def test_new_value_takes_precedence_over_details(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        new_value={"status": "active"},
        details={"status": "wrong"},
    )

    db_session.flush()

    assert log.new_value == {
        "status": "active",
    }


def test_details_are_used_when_new_value_missing(
    db_session,
):
    log = service.create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
        details={"status": "active"},
    )

    db_session.flush()

    assert log.new_value == {
        "status": "active",
    }


# ============================================================================
# LIST
# ============================================================================


def test_list_audit_logs_returns_paginated_result(
    db_session,
):
    for index in range(3):
        db_session.add(
            make_audit_log(
                entity_id=100 + index,
            )
        )

    db_session.flush()

    result = service.list_audit_logs(
        page=1,
        per_page=2,
    )

    assert result.page == 1
    assert result.per_page == 2
    assert result.total == 3
    assert result.pages == 2
    assert result.has_next is True
    assert result.has_prev is False
    assert len(result.items) == 2


def test_list_audit_logs_returns_last_page(
    db_session,
):
    for index in range(3):
        db_session.add(
            make_audit_log(
                entity_id=100 + index,
            )
        )

    db_session.flush()

    result = service.list_audit_logs(
        page=2,
        per_page=2,
    )

    assert result.page == 2
    assert result.pages == 2
    assert result.total == 3
    assert result.has_next is False
    assert result.has_prev is True
    assert len(result.items) == 1


def test_list_audit_logs_returns_empty_page(
    db_session,
):
    db_session.add(
        make_audit_log(
            entity_id=100,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        page=2,
        per_page=20,
    )

    assert result.page == 2
    assert result.total == 1
    assert result.items == []
    assert result.has_next is False
    assert result.has_prev is True


def test_list_audit_logs_filters_by_user_id(
    db_session,
):
    db_session.add(
        make_audit_log(
            user_id=1,
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            user_id=2,
            entity_id=101,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        user_id=1,
    )

    assert result.total == 1
    assert result.items[0].user_id == 1


def test_list_audit_logs_filters_by_action(
    db_session,
):
    db_session.add(
        make_audit_log(
            action=AuditAction.CREATE,
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            action=AuditAction.UPDATE,
            entity_id=101,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        action=AuditAction.UPDATE,
    )

    assert result.total == 1
    assert result.items[0].action == AuditAction.UPDATE


def test_list_audit_logs_accepts_action_value(
    db_session,
):
    db_session.add(
        make_audit_log(
            action=AuditAction.CREATE,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        action="create",
    )

    assert result.total == 1


def test_list_audit_logs_rejects_invalid_action():
    with pytest.raises(
        ValidationError,
        match="Invalid audit action",
    ):
        service.list_audit_logs(
            action="invalid-action",
        )


def test_list_audit_logs_filters_by_entity_type(
    db_session,
):
    db_session.add(
        make_audit_log(
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            entity_type="Appointment",
            entity_id=200,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        entity_type="Patient",
    )

    assert result.total == 1
    assert result.items[0].entity_type == "Patient"


def test_list_audit_logs_filters_by_entity_id(
    db_session,
):
    db_session.add(
        make_audit_log(
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            entity_id=101,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        entity_id=100,
    )

    assert result.total == 1
    assert result.items[0].entity_id == 100


def test_list_audit_logs_combines_filters(
    db_session,
):
    db_session.add(
        make_audit_log(
            user_id=1,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            user_id=1,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.add(
        make_audit_log(
            user_id=2,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        user_id=1,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=100,
    )

    assert result.total == 1

    log = result.items[0]

    assert log.user_id == 1
    assert log.action == AuditAction.UPDATE
    assert log.entity_type == "Patient"
    assert log.entity_id == 100


def test_list_audit_logs_normalizes_entity_type(
    db_session,
):
    db_session.add(
        make_audit_log(
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        entity_type="  Patient  ",
    )

    assert result.total == 1
    assert result.items[0].entity_type == "Patient"


def test_list_audit_logs_returns_empty_when_no_match(
    db_session,
):
    db_session.add(
        make_audit_log(
            user_id=1,
            entity_id=100,
        )
    )

    db_session.flush()

    result = service.list_audit_logs(
        user_id=999,
    )

    assert result.total == 0
    assert result.items == []
    assert result.has_next is False
    assert result.has_prev is False


# ============================================================================
# PAGINATION VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "page",
    [
        0,
        -1,
        True,
        False,
        "1",
    ],
)
def test_list_audit_logs_rejects_invalid_page(
    page,
):
    with pytest.raises(
        ValidationError,
        match="Page must be a positive integer",
    ):
        service.list_audit_logs(
            page=page,
        )


@pytest.mark.parametrize(
    "per_page",
    [
        0,
        -1,
        True,
        False,
        "20",
        101,
    ],
)
def test_list_audit_logs_rejects_invalid_per_page(
    per_page,
):
    with pytest.raises(
        ValidationError,
        match="Per page",
    ):
        service.list_audit_logs(
            per_page=per_page,
        )


# ============================================================================
# FILTER VALIDATION
# ============================================================================


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
def test_list_audit_logs_rejects_invalid_user_id(
    user_id,
):
    with pytest.raises(
        ValidationError,
        match="User ID must be a positive integer",
    ):
        service.list_audit_logs(
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
def test_list_audit_logs_rejects_invalid_entity_id(
    entity_id,
):
    with pytest.raises(
        ValidationError,
        match="Entity ID must be a positive integer",
    ):
        service.list_audit_logs(
            entity_id=entity_id,
        )


def test_list_audit_logs_rejects_entity_type_over_80_characters():
    with pytest.raises(
        ValidationError,
        match="Entity type cannot exceed 80 characters",
    ):
        service.list_audit_logs(
            entity_type="A" * 81,
        )


def test_list_audit_logs_allows_empty_entity_type(
    db_session,
):
    result = service.list_audit_logs(
        entity_type="   ",
    )

    assert result.total == 0
    assert result.items == []
    assert result.has_next is False
    assert result.has_prev is False


# ============================================================================
# ORDERING
# ============================================================================


def test_list_audit_logs_returns_newest_first(
    db_session,
):
    first = make_audit_log(
        entity_id=100,
    )

    second = make_audit_log(
        entity_id=101,
    )

    db_session.add(first)
    db_session.flush()

    db_session.add(second)
    db_session.flush()

    result = service.list_audit_logs()

    ids = [log.id for log in result.items]

    assert ids == sorted(
        ids,
        reverse=True,
    )


# ============================================================================
# GET
# ============================================================================


def test_get_audit_log_by_id_returns_record(
    db_session,
):
    log = make_audit_log(
        user_id=1,
        entity_type="Patient",
        entity_id=100,
        description="Patient created",
        ip_address="10.0.0.15",
    )

    db_session.add(log)
    db_session.flush()

    result = service.get_audit_log_by_id(
        log.id
    )

    assert result.id == log.id
    assert result.user_id == 1
    assert result.entity_type == "Patient"
    assert result.entity_id == 100
    assert result.description == "Patient created"
    assert result.ip_address == "10.0.0.15"


def test_get_audit_log_by_id_raises_not_found(
    db_session,
):
    with pytest.raises(
        NotFoundError,
        match="Audit log 999999 not found",
    ):
        service.get_audit_log_by_id(999999)


@pytest.mark.parametrize(
    "log_id",
    [
        0,
        -1,
        True,
        False,
        "1",
    ],
)
def test_get_audit_log_by_id_rejects_invalid_id(
    log_id,
):
    with pytest.raises(
        ValidationError,
        match="Audit log ID must be a positive integer",
    ):
        service.get_audit_log_by_id(log_id)