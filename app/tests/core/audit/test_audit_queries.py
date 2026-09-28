import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.audit_queries import (
    build_audit_query,
    count_audit_logs,
    get_audit_log,
    list_audit_logs,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


def make_log(
    *,
    clinic_id,
    user_id=None,
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


def test_admin_query_is_scoped_to_own_clinic(
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

    result = db_session.execute(
        build_audit_query(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
        )
    ).scalars().all()

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_admin_cannot_select_another_clinic():
    with pytest.raises(
        PermissionError,
        match="Audit clinic scope is not permitted",
    ):
        build_audit_query(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            target_clinic_id=2,
        )


def test_admin_without_clinic_is_rejected():
    with pytest.raises(
        PermissionError,
        match="Audit administrator must belong to a clinic",
    ):
        build_audit_query(
            actor_role=Role.ADMIN,
            actor_clinic_id=None,
        )


def test_admin_does_not_see_global_logs(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=None,
            entity_id=999,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
        )
    )

    db_session.flush()

    result = db_session.execute(
        build_audit_query(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
        )
    ).scalars().all()

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_super_admin_can_query_all_clinics(
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

    db_session.add(
        make_log(
            clinic_id=None,
            entity_id=999,
        )
    )

    db_session.flush()

    result = db_session.execute(
        build_audit_query(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=None,
        )
    ).scalars().all()

    assert len(result) == 3


def test_super_admin_can_scope_to_clinic(
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

    result = db_session.execute(
        build_audit_query(
            actor_role=Role.SUPER_ADMIN,
            actor_clinic_id=None,
            target_clinic_id=2,
        )
    ).scalars().all()

    assert len(result) == 1
    assert result[0].clinic_id == 2


def test_user_filter_cannot_escape_admin_tenant(
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

    result = db_session.execute(
        build_audit_query(
            actor_role=Role.ADMIN,
            actor_clinic_id=1,
            user_id=10,
        )
    ).scalars().all()

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_list_audit_logs_preserves_pagination(
    db_session,
):
    for entity_id in range(100, 105):
        db_session.add(
            make_log(
                clinic_id=1,
                entity_id=entity_id,
            )
        )

    db_session.flush()

    result = list_audit_logs(
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
    assert result.has_prev is False


def test_get_audit_log_is_tenant_scoped(
    db_session,
):
    own = make_log(
        clinic_id=1,
        entity_id=100,
    )

    foreign = make_log(
        clinic_id=2,
        entity_id=200,
    )

    db_session.add(own)
    db_session.add(foreign)
    db_session.flush()

    result = get_audit_log(
        audit_log_id=own.id,
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert result is not None
    assert result.id == own.id


def test_get_audit_log_hides_foreign_record(
    db_session,
):
    foreign = make_log(
        clinic_id=2,
        entity_id=200,
    )

    db_session.add(foreign)
    db_session.flush()

    result = get_audit_log(
        audit_log_id=foreign.id,
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert result is None


def test_count_audit_logs_is_tenant_scoped(
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

    count = count_audit_logs(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
    )

    assert count == 2


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
def test_non_admin_roles_are_rejected(role):
    with pytest.raises(
        PermissionError,
        match="Insufficient audit permissions",
    ):
        build_audit_query(
            actor_role=role,
            actor_clinic_id=1,
        )