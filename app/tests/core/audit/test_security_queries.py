import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.security_queries import (
    count_security_events,
    get_security_event_page,
    get_security_events,
    get_user_security_events,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


def make_log(
    *,
    clinic_id,
    user_id=10,
    action=AuditAction.LOGIN,
    entity_type="User",
    entity_id=10,
):
    return AuditLog(
        clinic_id=clinic_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def test_get_security_events_returns_authentication_events(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            action=AuditAction.LOGIN,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            action=AuditAction.LOGOUT,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            action=AuditAction.UPDATE,
        )
    )

    db_session.flush()

    result = get_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert len(result) == 2
    assert all(
        log.action
        in {
            AuditAction.LOGIN,
            AuditAction.LOGOUT,
        }
        for log in result
    )


def test_security_events_are_tenant_scoped(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            entity_id=200,
        )
    )

    db_session.flush()

    result = get_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_super_admin_can_query_security_events_across_clinics(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            entity_id=200,
        )
    )

    db_session.flush()

    result = get_security_events(
        actor_role=Role.SUPER_ADMIN,
        actor_clinic_id=None,
    )

    assert len(result) == 2


def test_security_events_support_user_filter(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            user_id=20,
            entity_id=200,
        )
    )

    db_session.flush()

    result = get_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        user_id=10,
    )

    assert len(result) == 1
    assert result[0].user_id == 10


def test_get_user_security_events_returns_user_history(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            action=AuditAction.LOGIN,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            action=AuditAction.LOGOUT,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            user_id=20,
            action=AuditAction.LOGIN,
        )
    )

    db_session.flush()

    result = get_user_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
    )

    assert len(result) == 2
    assert all(log.user_id == 10 for log in result)


def test_user_security_events_preserve_tenant_isolation(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            user_id=10,
            entity_id=200,
        )
    )

    db_session.flush()

    result = get_user_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
    )

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_security_event_page_preserves_pagination(
    db_session,
):
    for index in range(5):
        db_session.add(
            make_log(
                clinic_id=1,
                entity_id=100 + index,
            )
        )

    db_session.flush()

    result = get_security_event_page(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        page=1,
        per_page=2,
    )

    assert result.total == 5
    assert result.page == 1
    assert result.per_page == 2
    assert len(result.items) == 2
    assert result.has_next is True


def test_count_security_events_is_tenant_scoped(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=101,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            entity_id=102,
        )
    )

    db_session.flush()

    count = count_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert count == 2


def test_security_events_exclude_non_security_actions(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            action=AuditAction.VIEW,
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            action=AuditAction.STATUS_CHANGE,
            entity_id=101,
        )
    )

    db_session.flush()

    result = get_security_events(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert result == []


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PATIENT,
        Role.RECEPTIONIST,
        Role.ACCOUNTANT,
    ],
)
def test_non_admin_cannot_query_security_events(
    role,
):
    with pytest.raises(
        PermissionError,
        match="Insufficient audit permissions",
    ):
        get_security_events(
            actor_role=role,
            actor_clinic_id=1,
        )


@pytest.mark.parametrize(
    "target_user_id",
    [
        0,
        -1,
        True,
        False,
        "10",
    ],
)
def test_get_user_security_events_rejects_invalid_user_id(
    target_user_id,
):
    with pytest.raises(
        ValueError,
        match="Target user ID must be a positive integer",
    ):
        get_user_security_events(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            target_user_id=target_user_id,
        )