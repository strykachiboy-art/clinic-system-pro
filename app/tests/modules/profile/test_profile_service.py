from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.profile.schemas.profile_schema import (
    ProfileResponseSchema,
)
from app.modules.profile.services import profile_service


# ============================================================================
# TEST CONTEXT
# ============================================================================


@pytest.fixture(autouse=True)
def profile_app_context(app):
    yield


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        True,
        False,
        None,
        "1",
        1.5,
        [],
        {},
    ],
)
def test_validate_user_id_rejects_invalid_values(value):
    with pytest.raises(
        ValidationError,
    ):
        profile_service._validate_user_id(value)


def test_validate_user_id_accepts_positive_integer():
    assert (
        profile_service._validate_user_id(1)
        is None
    )


# ============================================================================
# USER RESOLUTION
# ============================================================================


def test_get_user_returns_active_user(user):
    result = profile_service._get_user(user.id)

    assert result is user


def test_get_user_rejects_missing_user():
    with pytest.raises(
        NotFoundError,
        match="User 999999 not found",
    ):
        profile_service._get_user(999999)


def test_get_user_rejects_inactive_user(
    user,
):
    user.is_active = False

    with pytest.raises(
        ValidationError,
        match="Authenticated user is inactive",
    ):
        profile_service._get_user(user.id)


# ============================================================================
# STAFF RESOLUTION
# ============================================================================


def test_get_staff_for_user_returns_linked_staff(
    staff,
):
    result = profile_service._get_staff_for_user(
        staff.user,
    )

    assert result is staff
    assert result.user_id == staff.user.id


def test_get_staff_for_user_returns_none_when_unlinked(
    user,
):
    result = profile_service._get_staff_for_user(
        user,
    )

    assert result is None


def test_get_staff_for_user_rejects_broken_link():
    user = SimpleNamespace(
        id=1,
        staff=SimpleNamespace(
            id=10,
            user_id=999999,
        ),
    )

    with pytest.raises(
        ConflictError,
        match="is not correctly linked",
    ):
        profile_service._get_staff_for_user(
            user,
        )


# ============================================================================
# CLINIC RESOLUTION
# ============================================================================


def test_get_clinic_for_user_resolves_user_clinic(
    user,
    clinic,
):
    result = profile_service._get_clinic_for_user(
        user,
        None,
    )

    assert result is clinic
    assert result.id == user.clinic_id


def test_get_clinic_for_user_falls_back_to_staff_clinic(
    staff,
    clinic,
):
    staff.user.clinic_id = None

    result = profile_service._get_clinic_for_user(
        staff.user,
        staff,
    )

    assert result is clinic


def test_get_clinic_for_user_returns_none_without_clinic(
    user,
):
    user.clinic_id = None

    result = profile_service._get_clinic_for_user(
        user,
        None,
    )

    assert result is None


def test_get_clinic_for_user_rejects_mismatched_user_and_staff_clinics(
    make_clinic,
    make_staff,
    clinic,
):
    other_clinic = make_clinic(
        name="Other Profile Clinic",
    )

    staff = make_staff(
        clinic,
    )

    staff.clinic_id = other_clinic.id

    with pytest.raises(
        ConflictError,
        match="User and Staff records belong to different clinics",
    ):
        profile_service._get_clinic_for_user(
            staff.user,
            staff,
        )


def test_get_clinic_for_user_rejects_invalid_clinic_id(
    user,
):
    user.clinic_id = 0

    with pytest.raises(
        ValidationError,
        match="Invalid clinic ID",
    ):
        profile_service._get_clinic_for_user(
            user,
            None,
        )


def test_get_clinic_for_user_rejects_missing_clinic(
    user,
):
    user.clinic_id = 999999

    with pytest.raises(
        NotFoundError,
        match="Clinic 999999 not found",
    ):
        profile_service._get_clinic_for_user(
            user,
            None,
        )


# ============================================================================
# ENUM / CHANGE HELPERS
# ============================================================================


def test_enum_value_returns_enum_value():
    from app.core.enums.audit_enums import AuditAction

    assert (
        profile_service._enum_value(
            AuditAction.UPDATE,
        )
        == AuditAction.UPDATE.value
    )


def test_enum_value_returns_plain_value_unchanged():
    value = "unchanged"

    assert (
        profile_service._enum_value(value)
        == value
    )


def test_record_changes_updates_changed_fields():
    obj = type(
        "ProfileObject",
        (),
        {
            "email": "old@example.com",
            "first_name": "Old",
        },
    )()

    old_value, new_value = profile_service._record_changes(
        obj=obj,
        entity_type="User",
        entity_id=1,
        fields={
            "email": "new@example.com",
            "first_name": "New",
        },
    )

    assert old_value == {
        "email": "old@example.com",
        "first_name": "Old",
    }

    assert new_value == {
        "email": "new@example.com",
        "first_name": "New",
    }

    assert obj.email == "new@example.com"
    assert obj.first_name == "New"


def test_record_changes_ignores_unchanged_values():
    obj = type(
        "ProfileObject",
        (),
        {
            "email": "same@example.com",
        },
    )()

    old_value, new_value = profile_service._record_changes(
        obj=obj,
        entity_type="User",
        entity_id=1,
        fields={
            "email": "same@example.com",
        },
    )

    assert old_value == {}
    assert new_value == {}
    assert obj.email == "same@example.com"


# ============================================================================
# GET PROFILE
# ============================================================================


def test_get_profile_returns_aggregated_user_staff_clinic_profile(
    staff,
    clinic,
):
    profile = profile_service.get_profile(
        staff.user.id,
    )

    assert isinstance(
        profile,
        ProfileResponseSchema,
    )

    assert profile.user.id == staff.user.id
    assert profile.user.email == staff.user.email

    assert profile.staff is not None
    assert profile.staff.id == staff.id
    assert profile.staff.user_id == staff.user.id
    assert profile.staff.clinic_id == clinic.id

    assert profile.clinic is not None
    assert profile.clinic.id == clinic.id
    assert profile.clinic.name == clinic.name


def test_get_profile_returns_user_without_staff(
    user,
    clinic,
):
    profile = profile_service.get_profile(
        user.id,
    )

    assert isinstance(
        profile,
        ProfileResponseSchema,
    )

    assert profile.user.id == user.id
    assert profile.staff is None
    assert profile.clinic is not None
    assert profile.clinic.id == clinic.id


def test_get_profile_rejects_missing_user():
    with pytest.raises(
        NotFoundError,
        match="User 999999 not found",
    ):
        profile_service.get_profile(
            999999,
        )


# ============================================================================
# UPDATE PROFILE — VALIDATION
# ============================================================================


def test_update_profile_requires_at_least_one_field(
    user,
):
    with pytest.raises(
        ValidationError,
        match="At least one profile field is required",
    ):
        profile_service.update_profile(
            user.id,
        )


def test_update_profile_rejects_unknown_fields(
    user,
):
    with pytest.raises(
        ValidationError,
        match="Unsupported profile field",
    ):
        profile_service.update_profile(
            user.id,
            role="doctor",
        )


def test_update_profile_rejects_staff_fields_without_staff(
    user,
):
    with pytest.raises(
        ValidationError,
        match="This user is not linked to a staff record",
    ):
        profile_service.update_profile(
            user.id,
            first_name="Updated",
        )


def test_update_profile_rejects_null_email(
    user,
):
    with pytest.raises(
        ValidationError,
        match="Email cannot be null",
    ):
        profile_service.update_profile(
            user.id,
            email=None,
        )


def test_update_profile_rejects_duplicate_email(
    make_user,
    user,
    clinic,
):
    other_user = make_user(
        clinic,
        email="taken@example.com",
    )

    assert other_user.id != user.id

    with pytest.raises(
        ConflictError,
        match="already in use",
    ):
        profile_service.update_profile(
            user.id,
            email="taken@example.com",
        )


# ============================================================================
# UPDATE PROFILE — USER FIELDS
# ============================================================================


def test_update_profile_updates_user_email(
    user,
    monkeypatch,
):
    audit_mock = Mock()

    monkeypatch.setattr(
        profile_service,
        "create_audit_log",
        audit_mock,
    )

    old_email = user.email
    new_email = "updated@example.com"

    profile = profile_service.update_profile(
        user.id,
        email=new_email,
    )

    assert profile.user.email == new_email
    assert user.email == new_email

    audit_mock.assert_called_once()

    call_kwargs = audit_mock.call_args.kwargs

    assert call_kwargs["entity_type"] == "User"
    assert call_kwargs["entity_id"] == user.id
    assert call_kwargs["old_value"] == {
        "email": old_email,
    }
    assert call_kwargs["new_value"] == {
        "email": new_email,
    }


def test_update_profile_does_not_audit_unchanged_email(
    user,
    monkeypatch,
):
    audit_mock = Mock()

    monkeypatch.setattr(
        profile_service,
        "create_audit_log",
        audit_mock,
    )

    profile_service.update_profile(
        user.id,
        email=user.email,
    )

    audit_mock.assert_not_called()


# ============================================================================
# UPDATE PROFILE — STAFF FIELDS
# ============================================================================


def test_update_profile_updates_staff_fields(
    staff,
    monkeypatch,
):
    audit_mock = Mock()

    monkeypatch.setattr(
        profile_service,
        "create_audit_log",
        audit_mock,
    )

    old_first_name = staff.first_name
    old_last_name = staff.last_name
    old_phone = staff.phone
    old_specialty = staff.specialty

    profile = profile_service.update_profile(
        staff.user.id,
        first_name="Updated",
        last_name="Profile",
        phone="08000000000",
        specialty="Cardiology",
    )

    assert profile.staff is not None
    assert profile.staff.first_name == "Updated"
    assert profile.staff.last_name == "Profile"
    assert profile.staff.phone == "08000000000"
    assert profile.staff.specialty == "Cardiology"

    assert staff.first_name == "Updated"
    assert staff.last_name == "Profile"
    assert staff.phone == "08000000000"
    assert staff.specialty == "Cardiology"

    audit_mock.assert_called_once()

    call_kwargs = audit_mock.call_args.kwargs

    assert call_kwargs["entity_type"] == "Staff"
    assert call_kwargs["entity_id"] == staff.id

    assert call_kwargs["old_value"] == {
        "first_name": old_first_name,
        "last_name": old_last_name,
        "phone": old_phone,
        "specialty": old_specialty,
    }

    assert call_kwargs["new_value"] == {
        "first_name": "Updated",
        "last_name": "Profile",
        "phone": "08000000000",
        "specialty": "Cardiology",
    }


def test_update_profile_updates_user_and_staff_and_creates_two_audit_logs(
    staff,
    monkeypatch,
):
    audit_mock = Mock()

    monkeypatch.setattr(
        profile_service,
        "create_audit_log",
        audit_mock,
    )

    old_email = staff.user.email
    old_first_name = staff.first_name

    profile = profile_service.update_profile(
        staff.user.id,
        email="newstaff@example.com",
        first_name="Updated",
    )

    assert profile.user.email == "newstaff@example.com"
    assert profile.staff is not None
    assert profile.staff.first_name == "Updated"

    assert audit_mock.call_count == 2

    calls = audit_mock.call_args_list

    user_call = calls[0].kwargs
    staff_call = calls[1].kwargs

    assert user_call["entity_type"] == "User"
    assert user_call["entity_id"] == staff.user.id
    assert user_call["old_value"] == {
        "email": old_email,
    }
    assert user_call["new_value"] == {
        "email": "newstaff@example.com",
    }

    assert staff_call["entity_type"] == "Staff"
    assert staff_call["entity_id"] == staff.id
    assert staff_call["old_value"] == {
        "first_name": old_first_name,
    }
    assert staff_call["new_value"] == {
        "first_name": "Updated",
    }


def test_update_profile_does_not_audit_unchanged_staff_fields(
    staff,
    monkeypatch,
):
    audit_mock = Mock()

    monkeypatch.setattr(
        profile_service,
        "create_audit_log",
        audit_mock,
    )

    profile_service.update_profile(
        staff.user.id,
        first_name=staff.first_name,
        last_name=staff.last_name,
        phone=staff.phone,
        specialty=staff.specialty,
    )

    audit_mock.assert_not_called()


# ============================================================================
# UPDATE PROFILE — DATA INTEGRITY
# ============================================================================


def test_update_profile_does_not_change_protected_fields(
    staff,
):
    original_role = staff.user.role
    original_user_clinic_id = staff.user.clinic_id
    original_staff_clinic_id = staff.clinic_id
    original_staff_user_id = staff.user_id

    profile = profile_service.update_profile(
        staff.user.id,
        email="protected-test@example.com",
        first_name="Safe",
    )

    assert profile.user.email == "protected-test@example.com"
    assert profile.staff is not None
    assert profile.staff.first_name == "Safe"

    assert staff.user.role == original_role
    assert staff.user.clinic_id == original_user_clinic_id
    assert staff.clinic_id == original_staff_clinic_id
    assert staff.user_id == original_staff_user_id


def test_update_profile_preserves_existing_clinic(
    staff,
    clinic,
):
    profile = profile_service.update_profile(
        staff.user.id,
        first_name="Clinic Safe",
    )

    assert profile.clinic is not None
    assert profile.clinic.id == clinic.id


# ============================================================================
# UPDATE PROFILE — TRANSACTION / FAILURE SAFETY
# ============================================================================


def test_update_profile_rejects_missing_authenticated_user(
    db_session,
):
    with pytest.raises(
        NotFoundError,
        match="User 999999 not found",
    ):
        profile_service.update_profile(
            999999,
            email="missing@example.com",
        )

    db_session.rollback()