# app/tests/modules/clinic/test_clinic_service.py

from datetime import time

import pytest

from app.core.enums.clinic_enums import ClinicStatus, ClinicType
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services import clinic_service


# ============================================================================
# TEST CONTEXT
# ============================================================================


@pytest.fixture(autouse=True)
def clinic_app_context(app):
    """
    Ensure every clinic service test runs inside the Flask
    application context.

    The clinic service currently uses Flask-SQLAlchemy's
    Model.query and the transactional decorator, both of which
    require an active application context.
    """
    yield


# ============================================================================
# GET CLINIC
# ============================================================================


def test_get_clinic_returns_clinic(clinic):
    result = clinic_service.get_clinic(clinic.id)

    assert result is clinic
    assert result.id == clinic.id


def test_get_clinic_returns_not_found_for_missing_id():
    with pytest.raises(NotFoundError, match=r"Clinic 999999 not found"):
        clinic_service.get_clinic(999999)


def test_get_clinic_rejects_zero():
    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        clinic_service.get_clinic(0)


def test_get_clinic_rejects_negative_id():
    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        clinic_service.get_clinic(-1)


def test_get_clinic_for_update_returns_clinic(clinic):
    result = clinic_service.get_clinic(
        clinic.id,
        for_update=True,
    )

    assert result is clinic
    assert result.id == clinic.id


# ============================================================================
# LIST CLINICS
# ============================================================================


def test_list_clinics_returns_clinics_sorted_by_name(
    make_clinic,
):
    clinic_z = make_clinic(name="Zeta Clinic")
    clinic_a = make_clinic(name="Alpha Clinic")
    clinic_m = make_clinic(name="Metro Clinic")

    clinics = clinic_service.list_clinics()

    assert [clinic.id for clinic in clinics] == [
        clinic_a.id,
        clinic_m.id,
        clinic_z.id,
    ]


def test_list_clinics_filters_by_status(
    make_clinic,
):
    active = make_clinic(
        name="Active Clinic",
        status=ClinicStatus.ACTIVE,
    )
    suspended = make_clinic(
        name="Suspended Clinic",
        status=ClinicStatus.SUSPENDED,
    )

    clinics = clinic_service.list_clinics(
        status=ClinicStatus.SUSPENDED,
    )

    assert [clinic.id for clinic in clinics] == [suspended.id]
    assert active.id not in [clinic.id for clinic in clinics]


def test_list_clinics_empty_database():
    clinics = clinic_service.list_clinics()

    assert clinics == []


# ============================================================================
# LIST BRANCHES
# ============================================================================


def test_list_branches_returns_direct_children(
    make_clinic,
):
    parent = make_clinic(name="Parent Clinic")
    branch_a = make_clinic(
        name="Branch A",
        parent_clinic_id=parent.id,
    )
    branch_b = make_clinic(
        name="Branch B",
        parent_clinic_id=parent.id,
    )
    unrelated = make_clinic(
        name="Unrelated Clinic",
    )

    branches = clinic_service.list_branches(parent.id)

    assert [branch.id for branch in branches] == [
        branch_a.id,
        branch_b.id,
    ]
    assert unrelated.id not in [branch.id for branch in branches]


def test_list_branches_sorts_by_name(
    make_clinic,
):
    parent = make_clinic(name="Parent Clinic")

    branch_z = make_clinic(
        name="Zeta Branch",
        parent_clinic_id=parent.id,
    )
    branch_a = make_clinic(
        name="Alpha Branch",
        parent_clinic_id=parent.id,
    )

    branches = clinic_service.list_branches(parent.id)

    assert [branch.id for branch in branches] == [
        branch_a.id,
        branch_z.id,
    ]


def test_list_branches_raises_when_parent_does_not_exist():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.list_branches(999999)


# ============================================================================
# CREATE CLINIC
# ============================================================================


def test_create_clinic_creates_active_clinic(db):
    clinic = clinic_service.create_clinic(
        name="Central Medical Center",
        clinic_type=ClinicType.GENERAL,
    )

    assert clinic.id is not None
    assert clinic.name == "Central Medical Center"
    assert clinic.clinic_type == ClinicType.GENERAL
    assert clinic.status == ClinicStatus.ACTIVE
    assert clinic.parent_clinic_id is None
    assert clinic.is_headquarters is False
    assert clinic.ai_credits == 0
    assert clinic.ai_requests_this_month == 0

    persisted = db.session.get(Clinic, clinic.id)

    assert persisted is clinic


def test_create_clinic_normalizes_name():
    clinic = clinic_service.create_clinic(
        name="  Central Clinic  ",
    )

    assert clinic.name == "Central Clinic"


def test_create_clinic_rejects_non_string_name():
    with pytest.raises(
        ValidationError,
        match="Clinic name must be a string",
    ):
        clinic_service.create_clinic(name=123)


def test_create_clinic_rejects_empty_name():
    with pytest.raises(
        ValidationError,
        match="Clinic name is required",
    ):
        clinic_service.create_clinic(name="   ")


def test_create_clinic_rejects_invalid_parent_id():
    with pytest.raises(
        ValidationError,
        match="Invalid parent clinic ID",
    ):
        clinic_service.create_clinic(
            name="Child Clinic",
            parent_clinic_id=0,
        )


def test_create_clinic_rejects_missing_parent():
    with pytest.raises(
        NotFoundError,
        match=r"Parent clinic 999999 not found",
    ):
        clinic_service.create_clinic(
            name="Child Clinic",
            parent_clinic_id=999999,
        )


def test_create_clinic_rejects_headquarters_with_parent(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="A headquarters clinic cannot have a parent clinic",
    ):
        clinic_service.create_clinic(
            name="Invalid HQ",
            parent_clinic_id=clinic.id,
            is_headquarters=True,
        )


def test_create_clinic_rejects_inactive_parent(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        clinic_service.create_clinic(
            name="Child Clinic",
            parent_clinic_id=suspended_clinic.id,
        )


def test_create_clinic_rejects_duplicate_name_under_same_parent(
    clinic,
):
    clinic_service.create_clinic(
        name="Duplicate Clinic",
        parent_clinic_id=clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match=(
            r"A clinic named 'Duplicate Clinic' "
            r"already exists under this parent clinic"
        ),
    ):
        clinic_service.create_clinic(
            name="Duplicate Clinic",
            parent_clinic_id=clinic.id,
        )


def test_create_clinic_allows_same_name_under_different_parents(
    make_clinic,
):
    parent_a = make_clinic(name="Parent A")
    parent_b = make_clinic(name="Parent B")

    first = clinic_service.create_clinic(
        name="Shared Branch",
        parent_clinic_id=parent_a.id,
    )

    second = clinic_service.create_clinic(
        name="Shared Branch",
        parent_clinic_id=parent_b.id,
    )

    assert first.id != second.id
    assert first.parent_clinic_id == parent_a.id
    assert second.parent_clinic_id == parent_b.id


def test_create_clinic_sets_profile_fields():
    opening = time(8, 0)
    closing = time(17, 0)

    clinic = clinic_service.create_clinic(
        name="Full Profile Clinic",
        clinic_type=ClinicType.SPECIALIST,
        address="123 Hospital Road",
        city="Onitsha",
        country="Nigeria",
        phone="+2348000000000",
        email="clinic@example.com",
        timezone="Africa/Lagos",
        opening_time=opening,
        closing_time=closing,
        is_headquarters=True,
    )

    assert clinic.clinic_type == ClinicType.SPECIALIST
    assert clinic.address == "123 Hospital Road"
    assert clinic.city == "Onitsha"
    assert clinic.country == "Nigeria"
    assert clinic.phone == "+2348000000000"
    assert clinic.email == "clinic@example.com"
    assert clinic.timezone == "Africa/Lagos"
    assert clinic.opening_time == opening
    assert clinic.closing_time == closing
    assert clinic.is_headquarters is True


# ============================================================================
# CREATE BRANCH
# ============================================================================


def test_create_branch_creates_active_branch(
    clinic,
):
    branch = clinic_service.create_branch(
        parent_clinic_id=clinic.id,
        name="Main Branch",
    )

    assert branch.id is not None
    assert branch.name == "Main Branch"
    assert branch.parent_clinic_id == clinic.id
    assert branch.is_headquarters is False
    assert branch.status == ClinicStatus.ACTIVE
    assert branch.ai_credits == 0
    assert branch.ai_requests_this_month == 0


def test_create_branch_rejects_invalid_parent_id():
    with pytest.raises(
        ValidationError,
        match="Invalid parent clinic ID",
    ):
        clinic_service.create_branch(
            parent_clinic_id=0,
            name="Branch",
        )


def test_create_branch_rejects_missing_parent():
    with pytest.raises(
        NotFoundError,
        match=r"Parent clinic 999999 not found",
    ):
        clinic_service.create_branch(
            parent_clinic_id=999999,
            name="Branch",
        )


def test_create_branch_rejects_inactive_parent(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        clinic_service.create_branch(
            parent_clinic_id=suspended_clinic.id,
            name="Branch",
        )


def test_create_branch_rejects_duplicate_name(
    clinic,
):
    clinic_service.create_branch(
        parent_clinic_id=clinic.id,
        name="Duplicate Branch",
    )

    with pytest.raises(
        ConflictError,
        match=(
            r"A clinic named 'Duplicate Branch' "
            r"already exists under this parent clinic"
        ),
    ):
        clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Duplicate Branch",
        )


# ============================================================================
# UPDATE CLINIC
# ============================================================================


def test_update_clinic_updates_allowed_fields(
    clinic,
):
    updated = clinic_service.update_clinic(
        clinic.id,
        name="Updated Clinic",
        clinic_type=ClinicType.SPECIALIST,
        address="New Address",
        city="Lagos",
        country="Nigeria",
        phone="08000000000",
        email="updated@example.com",
        timezone="Africa/Lagos",
        opening_time=time(8, 0),
        closing_time=time(18, 0),
    )

    assert updated.name == "Updated Clinic"
    assert updated.clinic_type == ClinicType.SPECIALIST
    assert updated.address == "New Address"
    assert updated.city == "Lagos"
    assert updated.country == "Nigeria"
    assert updated.phone == "08000000000"
    assert updated.email == "updated@example.com"
    assert updated.timezone == "Africa/Lagos"
    assert updated.opening_time == time(8, 0)
    assert updated.closing_time == time(18, 0)


def test_update_clinic_normalizes_name(
    clinic,
):
    updated = clinic_service.update_clinic(
        clinic.id,
        name="  Updated Name  ",
    )

    assert updated.name == "Updated Name"


def test_update_clinic_rejects_unsupported_field(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match=r"Unsupported clinic fields: invalid_field",
    ):
        clinic_service.update_clinic(
            clinic.id,
            invalid_field="value",
        )


def test_update_clinic_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.update_clinic(
            999999,
            name="Updated",
        )


def test_update_clinic_rejects_duplicate_name_under_same_parent(
    make_clinic,
):
    first = make_clinic(name="First Clinic")
    second = make_clinic(name="Second Clinic")

    with pytest.raises(
        ConflictError,
        match=(
            r"A clinic named 'First Clinic' "
            r"already exists under this parent clinic"
        ),
    ):
        clinic_service.update_clinic(
            second.id,
            name=first.name,
        )


def test_update_clinic_allows_same_name_for_same_clinic(
    clinic,
):
    updated = clinic_service.update_clinic(
        clinic.id,
        name=clinic.name,
    )

    assert updated.name == clinic.name


def test_update_clinic_rejects_invalid_timezone(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match=r"Invalid timezone 'Not/ARealTimezone'",
    ):
        clinic_service.update_clinic(
            clinic.id,
            timezone="Not/ARealTimezone",
        )


def test_update_clinic_rejects_invalid_operating_hours(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Opening time must be earlier than closing time",
    ):
        clinic_service.update_clinic(
            clinic.id,
            opening_time=time(18, 0),
            closing_time=time(8, 0),
        )


# ============================================================================
# BRANCH CONFIGURATION
# ============================================================================


def test_update_branch_configuration_assigns_parent(
    make_clinic,
):
    parent = make_clinic(name="Parent")
    child = make_clinic(name="Child")

    updated = clinic_service.update_branch_configuration(
        child.id,
        parent_clinic_id=parent.id,
    )

    assert updated.parent_clinic_id == parent.id


def test_update_branch_configuration_detaches_parent(
    make_clinic,
):
    parent = make_clinic(name="Parent")
    child = make_clinic(
        name="Child",
        parent_clinic_id=parent.id,
    )

    updated = clinic_service.update_branch_configuration(
        child.id,
        parent_clinic_id=None,
    )

    assert updated.parent_clinic_id is None


def test_update_branch_configuration_changes_headquarters_flag(
    clinic,
):
    assert clinic.is_headquarters is False

    updated = clinic_service.update_branch_configuration(
        clinic.id,
        is_headquarters=True,
    )

    assert updated.is_headquarters is True


def test_update_branch_configuration_rejects_self_parent(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="A clinic cannot be its own parent",
    ):
        clinic_service.update_branch_configuration(
            clinic.id,
            parent_clinic_id=clinic.id,
        )


def test_update_branch_configuration_rejects_invalid_parent_id(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Invalid parent clinic ID",
    ):
        clinic_service.update_branch_configuration(
            clinic.id,
            parent_clinic_id=0,
        )


def test_update_branch_configuration_rejects_missing_parent(
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match=r"Parent clinic 999999 not found",
    ):
        clinic_service.update_branch_configuration(
            clinic.id,
            parent_clinic_id=999999,
        )


def test_update_branch_configuration_rejects_inactive_parent(
    clinic,
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        clinic_service.update_branch_configuration(
            clinic.id,
            parent_clinic_id=suspended_clinic.id,
        )


def test_update_branch_configuration_rejects_hq_with_parent(
    make_clinic,
):
    parent = make_clinic(name="Parent")
    child = make_clinic(name="Child")

    with pytest.raises(
        ValidationError,
        match="A headquarters clinic cannot have a parent clinic",
    ):
        clinic_service.update_branch_configuration(
            child.id,
            parent_clinic_id=parent.id,
            is_headquarters=True,
        )


def test_update_branch_configuration_rejects_cycle(
    make_clinic,
):
    root = make_clinic(name="Root")
    child = make_clinic(
        name="Child",
        parent_clinic_id=root.id,
    )
    grandchild = make_clinic(
        name="Grandchild",
        parent_clinic_id=child.id,
    )

    with pytest.raises(
        ConflictError,
        match="circular clinic hierarchy",
    ):
        clinic_service.update_branch_configuration(
            root.id,
            parent_clinic_id=grandchild.id,
        )


def test_update_branch_configuration_rejects_duplicate_name_under_new_parent(
    make_clinic,
):
    parent_a = make_clinic(name="Parent A")
    parent_b = make_clinic(name="Parent B")

    existing = make_clinic(
        name="Existing Branch",
        parent_clinic_id=parent_b.id,
    )

    moving = make_clinic(
        name="Existing Branch",
        parent_clinic_id=parent_a.id,
    )

    assert existing.id != moving.id

    with pytest.raises(
        ConflictError,
        match=(
            r"A clinic named 'Existing Branch' "
            r"already exists under this parent clinic"
        ),
    ):
        clinic_service.update_branch_configuration(
            moving.id,
            parent_clinic_id=parent_b.id,
        )


# ============================================================================
# STATUS
# ============================================================================


def test_change_status_updates_status(
    clinic,
):
    updated = clinic_service.change_status(
        clinic.id,
        ClinicStatus.SUSPENDED,
    )

    assert updated.status == ClinicStatus.SUSPENDED


def test_change_status_returns_unchanged_clinic_when_status_same(
    clinic,
):
    original_status = clinic.status

    updated = clinic_service.change_status(
        clinic.id,
        original_status,
    )

    assert updated is clinic
    assert updated.status == original_status


def test_change_status_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.change_status(
            999999,
            ClinicStatus.SUSPENDED,
        )


# ============================================================================
# AI CREDITS
# ============================================================================


def test_add_ai_credits_increases_balance(
    clinic,
):
    clinic.ai_credits = 10

    updated = clinic_service.add_ai_credits(
        clinic.id,
        5,
    )

    assert updated.ai_credits == 15


def test_add_ai_credits_rejects_non_integer(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="AI credit amount must be an integer",
    ):
        clinic_service.add_ai_credits(
            clinic.id,
            "5",
        )


def test_add_ai_credits_rejects_zero(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="AI credit amount must be greater than zero",
    ):
        clinic_service.add_ai_credits(
            clinic.id,
            0,
        )


def test_add_ai_credits_rejects_negative_amount(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="AI credit amount must be greater than zero",
    ):
        clinic_service.add_ai_credits(
            clinic.id,
            -5,
        )


def test_add_ai_credits_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.add_ai_credits(
            999999,
            5,
        )


# ============================================================================
# API TOKEN
# ============================================================================


def test_regenerate_api_token_creates_token(
    clinic,
):
    token = clinic_service.regenerate_api_token(
        clinic.id,
    )

    assert isinstance(token, str)
    assert token
    assert len(token) > 40
    assert clinic.api_token == token


def test_regenerate_api_token_replaces_existing_token(
    clinic,
):
    clinic.api_token = "old-token"

    first = clinic_service.regenerate_api_token(
        clinic.id,
    )

    second = clinic_service.regenerate_api_token(
        clinic.id,
    )

    assert first != second
    assert clinic.api_token == second


def test_regenerate_api_token_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.regenerate_api_token(999999)


# ============================================================================
# ENSURE ACTIVE
# ============================================================================


def test_ensure_clinic_active_returns_active_clinic(
    clinic,
):
    result = clinic_service.ensure_clinic_active(
        clinic.id,
    )

    assert result is clinic


def test_ensure_clinic_active_rejects_suspended_clinic(
    suspended_clinic,
):
    with pytest.raises(
        ValidationError,
        match=rf"Clinic {suspended_clinic.id} is not active",
    ):
        clinic_service.ensure_clinic_active(
            suspended_clinic.id,
        )


def test_ensure_clinic_active_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        clinic_service.ensure_clinic_active(999999)