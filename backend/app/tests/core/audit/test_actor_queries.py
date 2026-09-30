import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.actor_queries import (
    count_actor_audit_logs,
    get_actor_audit_logs,
    get_actor_audit_page,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


def make_log(
    *,
    clinic_id,
    user_id,
    entity_type="Patient",
    entity_id=100,
    action=AuditAction.CREATE,
):
    return AuditLog(
        clinic_id=clinic_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )


def test_get_actor_audit_logs_returns_actor_history(
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
            user_id=10,
            entity_id=101,
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

    result = get_actor_audit_logs(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
    )

    assert len(result) == 2
    assert all(log.user_id == 10 for log in result)
    assert all(log.clinic_id == 1 for log in result)


def test_get_actor_audit_logs_preserves_tenant_isolation(
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

    result = get_actor_audit_logs(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
    )

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_super_admin_can_read_actor_history_across_clinics(
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

    result = get_actor_audit_logs(
        actor_role=Role.SUPER_ADMIN,
        actor_clinic_id=None,
        target_user_id=10,
    )

    assert len(result) == 2


def test_get_actor_audit_logs_supports_filters(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            user_id=10,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=101,
        )
    )

    db_session.flush()

    result = get_actor_audit_logs(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
        action=AuditAction.UPDATE,
        entity_type="Patient",
    )

    assert len(result) == 1
    assert result[0].action == AuditAction.UPDATE
    assert result[0].entity_id == 101


def test_get_actor_audit_page_preserves_pagination(
    db_session,
):
    for entity_id in range(100, 105):
        db_session.add(
            make_log(
                clinic_id=1,
                user_id=10,
                entity_id=entity_id,
            )
        )

    db_session.flush()

    result = get_actor_audit_page(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
        page=1,
        per_page=2,
    )

    assert result.total == 5
    assert result.page == 1
    assert result.per_page == 2
    assert len(result.items) == 2
    assert result.has_next is True


def test_count_actor_audit_logs_is_tenant_scoped(
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
            user_id=10,
            entity_id=101,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            user_id=10,
            entity_id=102,
        )
    )

    db_session.flush()

    count = count_actor_audit_logs(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        target_user_id=10,
    )

    assert count == 2


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PATIENT,
        Role.RECEPTIONIST,
    ],
)
def test_non_admin_cannot_query_actor_history(
    role,
):
    with pytest.raises(
        PermissionError,
        match="Insufficient audit permissions",
    ):
        get_actor_audit_logs(
            actor_role=role,
            actor_clinic_id=1,
            target_user_id=10,
        )