import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.patient_timeline import (
    count_patient_timeline,
    get_patient_timeline,
    get_patient_timeline_page,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role


def make_log(
    *,
    clinic_id,
    entity_type="Patient",
    entity_id=100,
    action=AuditAction.CREATE,
    user_id=None,
):
    return AuditLog(
        clinic_id=clinic_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
    )


def test_get_patient_timeline_returns_patient_events(
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
            entity_id=100,
            action=AuditAction.UPDATE,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=101,
        )
    )

    db_session.flush()

    result = get_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        patient_id=100,
    )

    assert len(result) == 2
    assert all(
        log.entity_type == "Patient"
        for log in result
    )
    assert all(
        log.entity_id == 100
        for log in result
    )
    assert all(
        log.clinic_id == 1
        for log in result
    )


def test_patient_timeline_is_tenant_scoped(
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
            entity_id=100,
        )
    )

    db_session.flush()

    result = get_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        patient_id=100,
    )

    assert len(result) == 1
    assert result[0].clinic_id == 1


def test_super_admin_can_read_patient_timeline_across_clinics(
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
            entity_id=100,
        )
    )

    db_session.flush()

    result = get_patient_timeline(
        actor_role=Role.SUPER_ADMIN,
        actor_clinic_id=None,
        patient_id=100,
    )

    assert len(result) == 2


def test_patient_timeline_supports_action_filter(
    db_session,
):
    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
            action=AuditAction.CREATE,
        )
    )

    db_session.add(
        make_log(
            clinic_id=1,
            entity_id=100,
            action=AuditAction.UPDATE,
        )
    )

    db_session.flush()

    result = get_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        patient_id=100,
        action=AuditAction.UPDATE,
    )

    assert len(result) == 1
    assert result[0].action == AuditAction.UPDATE


def test_patient_timeline_page_preserves_pagination(
    db_session,
):
    for index in range(5):
        db_session.add(
            make_log(
                clinic_id=1,
                entity_id=100,
            )
        )

    db_session.flush()

    result = get_patient_timeline_page(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        patient_id=100,
        page=1,
        per_page=2,
    )

    assert result.total == 5
    assert result.page == 1
    assert result.per_page == 2
    assert len(result.items) == 2
    assert result.has_next is True


def test_count_patient_timeline_is_tenant_scoped(
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
            entity_id=100,
        )
    )

    db_session.add(
        make_log(
            clinic_id=2,
            entity_id=100,
        )
    )

    db_session.flush()

    count = count_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=1,
        patient_id=100,
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
def test_non_admin_cannot_read_patient_timeline(
    role,
):
    with pytest.raises(
        PermissionError,
        match="Insufficient audit permissions",
    ):
        get_patient_timeline(
            actor_role=role,
            actor_clinic_id=1,
            patient_id=100,
        )
        
def test_patient_timeline_reads_production_patient_audit_writer(
    db_session,
    clinic,
    user,
):
    from app.core.audit.queries.patient_timeline import (
        get_patient_timeline,
    )
    from app.modules.patient.services.patient_service import (
        create_patient,
    )

    patient = create_patient(
        clinic.id,
        {
            "first_name": "Timeline",
            "last_name": "Integration",
            "email": "timeline-integration@test.com",
        },
        actor_id=user.id,
    )

    result = get_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=clinic.id,
        patient_id=patient.id,
    )

    assert len(result) == 1
    assert result[0].entity_id == patient.id
    assert result[0].entity_type == "patient"
    assert result[0].user_id == user.id
    assert result[0].clinic_id == clinic.id
    assert result[0].action == AuditAction.CREATE