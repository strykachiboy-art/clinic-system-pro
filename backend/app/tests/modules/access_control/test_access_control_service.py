from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.auth.user.models.user_model import User
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.access_control.schemas.access_control_schema import (
    AccessControlUserListQuerySchema,
)
from app.modules.access_control.services import (
    access_control_service,
)


# ============================================================================
# HELPERS
# ============================================================================


def make_query(
    *,
    page: int = 1,
    per_page: int = 50,
    role: Role | None = None,
    is_active: bool | None = None,
) -> AccessControlUserListQuerySchema:
    return AccessControlUserListQuerySchema(
        page=page,
        per_page=per_page,
        role=role,
        is_active=is_active,
    )


def assert_user_response(
    response,
    user: User,
):
    assert response.id == user.id
    assert str(response.email) == user.email
    assert response.role == user.role
    assert response.is_active is user.is_active
    assert response.clinic_id == user.clinic_id


# ============================================================================
# POSITIVE ID VALIDATION
# ============================================================================


class TestValidatePositiveId:
    @pytest.mark.parametrize(
        "value",
        [
            0,
            -1,
            None,
            True,
            False,
            "1",
        ],
    )
    def test_rejects_invalid_ids(
        self,
        value,
    ):
        with pytest.raises(
            ValidationError,
            match="must be a positive integer",
        ):
            access_control_service._validate_positive_id(
                value,
                "User ID",
            )

    @pytest.mark.parametrize(
        "value",
        [
            1,
            2,
            999,
        ],
    )
    def test_accepts_positive_integer(
        self,
        value,
    ):
        access_control_service._validate_positive_id(
            value,
            "User ID",
        )


# ============================================================================
# REASON NORMALIZATION
# ============================================================================


class TestNormalizeReason:
    def test_none_returns_none(self):
        assert (
            access_control_service._normalize_reason(
                None
            )
            is None
        )

    def test_strips_surrounding_whitespace(self):
        result = access_control_service._normalize_reason(
            "  Administrative review  "
        )

        assert result == "Administrative review"

    def test_blank_string_returns_none(self):
        result = access_control_service._normalize_reason(
            "    "
        )

        assert result is None

    def test_rejects_non_string_reason(self):
        with pytest.raises(
            ValidationError,
            match="Reason must be a string",
        ):
            access_control_service._normalize_reason(
                123
            )


# ============================================================================
# GET USER
# ============================================================================


class TestGetUser:
    def test_returns_existing_user(
        self,
        app,
        user,
    ):
        result = access_control_service._get_user(
            user.id
        )

        assert result.id == user.id
        assert result.email == user.email

    @pytest.mark.parametrize(
        "user_id",
        [
            0,
            -1,
            None,
            True,
            False,
            "1",
        ],
    )
    def test_rejects_invalid_user_id(
        self,
        app,
        user_id,
    ):
        with pytest.raises(
            ValidationError,
            match="User ID must be a positive integer",
        ):
            access_control_service._get_user(
                user_id
            )

    def test_raises_not_found_for_missing_user(
        self,
        app,
    ):
        with pytest.raises(
            NotFoundError,
            match=r"User 999999 not found",
        ):
            access_control_service._get_user(
                999999
            )


# ============================================================================
# ACTOR VALIDATION
# ============================================================================


class TestValidateActor:
    def test_accepts_active_super_admin(
        self,
        app,
        make_user,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="super-admin@test.com",
        )

        result = access_control_service._validate_actor(
            super_admin.id
        )

        assert result.id == super_admin.id
        assert result.role is Role.SUPER_ADMIN
        assert result.is_active is True

    def test_rejects_inactive_super_admin(
        self,
        app,
        make_user,
        db_session,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="inactive-super-admin@test.com",
            is_active=False,
        )

        db_session.commit()

        with pytest.raises(
            ValidationError,
            match="Authenticated administrator is inactive",
        ):
            access_control_service._validate_actor(
                super_admin.id
            )

    @pytest.mark.parametrize(
        "role",
        [
            Role.ADMIN,
            Role.PATIENT,
            Role.DOCTOR,
            Role.NURSE,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
            Role.RECEPTIONIST,
            Role.ACCOUNTANT,
            Role.PARAMEDIC,
            Role.OTHER,
            Role.DRIVER,
            Role.EMT,
            Role.AMBULANCE_DISPATCHER,
            Role.AMBULANCE_COORDINATOR,
        ],
    )
    def test_rejects_non_super_admin_roles(
        self,
        app,
        user,
        db_session,
        role,
    ):
        user.role = role
        user.is_active = True
        db_session.commit()

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service._validate_actor(
                user.id
            )

    def test_rejects_missing_actor(
        self,
        app,
    ):
        with pytest.raises(
            NotFoundError,
            match=r"User 999999 not found",
        ):
            access_control_service._validate_actor(
                999999
            )

    @pytest.mark.parametrize(
        "actor_id",
        [
            0,
            -1,
            None,
            True,
            False,
            "1",
        ],
    )
    def test_rejects_invalid_actor_id(
        self,
        app,
        actor_id,
    ):
        with pytest.raises(
            ValidationError,
            match="User ID must be a positive integer",
        ):
            access_control_service._validate_actor(
                actor_id
            )


# ============================================================================
# CLINIC VALIDATION
# ============================================================================


class TestValidateSameClinic:
    def test_super_admin_bypasses_clinic_check(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="scope-super@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="scope-target@test.com",
        )

        access_control_service._validate_same_clinic(
            actor,
            target,
        )

    def test_super_admin_can_access_target_without_clinic(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="scope-super-no-clinic@test.com",
        )

        target = make_user(
            None,
            role=Role.PATIENT,
            email="scope-target-no-clinic@test.com",
        )

        access_control_service._validate_same_clinic(
            actor,
            target,
        )

    def test_admin_without_clinic_is_rejected_by_helper(
        self,
        app,
        user,
        make_user,
    ):
        user.role = Role.ADMIN
        user.clinic_id = None

        target = make_user(
            None,
            role=Role.PATIENT,
            email="target-no-clinic@test.com",
        )

        with pytest.raises(
            ValidationError,
            match="Administrator must belong to a clinic",
        ):
            access_control_service._validate_same_clinic(
                user,
                target,
            )

    def test_target_without_clinic_is_rejected_for_admin_helper(
        self,
        app,
        user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = User(
            email="temporary-target@test.com",
            role=Role.PATIENT,
            clinic_id=None,
        )

        with pytest.raises(
            ValidationError,
            match="Target user must belong to a clinic",
        ):
            access_control_service._validate_same_clinic(
                user,
                target,
            )

    def test_different_clinics_are_rejected_for_admin_helper(
        self,
        app,
        user,
        make_user,
        make_clinic,
        clinic,
    ):
        second_clinic = make_clinic()

        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            second_clinic,
            role=Role.PATIENT,
            email="different-clinic@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Administrator and target user must belong "
                "to the same clinic"
            ),
        ):
            access_control_service._validate_same_clinic(
                user,
                target,
            )


# ============================================================================
# USER SERIALIZATION
# ============================================================================


class TestSerializeUser:
    def test_serializes_user_to_response_schema(
        self,
        app,
        user,
    ):
        result = access_control_service._serialize_user(
            user
        )

        assert_user_response(
            result,
            user,
        )

    def test_serialized_user_contains_expected_fields(
        self,
        app,
        user,
    ):
        result = access_control_service._serialize_user(
            user
        )

        data = result.model_dump()

        assert set(data.keys()) == {
            "id",
            "email",
            "role",
            "is_active",
            "clinic_id",
        }


# ============================================================================
# ROLE CHANGE PERMISSIONS
# ============================================================================


class TestValidateRoleChangePermissions:
    def test_rejects_non_super_admin_actor(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="regular-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match="Only a super administrator can change user roles",
        ):
            access_control_service._validate_role_change_permissions(
                user,
                target,
                Role.DOCTOR,
            )

    def test_super_admin_cannot_modify_self(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="self-role@test.com",
        )

        with pytest.raises(
            ConflictError,
            match="Super administrators cannot change their own role",
        ):
            access_control_service._validate_role_change_permissions(
                actor,
                actor,
                Role.ADMIN,
            )

    def test_super_admin_cannot_modify_another_super_admin(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="super-role-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="super-role-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot modify another "
                "super administrator"
            ),
        ):
            access_control_service._validate_role_change_permissions(
                actor,
                target,
                Role.ADMIN,
            )

    def test_super_admin_cannot_assign_super_admin(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="super-assign-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="super-assign-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot assign "
                "super administrator privileges"
            ),
        ):
            access_control_service._validate_role_change_permissions(
                actor,
                target,
                Role.SUPER_ADMIN,
            )

    def test_super_admin_can_modify_regular_admin(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="super-admin-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.ADMIN,
            email="regular-admin-target@test.com",
        )

        access_control_service._validate_role_change_permissions(
            actor,
            target,
            Role.DOCTOR,
        )

    @pytest.mark.parametrize(
        "new_role",
        [
            Role.PATIENT,
            Role.DOCTOR,
            Role.NURSE,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
            Role.RECEPTIONIST,
            Role.ACCOUNTANT,
            Role.PARAMEDIC,
            Role.OTHER,
            Role.DRIVER,
            Role.EMT,
            Role.AMBULANCE_DISPATCHER,
            Role.AMBULANCE_COORDINATOR,
            Role.ADMIN,
        ],
    )
    def test_super_admin_can_assign_non_super_admin_roles(
        self,
        app,
        make_user,
        clinic,
        new_role,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email=f"assign-actor-{new_role.value}@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email=f"assign-target-{new_role.value}@test.com",
        )

        access_control_service._validate_role_change_permissions(
            actor,
            target,
            new_role,
        )


# ============================================================================
# STATUS CHANGE PERMISSIONS
# ============================================================================


class TestValidateStatusChangePermissions:
    def test_rejects_non_super_admin_actor(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-regular-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match="Only a super administrator can change user status",
        ):
            access_control_service._validate_status_change_permissions(
                user,
                target,
            )

    def test_super_admin_cannot_modify_self(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-self@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Super administrators cannot change their own "
                "account status"
            ),
        ):
            access_control_service._validate_status_change_permissions(
                actor,
                actor,
            )

    def test_super_admin_cannot_modify_another_super_admin(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-super-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot modify another "
                "super administrator"
            ),
        ):
            access_control_service._validate_status_change_permissions(
                actor,
                target,
            )

    def test_super_admin_can_modify_regular_admin_status(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-super-admin@test.com",
        )

        target = make_user(
            clinic,
            role=Role.ADMIN,
            email="status-regular-admin@test.com",
        )

        access_control_service._validate_status_change_permissions(
            actor,
            target,
        )


# ============================================================================
# GET ACCESS CONTROL USER
# ============================================================================


class TestGetAccessControlUser:
    def test_super_admin_can_get_user_in_any_clinic(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="global-viewer@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="global-target@test.com",
        )

        result = access_control_service.get_access_control_user(
            actor_id=actor.id,
            user_id=target.id,
        )

        assert_user_response(
            result,
            target,
        )

    def test_super_admin_can_get_user_without_clinic(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="global-no-clinic-viewer@test.com",
        )

        target = make_user(
            None,
            role=Role.PATIENT,
            email="global-no-clinic-target@test.com",
        )

        result = access_control_service.get_access_control_user(
            actor_id=actor.id,
            user_id=target.id,
        )

        assert_user_response(
            result,
            target,
        )

    def test_regular_admin_is_denied(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.is_active = True
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="admin-denied-target@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service.get_access_control_user(
                actor_id=user.id,
                user_id=target.id,
            )

    def test_get_rejects_invalid_actor(
        self,
        app,
        user,
    ):
        with pytest.raises(
            ValidationError,
            match="User ID must be a positive integer",
        ):
            access_control_service.get_access_control_user(
                actor_id=0,
                user_id=user.id,
            )

    def test_get_rejects_missing_target(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="missing-target-actor@test.com",
        )

        with pytest.raises(
            NotFoundError,
            match=r"User 999999 not found",
        ):
            access_control_service.get_access_control_user(
                actor_id=actor.id,
                user_id=999999,
            )


# ============================================================================
# LIST ACCESS CONTROL USERS
# ============================================================================


class TestListAccessControlUsers:
    def test_super_admin_lists_users_across_clinics(
        self,
        app,
        make_user,
        make_clinic,
        clinic,
    ):
        second_clinic = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="global-list-admin@test.com",
        )

        clinic_one_user = make_user(
            clinic,
            role=Role.PATIENT,
            email="global-clinic-one@test.com",
        )

        clinic_two_user = make_user(
            second_clinic,
            role=Role.DOCTOR,
            email="global-clinic-two@test.com",
        )

        no_clinic_user = make_user(
            None,
            role=Role.PATIENT,
            email="global-no-clinic@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(),
            )
        )

        ids = [item.id for item in result]

        assert clinic_one_user.id in ids
        assert clinic_two_user.id in ids
        assert no_clinic_user.id in ids
        assert actor.id in ids

        assert total == 4

    def test_regular_admin_is_denied(
        self,
        app,
        user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.is_active = True
        user.clinic_id = clinic.id

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service.list_access_control_users(
                actor_id=user.id,
                query=make_query(),
            )

    def test_inactive_super_admin_is_denied(
        self,
        app,
        make_user,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="inactive-list-admin@test.com",
            is_active=False,
        )

        db_session.commit()

        with pytest.raises(
            ValidationError,
            match="Authenticated administrator is inactive",
        ):
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(),
            )

    def test_filters_by_role(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-filter-actor@test.com",
        )

        patient = make_user(
            clinic,
            role=Role.PATIENT,
            email="filter-patient@test.com",
        )

        doctor = make_user(
            clinic,
            role=Role.DOCTOR,
            email="filter-doctor@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    role=Role.DOCTOR,
                ),
            )
        )

        ids = [item.id for item in result]

        assert doctor.id in ids
        assert patient.id not in ids
        assert actor.id not in ids
        assert total == 1

    def test_filters_by_active_status(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="active-filter-actor@test.com",
        )

        active_user = make_user(
            clinic,
            role=Role.PATIENT,
            email="active-filter@test.com",
        )

        inactive_user = make_user(
            clinic,
            role=Role.PATIENT,
            email="inactive-filter@test.com",
            is_active=False,
        )

        db_session.commit()

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    is_active=True,
                ),
            )
        )

        ids = [item.id for item in result]

        assert active_user.id in ids
        assert inactive_user.id not in ids
        assert actor.id in ids
        assert total == 2

    def test_filters_by_role_and_status_together(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="combined-filter-actor@test.com",
        )

        active_doctor = make_user(
            clinic,
            role=Role.DOCTOR,
            email="active-doctor-filter@test.com",
        )

        inactive_doctor = make_user(
            clinic,
            role=Role.DOCTOR,
            email="inactive-doctor-filter@test.com",
            is_active=False,
        )

        active_patient = make_user(
            clinic,
            role=Role.PATIENT,
            email="active-patient-filter@test.com",
        )

        db_session.commit()

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    role=Role.DOCTOR,
                    is_active=True,
                ),
            )
        )

        ids = [item.id for item in result]

        assert active_doctor.id in ids
        assert inactive_doctor.id not in ids
        assert active_patient.id not in ids
        assert actor.id not in ids
        assert total == 1

    def test_list_is_deterministically_ordered_by_id(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="order-actor@test.com",
        )

        first = make_user(
            None,
            role=Role.PATIENT,
            email="order-first@test.com",
        )

        second = make_user(
            None,
            role=Role.PATIENT,
            email="order-second@test.com",
        )

        third = make_user(
            None,
            role=Role.PATIENT,
            email="order-third@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(),
            )
        )

        ids = [item.id for item in result]

        assert ids == sorted(ids)
        assert total == 4
        assert actor.id in ids
        assert first.id in ids
        assert second.id in ids
        assert third.id in ids

    def test_paginates_results(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="pagination-actor@test.com",
        )

        created_users = [
            make_user(
                None,
                role=Role.PATIENT,
                email=f"pagination-{index}@test.com",
            )
            for index in range(1, 8)
        ]

        result_page_one, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    page=1,
                    per_page=3,
                ),
            )
        )

        result_page_two, total_again = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    page=2,
                    per_page=3,
                ),
            )
        )

        page_one_ids = [
            item.id
            for item in result_page_one
        ]

        page_two_ids = [
            item.id
            for item in result_page_two
        ]

        expected_ids = {
            actor.id,
            *[
                created.id
                for created in created_users
            ],
        }

        assert len(result_page_one) == 3
        assert len(result_page_two) == 3
        assert total == 8
        assert total_again == total

        assert not set(page_one_ids).intersection(
            page_two_ids
        )

        assert page_one_ids == sorted(
            page_one_ids
        )
        assert page_two_ids == sorted(
            page_two_ids
        )

        assert set(page_one_ids).issubset(
            expected_ids
        )
        assert set(page_two_ids).issubset(
            expected_ids
        )

    def test_empty_page_returns_empty_list_and_total(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="empty-page-actor@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=actor.id,
                query=make_query(
                    page=999,
                    per_page=50,
                ),
            )
        )

        assert result == []
        assert total == 1


# ============================================================================
# CHANGE USER ROLE
# ============================================================================


class TestChangeUserRole:
    def test_super_admin_changes_regular_user_role(
        self,
        app,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-change-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-change@test.com",
        )

        original_token_version = (
            target.token_version
        )

        audit = Mock()

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            audit,
        )

        result = access_control_service.change_user_role(
            actor_id=actor.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
            reason="  Clinical promotion  ",
        )

        assert result.previous_role is Role.PATIENT
        assert result.new_role is Role.DOCTOR
        assert result.reason == "Clinical promotion"

        assert result.user.id == target.id
        assert result.user.role is Role.DOCTOR

        db_session.refresh(target)

        assert target.role is Role.DOCTOR
        assert target.token_version == (
            original_token_version + 1
        )

        audit.assert_called_once()

        call = audit.call_args.kwargs

        assert call["action"] is AuditAction.UPDATE
        assert call["entity_type"] == "User"
        assert call["entity_id"] == target.id
        assert call["user_id"] == actor.id

        assert call["old_value"] == {
            "role": Role.PATIENT.value,
            "token_version": original_token_version,
        }

        assert call["new_value"] == {
            "role": Role.DOCTOR.value,
            "token_version": original_token_version + 1,
            "reason": "Clinical promotion",
        }

    def test_role_change_without_reason(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-no-reason-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-no-reason@test.com",
        )

        result = access_control_service.change_user_role(
            actor_id=actor.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
        )

        assert result.reason is None
        assert result.previous_role is Role.PATIENT
        assert result.new_role is Role.DOCTOR

    def test_rejects_invalid_new_role(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="invalid-role-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="invalid-role@test.com",
        )

        with pytest.raises(
            ValidationError,
            match="Invalid user role",
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=target.id,
                new_role="doctor",
            )

    def test_rejects_self_role_change(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="self-role-change@test.com",
        )

        with pytest.raises(
            ConflictError,
            match="Super administrators cannot change their own role",
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=actor.id,
                new_role=Role.ADMIN,
            )

    def test_rejects_same_existing_role(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="same-role-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="same-role@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=r"User already has role 'doctor'",
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
            )

    def test_regular_admin_is_denied(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.is_active = True
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="admin-denied-role@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
            )

    def test_super_admin_can_demote_admin(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="demote-super@test.com",
        )

        target = make_user(
            clinic,
            role=Role.ADMIN,
            email="demote-admin@test.com",
        )

        original_version = (
            target.token_version
        )

        result = access_control_service.change_user_role(
            actor_id=actor.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
            reason="Administrative reassignment",
        )

        assert result.previous_role is Role.ADMIN
        assert result.new_role is Role.DOCTOR
        assert result.reason == "Administrative reassignment"

        db_session.refresh(target)

        assert target.role is Role.DOCTOR
        assert target.token_version == (
            original_version + 1
        )

    def test_super_admin_cannot_modify_super_admin(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="modify-super-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="modify-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot modify another "
                "super administrator"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=target.id,
                new_role=Role.ADMIN,
            )

    def test_super_admin_cannot_create_super_admin(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="create-super-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="create-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot assign "
                "super administrator privileges"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=target.id,
                new_role=Role.SUPER_ADMIN,
            )

    def test_role_change_increments_token_version(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-token-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-token-version@test.com",
        )

        original_version = (
            target.token_version
        )

        access_control_service.change_user_role(
            actor_id=actor.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
        )

        db_session.refresh(target)

        assert target.token_version == (
            original_version + 1
        )

    def test_role_change_is_atomic_when_audit_log_fails(
        self,
        app,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-rollback-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-rollback-target@test.com",
        )

        original_role = target.role
        original_version = target.token_version

        db_session.commit()

        def fail_audit(*args, **kwargs):
            raise RuntimeError(
                "audit failure"
            )

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            fail_audit,
        )

        with pytest.raises(
            RuntimeError,
            match="audit failure",
        ):
            access_control_service.change_user_role(
                actor_id=actor.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
                reason="Rollback test",
            )

        db_session.refresh(target)

        assert target.role is original_role
        assert target.token_version == original_version


# ============================================================================
# CHANGE USER STATUS
# ============================================================================


class TestChangeUserStatus:
    def test_super_admin_deactivates_regular_user(
        self,
        app,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-change-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-change@test.com",
        )

        original_version = (
            target.token_version
        )

        audit = Mock()

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            audit,
        )

        result = access_control_service.change_user_status(
            actor_id=actor.id,
            user_id=target.id,
            is_active=False,
            reason="  Access suspended  ",
        )

        assert result.previous_status is True
        assert result.new_status is False
        assert result.reason == "Access suspended"

        assert result.user.id == target.id
        assert result.user.is_active is False

        db_session.refresh(target)

        assert target.is_active is False
        assert target.token_version == (
            original_version + 1
        )

        audit.assert_called_once()

        call = audit.call_args.kwargs

        assert call["action"] is AuditAction.UPDATE
        assert call["entity_type"] == "User"
        assert call["entity_id"] == target.id
        assert call["user_id"] == actor.id

        assert call["old_value"] == {
            "is_active": True,
            "token_version": original_version,
        }

        assert call["new_value"] == {
            "is_active": False,
            "token_version": original_version + 1,
            "reason": "Access suspended",
        }

    def test_super_admin_reactivates_regular_user(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-reactivate-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            is_active=False,
            email="status-reactivate@test.com",
        )

        original_version = (
            target.token_version
        )

        result = access_control_service.change_user_status(
            actor_id=actor.id,
            user_id=target.id,
            is_active=True,
        )

        assert result.previous_status is False
        assert result.new_status is True
        assert result.reason is None

        db_session.refresh(target)

        assert target.is_active is True
        assert target.token_version == (
            original_version + 1
        )

    def test_rejects_non_boolean_status(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="invalid-status-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="invalid-status@test.com",
        )

        with pytest.raises(
            ValidationError,
            match="is_active must be a boolean",
        ):
            access_control_service.change_user_status(
                actor_id=actor.id,
                user_id=target.id,
                is_active=1,
            )

    def test_rejects_self_status_change(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-self-change@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Super administrators cannot change their own "
                "account status"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=actor.id,
                user_id=actor.id,
                is_active=False,
            )

    def test_rejects_same_existing_status(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="same-status-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            is_active=True,
            email="same-status@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "User already has the requested account status"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=actor.id,
                user_id=target.id,
                is_active=True,
            )

    def test_regular_admin_is_denied(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.is_active = True
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="admin-denied-status@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=user.id,
                user_id=target.id,
                is_active=False,
            )

    def test_super_admin_can_change_regular_admin_status(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-global-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.ADMIN,
            is_active=True,
            email="status-global-target@test.com",
        )

        original_version = (
            target.token_version
        )

        result = access_control_service.change_user_status(
            actor_id=actor.id,
            user_id=target.id,
            is_active=False,
            reason="Clinic administration review",
        )

        assert result.previous_status is True
        assert result.new_status is False
        assert result.reason == (
            "Clinic administration review"
        )

        db_session.refresh(target)

        assert target.is_active is False
        assert target.token_version == (
            original_version + 1
        )

    def test_super_admin_cannot_change_super_admin_status(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-super-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            is_active=True,
            email="status-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot modify another "
                "super administrator"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=actor.id,
                user_id=target.id,
                is_active=False,
            )

    def test_status_change_increments_token_version(
        self,
        app,
        make_user,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-token-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            is_active=True,
            email="status-token-version@test.com",
        )

        original_version = (
            target.token_version
        )

        access_control_service.change_user_status(
            actor_id=actor.id,
            user_id=target.id,
            is_active=False,
        )

        db_session.refresh(target)

        assert target.token_version == (
            original_version + 1
        )

    def test_status_change_without_reason(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-no-reason-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-no-reason@test.com",
        )

        result = access_control_service.change_user_status(
            actor_id=actor.id,
            user_id=target.id,
            is_active=False,
        )

        assert result.reason is None

    def test_status_change_is_atomic_when_audit_log_fails(
        self,
        app,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-rollback-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            is_active=True,
            email="status-rollback-target@test.com",
        )

        original_status = target.is_active
        original_version = target.token_version

        db_session.commit()

        def fail_audit(*args, **kwargs):
            raise RuntimeError(
                "audit failure"
            )

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            fail_audit,
        )

        with pytest.raises(
            RuntimeError,
            match="audit failure",
        ):
            access_control_service.change_user_status(
                actor_id=actor.id,
                user_id=target.id,
                is_active=False,
                reason="Rollback test",
            )

        db_session.refresh(target)

        assert target.is_active is original_status
        assert target.token_version == original_version


# ============================================================================
# CLINIC TRANSFER VALIDATION
# ============================================================================


class TestValidateClinicTransferPermissions:
    def test_non_super_admin_is_rejected(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="transfer-admin-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Only a super administrator can transfer users "
                "between clinics"
            ),
        ):
            access_control_service._validate_clinic_transfer_permissions(
                user,
                target,
            )

    def test_super_admin_cannot_transfer_self(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-self@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Super administrators cannot transfer their own account"
            ),
        ):
            access_control_service._validate_clinic_transfer_permissions(
                actor,
                actor,
            )

    def test_super_admin_cannot_transfer_another_super_admin(
        self,
        app,
        make_user,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-super-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot transfer another "
                "super administrator"
            ),
        ):
            access_control_service._validate_clinic_transfer_permissions(
                actor,
                target,
            )

    def test_super_admin_cannot_transfer_patient_account(
        self,
        app,
        make_user,
        make_patient,
        clinic,
        db_session,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-patient-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="transfer-patient-target@test.com",
        )

        patient = make_patient(
            clinic,
            patient_number="TRANSFER-PATIENT-001",
        )

        patient.user_id = target.id
        db_session.flush()

        assert target.patient is not None

        with pytest.raises(
            ConflictError,
            match=(
                "Patient accounts cannot be transferred "
                "through access control"
            ),
        ):
            access_control_service._validate_clinic_transfer_permissions(
                actor,
                target,
            )

    def test_super_admin_can_transfer_regular_user(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-allowed-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="transfer-allowed-target@test.com",
        )

        access_control_service._validate_clinic_transfer_permissions(
            actor,
            target,
        )


# ============================================================================
# ACTIVE DESTINATION CLINIC
# ============================================================================


class TestGetActiveClinic:
    def test_returns_active_clinic(
        self,
        app,
        clinic,
    ):
        result = access_control_service._get_active_clinic(
            clinic.id
        )

        assert result.id == clinic.id
        assert result.status is ClinicStatus.ACTIVE

    @pytest.mark.parametrize(
        "clinic_id",
        [
            0,
            -1,
            None,
            True,
            False,
            "1",
        ],
    )
    def test_rejects_invalid_destination_clinic_id(
        self,
        app,
        clinic_id,
    ):
        with pytest.raises(
            ValidationError,
            match=(
                "Destination clinic ID must be a positive integer"
            ),
        ):
            access_control_service._get_active_clinic(
                clinic_id
            )

    def test_raises_not_found_for_missing_destination_clinic(
        self,
        app,
    ):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 999999 not found",
        ):
            access_control_service._get_active_clinic(
                999999
            )

    def test_rejects_suspended_destination_clinic(
        self,
        app,
        suspended_clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Destination clinic is not active",
        ):
            access_control_service._get_active_clinic(
                suspended_clinic.id
            )


# ============================================================================
# TRANSFER USER CLINIC
# ============================================================================


class TestTransferUserClinic:
    def test_super_admin_transfers_regular_user(
        self,
        app,
        make_user,
        make_clinic,
        clinic,
        db_session,
        monkeypatch,
    ):
        second_clinic = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="transfer-target@test.com",
        )

        original_version = target.token_version

        audit = Mock()

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            audit,
        )

        result = access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=second_clinic.id,
            reason="  Staff reassignment  ",
        )

        assert result.user.id == target.id
        assert result.previous_clinic_id == clinic.id
        assert result.new_clinic_id == second_clinic.id
        assert result.reason == "Staff reassignment"

        db_session.refresh(target)

        assert target.clinic_id == second_clinic.id
        assert target.token_version == (
            original_version + 1
        )

        audit.assert_called_once()

        call = audit.call_args.kwargs

        assert call["action"] is AuditAction.UPDATE
        assert call["entity_type"] == "User"
        assert call["entity_id"] == target.id
        assert call["user_id"] == actor.id

        assert call["old_value"] == {
            "clinic_id": clinic.id,
            "staff_clinic_id": None,
            "token_version": original_version,
        }

        assert call["new_value"] == {
            "clinic_id": second_clinic.id,
            "staff_clinic_id": None,
            "token_version": original_version + 1,
            "reason": "Staff reassignment",
        }

    def test_transfers_user_without_existing_clinic(
        self,
        app,
        make_user,
        make_clinic,
        db_session,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-no-clinic-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.DOCTOR,
            email="transfer-no-clinic-target@test.com",
        )

        original_version = target.token_version

        result = access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=destination.id,
        )

        assert result.previous_clinic_id is None
        assert result.new_clinic_id == destination.id
        assert result.reason is None

        db_session.refresh(target)

        assert target.clinic_id == destination.id
        assert target.token_version == (
            original_version + 1
        )

    def test_transfers_staff_user_and_updates_staff_clinic(
        self,
        app,
        make_user,
        make_staff,
        make_clinic,
        clinic,
        db_session,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="staff-transfer-actor@test.com",
        )

        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            user_overrides={
                "email": "staff-transfer-target@test.com",
            },
        )

        target = staff.user

        original_version = target.token_version

        result = access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=destination.id,
            reason="Doctor reassigned to new clinic",
        )

        assert result.user.id == target.id
        assert result.previous_clinic_id == clinic.id
        assert result.new_clinic_id == destination.id

        db_session.refresh(target)
        db_session.refresh(staff)

        assert target.clinic_id == destination.id
        assert staff.clinic_id == destination.id
        assert target.token_version == (
            original_version + 1
        )

    def test_rejects_admin_transfer(
        self,
        app,
        user,
        make_user,
        make_clinic,
        clinic,
    ):
        destination = make_clinic()

        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="admin-transfer-target@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Only a super administrator can access "
                "access-control administration"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=user.id,
                user_id=target.id,
                destination_clinic_id=destination.id,
            )

    def test_rejects_self_transfer(
        self,
        app,
        make_user,
        make_clinic,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="self-transfer-actor@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Super administrators cannot transfer their own account"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=actor.id,
                destination_clinic_id=destination.id,
            )

    def test_rejects_super_admin_target(
        self,
        app,
        make_user,
        make_clinic,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="protected-transfer-actor@test.com",
        )

        target = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="protected-transfer-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "A super administrator cannot transfer another "
                "super administrator"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=destination.id,
            )

    def test_rejects_patient_account(
        self,
        app,
        make_user,
        make_patient,
        make_clinic,
        clinic,
        db_session,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="patient-transfer-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="patient-transfer-target@test.com",
        )

        patient = make_patient(
            clinic,
            patient_number="PATIENT-TRANSFER-001",
        )

        patient.user_id = target.id
        db_session.flush()

        with pytest.raises(
            ConflictError,
            match=(
                "Patient accounts cannot be transferred "
                "through access control"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=destination.id,
            )

    def test_rejects_missing_destination_clinic(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="missing-destination-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="missing-destination-target@test.com",
        )

        with pytest.raises(
            NotFoundError,
            match=r"Clinic 999999 not found",
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=999999,
            )

    def test_rejects_inactive_destination_clinic(
        self,
        app,
        make_user,
        suspended_clinic,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="inactive-destination-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="inactive-destination-target@test.com",
        )

        with pytest.raises(
            ValidationError,
            match="Destination clinic is not active",
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=suspended_clinic.id,
            )

    def test_rejects_same_destination_clinic(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="same-destination-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="same-destination-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "User already belongs to the destination clinic"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=clinic.id,
            )

    @pytest.mark.parametrize(
        "destination_clinic_id",
        [
            0,
            -1,
            None,
            True,
            False,
            "1",
        ],
    )
    def test_rejects_invalid_destination_clinic_id(
        self,
        app,
        make_user,
        clinic,
        destination_clinic_id,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email=(
                f"invalid-destination-actor-"
                f"{str(destination_clinic_id)}@test.com"
            ),
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email=(
                f"invalid-destination-target-"
                f"{str(destination_clinic_id)}@test.com"
            ),
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Destination clinic ID must be a positive integer"
            ),
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=destination_clinic_id,
            )

    def test_rejects_missing_target_user(
        self,
        app,
        make_user,
        clinic,
    ):
        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="missing-target-actor@test.com",
        )

        with pytest.raises(
            NotFoundError,
            match=r"User 999999 not found",
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=999999,
                destination_clinic_id=clinic.id,
            )

    def test_rejects_invalid_actor_id(
        self,
        app,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="User ID must be a positive integer",
        ):
            access_control_service.transfer_user_clinic(
                actor_id=0,
                user_id=1,
                destination_clinic_id=clinic.id,
            )

    def test_transfer_without_reason(
        self,
        app,
        make_user,
        make_clinic,
        clinic,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-no-reason-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="transfer-no-reason-target@test.com",
        )

        result = access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=destination.id,
        )

        assert result.reason is None
        assert result.previous_clinic_id == clinic.id
        assert result.new_clinic_id == destination.id

    def test_transfer_invalidates_existing_token_version(
        self,
        app,
        make_user,
        make_clinic,
        clinic,
        db_session,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-token-actor@test.com",
        )

        target = make_user(
            clinic,
            role=Role.DOCTOR,
            email="transfer-token-target@test.com",
        )

        original_version = target.token_version

        access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=destination.id,
        )

        db_session.refresh(target)

        assert target.token_version == (
            original_version + 1
        )

    def test_transfer_is_atomic_when_audit_log_fails(
        self,
        app,
        make_user,
        make_staff,
        make_clinic,
        clinic,
        db_session,
        monkeypatch,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-rollback-actor@test.com",
        )

        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            user_overrides={
                "email": "transfer-rollback-target@test.com",
            },
        )

        target = staff.user

        original_clinic_id = target.clinic_id
        original_staff_clinic_id = staff.clinic_id
        original_version = target.token_version

        db_session.commit()

        def fail_audit(*args, **kwargs):
            raise RuntimeError(
                "audit failure"
            )

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            fail_audit,
        )

        with pytest.raises(
            RuntimeError,
            match="audit failure",
        ):
            access_control_service.transfer_user_clinic(
                actor_id=actor.id,
                user_id=target.id,
                destination_clinic_id=destination.id,
                reason="Rollback test",
            )

        db_session.refresh(target)
        db_session.refresh(staff)

        assert target.clinic_id == original_clinic_id
        assert staff.clinic_id == original_staff_clinic_id
        assert target.token_version == original_version

    def test_transfer_audit_contains_staff_clinic_state(
        self,
        app,
        make_user,
        make_staff,
        make_clinic,
        clinic,
        monkeypatch,
    ):
        destination = make_clinic()

        actor = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="transfer-audit-staff-actor@test.com",
        )

        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
            user_overrides={
                "email": "transfer-audit-staff-target@test.com",
            },
        )

        target = staff.user

        original_version = target.token_version
        audit = Mock()

        monkeypatch.setattr(
            access_control_service,
            "create_audit_log",
            audit,
        )

        access_control_service.transfer_user_clinic(
            actor_id=actor.id,
            user_id=target.id,
            destination_clinic_id=destination.id,
            reason="Cross-clinic reassignment",
        )

        audit.assert_called_once()

        call = audit.call_args.kwargs

        assert call["old_value"] == {
            "clinic_id": clinic.id,
            "staff_clinic_id": clinic.id,
            "token_version": original_version,
        }

        assert call["new_value"] == {
            "clinic_id": destination.id,
            "staff_clinic_id": destination.id,
            "token_version": original_version + 1,
            "reason": "Cross-clinic reassignment",
        }