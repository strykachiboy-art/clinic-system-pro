from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.auth.user.models.user_model import User
from app.core.enums.audit_enums import AuditAction
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
    def test_accepts_active_admin(
        self,
        app,
        user,
    ):
        user.role = Role.ADMIN
        user.is_active = True

        result = access_control_service._validate_actor(
            user.id
        )

        assert result.id == user.id
        assert result.role is Role.ADMIN

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

    def test_rejects_inactive_admin(
        self,
        app,
        user,
        db_session,
    ):
        user.role = Role.ADMIN
        user.is_active = False
        db_session.commit()

        with pytest.raises(
            ValidationError,
            match="Authenticated administrator is inactive",
        ):
            access_control_service._validate_actor(
                user.id
            )

    @pytest.mark.parametrize(
        "role",
        [
            Role.PATIENT,
            Role.DOCTOR,
            Role.NURSE,
            Role.PHARMACIST,
        ],
    )
    def test_rejects_non_administrator_roles(
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
            match="Authenticated user is not authorized",
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


# ============================================================================
# CLINIC VALIDATION
# ============================================================================


class TestValidateSameClinic:
    def test_admin_and_target_in_same_clinic_are_allowed(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="same-clinic@test.com",
        )

        access_control_service._validate_same_clinic(
            user,
            target,
        )

    def test_super_admin_bypasses_clinic_check(
        self,
        app,
        make_user,
        clinic,
    ):
        super_admin = make_user(
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
            super_admin,
            target,
        )

    def test_admin_without_clinic_is_rejected(
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

    def test_target_without_clinic_is_rejected_for_admin(
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

    def test_different_clinics_are_rejected(
        self,
        app,
        user,
        make_clinic,
        make_user,
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
    def test_rejects_self_role_change(
        self,
        app,
        user,
    ):
        user.role = Role.ADMIN

        with pytest.raises(
            ConflictError,
            match="Users cannot change their own role",
        ):
            access_control_service._validate_role_change_permissions(
                user,
                user,
                Role.PATIENT,
            )

    @pytest.mark.parametrize(
        "target_role",
        [
            Role.ADMIN,
            Role.SUPER_ADMIN,
        ],
    )
    def test_admin_cannot_modify_administrator_targets(
        self,
        app,
        user,
        make_user,
        clinic,
        target_role,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=target_role,
            email=f"target-{target_role.value}@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot modify another administrator"
            ),
        ):
            access_control_service._validate_role_change_permissions(
                user,
                target,
                Role.PATIENT,
            )

    @pytest.mark.parametrize(
        "new_role",
        [
            Role.ADMIN,
            Role.SUPER_ADMIN,
        ],
    )
    def test_admin_cannot_assign_administrator_privileges(
        self,
        app,
        user,
        make_user,
        clinic,
        new_role,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email=f"assignment-{new_role.value}@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot assign administrator privileges"
            ),
        ):
            access_control_service._validate_role_change_permissions(
                user,
                target,
                new_role,
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

    def test_admin_can_change_regular_user_role(
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

        access_control_service._validate_role_change_permissions(
            user,
            target,
            Role.DOCTOR,
        )


# ============================================================================
# STATUS CHANGE PERMISSIONS
# ============================================================================


class TestValidateStatusChangePermissions:
    def test_rejects_self_status_change(
        self,
        app,
        user,
    ):
        user.role = Role.ADMIN

        with pytest.raises(
            ConflictError,
            match="Users cannot change their own account status",
        ):
            access_control_service._validate_status_change_permissions(
                user,
                user,
            )

    @pytest.mark.parametrize(
        "target_role",
        [
            Role.ADMIN,
            Role.SUPER_ADMIN,
        ],
    )
    def test_admin_cannot_modify_administrator_status(
        self,
        app,
        user,
        make_user,
        clinic,
        target_role,
    ):
        user.role = Role.ADMIN

        target = make_user(
            clinic,
            role=target_role,
            email=f"status-target-{target_role.value}@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot modify another administrator"
            ),
        ):
            access_control_service._validate_status_change_permissions(
                user,
                target,
            )

    def test_super_admin_cannot_modify_another_super_admin_status(
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

    def test_admin_can_modify_regular_user_status(
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
            email="status-regular-user@test.com",
        )

        access_control_service._validate_status_change_permissions(
            user,
            target,
        )


# ============================================================================
# GET ACCESS CONTROL USER
# ============================================================================


class TestGetAccessControlUser:
    def test_admin_can_get_same_clinic_user(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="view-target@test.com",
        )

        result = access_control_service.get_access_control_user(
            actor_id=user.id,
            user_id=target.id,
        )

        assert_user_response(
            result,
            target,
        )

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

    def test_admin_cannot_get_user_from_other_clinic(
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
            email="cross-clinic-target@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Administrator and target user must belong "
                "to the same clinic"
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
        user,
    ):
        user.role = Role.ADMIN

        with pytest.raises(
            NotFoundError,
            match=r"User 999999 not found",
        ):
            access_control_service.get_access_control_user(
                actor_id=user.id,
                user_id=999999,
            )


# ============================================================================
# LIST ACCESS CONTROL USERS
# ============================================================================


class TestListAccessControlUsers:
    def test_admin_lists_only_same_clinic_users(
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

        same_one = make_user(
            clinic,
            role=Role.PATIENT,
            email="list-same-one@test.com",
        )

        same_two = make_user(
            clinic,
            role=Role.DOCTOR,
            email="list-same-two@test.com",
        )

        other_clinic_user = make_user(
            second_clinic,
            role=Role.PATIENT,
            email="list-other-clinic@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=user.id,
                query=make_query(),
            )
        )

        ids = [item.id for item in result]

        assert user.id in ids
        assert same_one.id in ids
        assert same_two.id in ids
        assert other_clinic_user.id not in ids

        assert total == 3

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

    def test_admin_without_clinic_cannot_list(
        self,
        app,
        user,
    ):
        user.role = Role.ADMIN
        user.clinic_id = None

        with pytest.raises(
            ValidationError,
            match="Administrator must belong to a clinic",
        ):
            access_control_service.list_access_control_users(
                actor_id=user.id,
                query=make_query(),
            )

    def test_filters_by_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                query=make_query(
                    role=Role.DOCTOR,
                ),
            )
        )

        ids = [item.id for item in result]

        assert doctor.id in ids
        assert patient.id not in ids
        assert user.id not in ids
        assert total == 1

    def test_filters_by_active_status(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                query=make_query(
                    is_active=True,
                ),
            )
        )

        ids = [item.id for item in result]

        assert active_user.id in ids
        assert inactive_user.id not in ids
        assert user.id in ids
        assert total == 2

    def test_filters_by_role_and_status_together(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
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
        assert total == 1

    def test_list_is_deterministically_ordered_by_id(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        first = make_user(
            clinic,
            role=Role.PATIENT,
            email="order-first@test.com",
        )

        second = make_user(
            clinic,
            role=Role.PATIENT,
            email="order-second@test.com",
        )

        third = make_user(
            clinic,
            role=Role.PATIENT,
            email="order-third@test.com",
        )

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=user.id,
                query=make_query(),
            )
        )

        ids = [item.id for item in result]

        assert ids == sorted(ids)
        assert total == 4
        assert first.id in ids
        assert second.id in ids
        assert third.id in ids

    def test_paginates_results(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        created_users = [
            make_user(
                clinic,
                role=Role.PATIENT,
                email=f"pagination-{index}@test.com",
            )
            for index in range(1, 8)
        ]

        result_page_one, total = (
            access_control_service.list_access_control_users(
                actor_id=user.id,
                query=make_query(
                    page=1,
                    per_page=3,
                ),
            )
        )

        result_page_two, total_again = (
            access_control_service.list_access_control_users(
                actor_id=user.id,
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
            user.id,
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
        user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        result, total = (
            access_control_service.list_access_control_users(
                actor_id=user.id,
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
    def test_admin_changes_regular_user_role(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
            actor_id=user.id,
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
        assert call["user_id"] == user.id

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
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-no-reason@test.com",
        )

        result = access_control_service.change_user_role(
            actor_id=user.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
        )

        assert result.reason is None
        assert result.previous_role is Role.PATIENT
        assert result.new_role is Role.DOCTOR

    def test_rejects_invalid_new_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                user_id=target.id,
                new_role="doctor",
            )

    def test_rejects_self_role_change(
        self,
        app,
        user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        with pytest.raises(
            ConflictError,
            match="Users cannot change their own role",
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=user.id,
                new_role=Role.DOCTOR,
            )

    def test_rejects_same_existing_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
            )

    def test_admin_cannot_change_admin_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.ADMIN,
            email="admin-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot modify another administrator"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
            )

    def test_admin_cannot_grant_admin_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="grant-admin@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot assign administrator privileges"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.ADMIN,
            )

    def test_admin_cannot_grant_super_admin_role(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="grant-super-admin@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot assign administrator privileges"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.SUPER_ADMIN,
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

    def test_admin_cannot_change_user_in_other_clinic(
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
            email="role-other-clinic@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Administrator and target user must belong "
                "to the same clinic"
            ),
        ):
            access_control_service.change_user_role(
                actor_id=user.id,
                user_id=target.id,
                new_role=Role.DOCTOR,
            )

    def test_role_change_increments_token_version(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-token-version@test.com",
        )

        original_version = (
            target.token_version
        )

        access_control_service.change_user_role(
            actor_id=user.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
        )

        db_session.refresh(target)

        assert target.token_version == (
            original_version + 1
        )


# ============================================================================
# CHANGE USER STATUS
# ============================================================================


class TestChangeUserStatus:
    def test_admin_deactivates_regular_user(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
            actor_id=user.id,
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
        assert call["user_id"] == user.id

        assert call["old_value"] == {
            "is_active": True,
            "token_version": original_version,
        }

        assert call["new_value"] == {
            "is_active": False,
            "token_version": original_version + 1,
            "reason": "Access suspended",
        }

    def test_admin_reactivates_regular_user(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
            actor_id=user.id,
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
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                user_id=target.id,
                is_active=1,
            )

    def test_rejects_self_status_change(
        self,
        app,
        user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        with pytest.raises(
            ConflictError,
            match="Users cannot change their own account status",
        ):
            access_control_service.change_user_status(
                actor_id=user.id,
                user_id=user.id,
                is_active=False,
            )

    def test_rejects_same_existing_status(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
                actor_id=user.id,
                user_id=target.id,
                is_active=True,
            )

    def test_admin_cannot_change_admin_status(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.ADMIN,
            email="status-admin-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot modify another administrator"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=user.id,
                user_id=target.id,
                is_active=False,
            )

    def test_admin_cannot_change_super_admin_status(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.SUPER_ADMIN,
            email="status-super-target@test.com",
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Administrator cannot modify another administrator"
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
            email="status-super-target2@test.com",
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

    def test_admin_cannot_change_user_in_other_clinic_status(
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
            email="status-other-clinic@test.com",
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Administrator and target user must belong "
                "to the same clinic"
            ),
        ):
            access_control_service.change_user_status(
                actor_id=user.id,
                user_id=target.id,
                is_active=False,
            )

    def test_status_change_increments_token_version(
        self,
        app,
        user,
        make_user,
        clinic,
        db_session,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

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
            actor_id=user.id,
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
        user,
        make_user,
        clinic,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-no-reason@test.com",
        )

        result = access_control_service.change_user_status(
            actor_id=user.id,
            user_id=target.id,
            is_active=False,
        )

        assert result.reason is None