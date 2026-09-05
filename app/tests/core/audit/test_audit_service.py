import pytest
from datetime import timedelta

from app.core.audit.services.audit_service import (
    create_audit_log,
    get_audit_log_by_id,
    list_audit_logs,
)
from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import NotFoundError


# ============================================================================
# create_audit_log()
# ============================================================================

class TestCreateAuditLog:
    def test_creates_audit_log_with_entity_fields(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            description="User created",
            user_id=user.id,
        )

        assert isinstance(log, AuditLog)
        assert log.action == AuditAction.CREATE
        assert log.entity_type == "User"
        assert log.entity_id == user.id
        assert log.description == "User created"
        assert log.user_id == user.id

    def test_creates_audit_log_with_resource_fields(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            resource_type="User",
            resource_id=user.id,
            description="User created",
            user_id=user.id,
        )

        assert log.entity_type == "User"
        assert log.entity_id == user.id
        assert log.action == AuditAction.CREATE

    def test_entity_fields_take_precedence_over_resource_fields(
        self,
        db,
        user,
        patient,
    ):
        log = create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
            resource_type="User",
            resource_id=user.id,
        )

        assert log.entity_type == "Patient"
        assert log.entity_id == patient.id

    def test_resource_fields_are_used_when_entity_fields_are_missing(
        self,
        db,
        patient,
    ):
        log = create_audit_log(
            action=AuditAction.UPDATE,
            resource_type="Patient",
            resource_id=patient.id,
        )

        assert log.entity_type == "Patient"
        assert log.entity_id == patient.id

    def test_accepts_optional_values(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            description="User updated",
            old_value={"email": "old@test.com"},
            new_value={"email": "new@test.com"},
            user_id=user.id,
        )

        assert log.description == "User updated"
        assert log.old_value == {"email": "old@test.com"}
        assert log.new_value == {"email": "new@test.com"}
        assert log.user_id == user.id

    def test_details_are_used_as_new_value_when_new_value_is_none(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            details={"changed_fields": ["email", "role"]},
        )

        assert log.new_value == {
            "changed_fields": ["email", "role"]
        }

    def test_explicit_new_value_takes_precedence_over_details(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            new_value={"role": "admin"},
            details={"role": "doctor"},
        )

        assert log.new_value == {"role": "admin"}

    def test_user_id_is_optional(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
        )

        assert log.user_id is None

    def test_requires_entity_type_or_resource_type(
        self,
        db,
        user,
    ):
        with pytest.raises(
            ValueError,
            match="Audit entity type and entity ID are required",
        ):
            create_audit_log(
                action=AuditAction.CREATE,
                entity_id=user.id,
            )

    def test_requires_entity_id_or_resource_id(
        self,
        db,
    ):
        with pytest.raises(
            ValueError,
            match="Audit entity type and entity ID are required",
        ):
            create_audit_log(
                action=AuditAction.CREATE,
                entity_type="User",
            )

    def test_rejects_missing_entity_type_and_resource_type(
        self,
        db,
    ):
        with pytest.raises(
            ValueError,
            match="Audit entity type and entity ID are required",
        ):
            create_audit_log(
                action=AuditAction.CREATE,
            )

    def test_entity_id_zero_is_valid(
        self,
        db,
    ):
        """
        The implementation explicitly checks `is not None`, so 0 should
        not be treated as a missing entity ID.
        """
        log = create_audit_log(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=0,
        )

        assert log.entity_id == 0

    def test_resource_id_zero_is_valid(
        self,
        db,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            resource_type="User",
            resource_id=0,
        )

        assert log.entity_id == 0

    def test_adds_log_to_session(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
        )

        db.session.flush()

        assert log.id is not None

        persisted = db.session.get(AuditLog, log.id)

        assert persisted is not None
        assert persisted.entity_type == "User"
        assert persisted.entity_id == user.id


# ============================================================================
# list_audit_logs()
# ============================================================================

class TestListAuditLogs:
    def _create_log(
        self,
        db,
        *,
        action,
        entity_type,
        entity_id,
        user_id=None,
        description=None,
    ):
        log = create_audit_log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            description=description,
        )
        db.session.flush()
        return log

    def test_returns_paginated_audit_logs(
        self,
        db,
        user,
        patient,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            user_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
            user_id=user.id,
        )

        db.session.commit()

        result = list_audit_logs()

        assert result.page == 1
        assert result.per_page == 20
        assert result.total == 2
        assert len(result.items) == 2

    def test_filters_by_user_id(
        self,
        db,
        make_user,
        clinic,
    ):
        user_one = make_user(
            clinic,
            email="audit-user-one@test.com",
        )

        user_two = make_user(
            clinic,
            email="audit-user-two@test.com",
        )

        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user_one.id,
            user_id=user_one.id,
        )

        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user_two.id,
            user_id=user_two.id,
        )

        db.session.commit()

        result = list_audit_logs(user_id=user_one.id)

        assert result.total == 1
        assert result.items[0].user_id == user_one.id

    def test_filters_by_action(
        self,
        db,
        user,
        patient,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            user_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
            user_id=user.id,
        )

        db.session.commit()

        result = list_audit_logs(
            action=AuditAction.UPDATE,
        )

        assert result.total == 1
        assert result.items[0].action == AuditAction.UPDATE

    def test_filters_by_entity_type(
        self,
        db,
        user,
        patient,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=patient.id,
        )

        db.session.commit()

        result = list_audit_logs(
            entity_type="Patient",
        )

        assert result.total == 1
        assert result.items[0].entity_type == "Patient"

    def test_filters_by_entity_id(
        self,
        db,
        user,
        patient,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="Patient",
            entity_id=patient.id,
        )

        db.session.commit()

        result = list_audit_logs(
            entity_type="Patient",
            entity_id=patient.id,
        )

        assert result.total == 1
        assert result.items[0].entity_type == "Patient"
        assert result.items[0].entity_id == patient.id

    def test_combines_multiple_filters(
        self,
        db,
        user,
        patient,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            user_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            user_id=user.id,
        )

        self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
            user_id=user.id,
        )

        db.session.commit()

        result = list_audit_logs(
            user_id=user.id,
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
        )

        assert result.total == 1
        assert result.items[0].action == AuditAction.UPDATE
        assert result.items[0].entity_type == "User"
        assert result.items[0].entity_id == user.id

    def test_returns_all_matching_logs_when_no_filters_are_given(
        self,
        db,
        user,
        patient,
    ):
        for index in range(3):
            self._create_log(
                db,
                action=AuditAction.CREATE,
                entity_type="User",
                entity_id=user.id,
                description=f"Log {index}",
            )

        self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
        )

        db.session.commit()

        result = list_audit_logs()

        assert result.total == 4
        assert len(result.items) == 4

    def test_empty_result_returns_empty_page(
        self,
        db,
    ):
        result = list_audit_logs(
            user_id=999999,
        )

        assert result.total == 0
        assert result.items == []

    def test_paginates_results(
        self,
        db,
        user,
    ):
        for index in range(5):
            self._create_log(
                db,
                action=AuditAction.CREATE,
                entity_type="User",
                entity_id=user.id,
                description=f"Log {index}",
            )

        db.session.commit()

        result = list_audit_logs(
            page=1,
            per_page=2,
        )

        assert result.page == 1
        assert result.per_page == 2
        assert result.total == 5
        assert len(result.items) == 2
        assert result.pages == 3

    def test_returns_second_page(
        self,
        db,
        user,
    ):
        for index in range(5):
            self._create_log(
                db,
                action=AuditAction.CREATE,
                entity_type="User",
                entity_id=user.id,
                description=f"Log {index}",
            )

        db.session.commit()

        result = list_audit_logs(
            page=2,
            per_page=2,
        )

        assert result.page == 2
        assert result.total == 5
        assert len(result.items) == 2

    def test_out_of_range_page_returns_empty_items(
        self,
        db,
        user,
    ):
        self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
        )

        db.session.commit()

        result = list_audit_logs(
            page=999,
            per_page=20,
        )

        assert result.total == 1
        assert result.items == []

    def test_orders_logs_by_created_at_descending(
        self,
        db,
        user,
    ):
        first = self._create_log(
            db,
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            description="First",
        )

        db.session.commit()

        second = self._create_log(
            db,
            action=AuditAction.UPDATE,
            entity_type="User",
            entity_id=user.id,
            description="Second",
        )

        db.session.commit()

        # SQLite may assign the same timestamp to rows created in rapid
        # succession. Make the timestamps explicitly different so this
        # test verifies the service's ORDER BY behavior deterministically.
        second.created_at = first.created_at + timedelta(seconds=1)
        db.session.commit()

        result = list_audit_logs()

        assert result.items[0].id == second.id
        assert result.items[1].id == first.id
        assert result.items[0].created_at > result.items[1].created_at


# ============================================================================
# get_audit_log_by_id()
# ============================================================================

class TestGetAuditLogById:
    def test_returns_audit_log_when_it_exists(
        self,
        db,
        user,
    ):
        log = create_audit_log(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=user.id,
            description="User created",
            user_id=user.id,
        )

        db.session.commit()

        result = get_audit_log_by_id(log.id)

        assert result.id == log.id
        assert result.action == AuditAction.CREATE
        assert result.entity_type == "User"
        assert result.entity_id == user.id
        assert result.description == "User created"

    def test_raises_not_found_error_when_log_does_not_exist(
        self,
        db,
    ):
        with pytest.raises(
            NotFoundError,
            match="Audit log 999999 not found",
        ):
            get_audit_log_by_id(999999)