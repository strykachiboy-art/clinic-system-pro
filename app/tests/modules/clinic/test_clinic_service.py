from datetime import time

import pytest

from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus, ClinicType
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services import clinic_service


# =====================================================================
# TEST HELPERS
# =====================================================================


@pytest.fixture
def mock_audit_log(monkeypatch):
    """
    Replace audit logging with an in-memory collector.

    This allows the service tests to verify audit behavior without
    coupling the tests to the AuditLog database implementation.
    """
    calls = []

    def fake_create_audit_log(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        clinic_service,
        "create_audit_log",
        fake_create_audit_log,
    )

    return calls


# =====================================================================
# PRIVATE HELPERS
# =====================================================================


class TestEnumValue:
    def test_returns_underlying_enum_value(self):
        result = clinic_service._enum_value(
            ClinicStatus.ACTIVE
        )

        assert result == "active"

    def test_returns_plain_string_unchanged(self):
        result = clinic_service._enum_value("active")

        assert result == "active"

    def test_returns_integer_unchanged(self):
        result = clinic_service._enum_value(10)

        assert result == 10

    def test_returns_none_unchanged(self):
        result = clinic_service._enum_value(None)

        assert result is None


class TestValidateName:
    def test_valid_name_is_returned(self):
        result = clinic_service._validate_name(
            "Test Clinic"
        )

        assert result == "Test Clinic"

    def test_name_is_stripped(self):
        result = clinic_service._validate_name(
            "  Test Clinic  "
        )

        assert result == "Test Clinic"

    def test_none_name_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service._validate_name(None)

    def test_empty_name_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service._validate_name("")

    def test_whitespace_name_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service._validate_name("   ")


class TestValidateOperatingHours:
    def test_both_times_can_be_none(self):
        clinic_service._validate_operating_hours(
            None,
            None,
        )

    def test_only_opening_time_is_allowed(self):
        clinic_service._validate_operating_hours(
            time(8, 0),
            None,
        )

    def test_only_closing_time_is_allowed(self):
        clinic_service._validate_operating_hours(
            None,
            time(17, 0),
        )

    def test_valid_hours_are_allowed(self):
        clinic_service._validate_operating_hours(
            time(8, 0),
            time(17, 0),
        )

    def test_equal_times_raise_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Opening time must be earlier than closing time",
        ):
            clinic_service._validate_operating_hours(
                time(8, 0),
                time(8, 0),
            )

    def test_opening_after_closing_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Opening time must be earlier than closing time",
        ):
            clinic_service._validate_operating_hours(
                time(18, 0),
                time(8, 0),
            )


class TestGetParentClinic:
    def test_returns_existing_parent(self, clinic):
        result = clinic_service._get_parent_clinic(
            clinic.id
        )

        assert result.id == clinic.id

    def test_missing_parent_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Parent clinic 99999 not found",
        ):
            clinic_service._get_parent_clinic(99999)


class TestCheckNameConflict:
    def test_duplicate_name_under_same_parent_raises_conflict(
        self,
        clinic,
        make_clinic,
    ):
        make_clinic(
            name="Duplicate Clinic",
            parent_clinic_id=clinic.id,
        )

        with pytest.raises(
            ConflictError,
            match="already exists under this parent clinic",
        ):
            clinic_service._check_name_conflict(
                name="Duplicate Clinic",
                parent_clinic_id=clinic.id,
            )

    def test_same_name_under_different_parent_is_allowed(
        self,
        make_clinic,
    ):
        parent_one = make_clinic(
            name="Parent One"
        )

        parent_two = make_clinic(
            name="Parent Two"
        )

        make_clinic(
            name="Same Name",
            parent_clinic_id=parent_one.id,
        )

        # Different parent means no conflict.
        clinic_service._check_name_conflict(
            name="Same Name",
            parent_clinic_id=parent_two.id,
        )

    def test_excluded_clinic_does_not_conflict(
        self,
        clinic,
    ):
        clinic_service._check_name_conflict(
            name=clinic.name,
            parent_clinic_id=clinic.parent_clinic_id,
            exclude_clinic_id=clinic.id,
        )


# =====================================================================
# GET CLINIC
# =====================================================================


class TestGetClinic:
    def test_returns_existing_clinic(self, clinic):
        result = clinic_service.get_clinic(
            clinic.id
        )

        assert result.id == clinic.id
        assert result.name == clinic.name

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.get_clinic(99999)


# =====================================================================
# LIST CLINICS
# =====================================================================


class TestListClinics:
    def test_returns_clinics_sorted_by_name(
        self,
        make_clinic,
    ):
        make_clinic(name="Zulu Clinic")
        make_clinic(name="Alpha Clinic")
        make_clinic(name="Middle Clinic")

        clinics = clinic_service.list_clinics()

        names = [clinic.name for clinic in clinics]

        assert names == sorted(names)

    def test_filters_by_status(
        self,
        make_clinic,
    ):
        make_clinic(
            name="Active Clinic",
            status=ClinicStatus.ACTIVE,
        )

        make_clinic(
            name="Suspended Clinic",
            status=ClinicStatus.SUSPENDED,
        )

        clinics = clinic_service.list_clinics(
            status=ClinicStatus.SUSPENDED
        )

        assert len(clinics) == 1
        assert clinics[0].name == "Suspended Clinic"
        assert clinics[0].status == ClinicStatus.SUSPENDED

    def test_returns_empty_list_when_status_has_no_matches(
        self,
        clinic,
    ):
        clinic.status = ClinicStatus.SUSPENDED
        db.session.commit()

        clinics = clinic_service.list_clinics(
            status=ClinicStatus.INACTIVE
        )

        assert clinics == []


# =====================================================================
# LIST BRANCHES
# =====================================================================


class TestListBranches:
    def test_returns_direct_branches(
        self,
        make_clinic,
    ):
        parent = make_clinic(
            name="Parent Clinic"
        )

        branch_one = make_clinic(
            name="Branch One",
            parent_clinic_id=parent.id,
        )

        branch_two = make_clinic(
            name="Branch Two",
            parent_clinic_id=parent.id,
        )

        other_parent = make_clinic(
            name="Other Parent"
        )

        make_clinic(
            name="Other Branch",
            parent_clinic_id=other_parent.id,
        )

        branches = clinic_service.list_branches(
            parent.id
        )

        assert len(branches) == 2

        ids = {branch.id for branch in branches}

        assert ids == {
            branch_one.id,
            branch_two.id,
        }

    def test_returns_branches_sorted_by_name(
        self,
        make_clinic,
    ):
        parent = make_clinic(
            name="Parent Clinic"
        )

        make_clinic(
            name="Zulu Branch",
            parent_clinic_id=parent.id,
        )

        make_clinic(
            name="Alpha Branch",
            parent_clinic_id=parent.id,
        )

        branches = clinic_service.list_branches(
            parent.id
        )

        assert [branch.name for branch in branches] == [
            "Alpha Branch",
            "Zulu Branch",
        ]

    def test_missing_parent_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.list_branches(99999)


# =====================================================================
# CREATE CLINIC
# =====================================================================


class TestCreateClinic:
    def test_creates_root_clinic(
        self,
        mock_audit_log,
    ):
        clinic = clinic_service.create_clinic(
            name="New Clinic"
        )

        assert clinic.id is not None
        assert clinic.name == "New Clinic"
        assert clinic.clinic_type == ClinicType.GENERAL
        assert clinic.status == ClinicStatus.ACTIVE
        assert clinic.parent_clinic_id is None
        assert clinic.is_headquarters is False
        assert clinic.timezone == "UTC"
        assert clinic.ai_credits == 0
        assert clinic.ai_requests_this_month == 0

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.CREATE
        assert mock_audit_log[0]["entity_type"] == "Clinic"
        assert mock_audit_log[0]["entity_id"] == clinic.id

    def test_creates_headquarters(
        self,
        mock_audit_log,
    ):
        clinic = clinic_service.create_clinic(
            name="Main Headquarters",
            clinic_type=ClinicType.SPECIALIST,
            is_headquarters=True,
        )

        assert clinic.name == "Main Headquarters"
        assert clinic.clinic_type == ClinicType.SPECIALIST
        assert clinic.is_headquarters is True
        assert clinic.parent_clinic_id is None

        assert (
            mock_audit_log[0]["new_value"]["is_headquarters"]
            is True
        )

    def test_creates_child_clinic(
        self,
        clinic,
        mock_audit_log,
    ):
        child = clinic_service.create_clinic(
            name="Child Clinic",
            clinic_type=ClinicType.DENTAL,
            parent_clinic_id=clinic.id,
        )

        assert child.id is not None
        assert child.name == "Child Clinic"
        assert child.parent_clinic_id == clinic.id
        assert child.clinic_type == ClinicType.DENTAL
        assert child.status == ClinicStatus.ACTIVE
        assert child.is_headquarters is False

    def test_creates_clinic_with_all_profile_fields(
        self,
        mock_audit_log,
    ):
        clinic = clinic_service.create_clinic(
            name="Full Clinic",
            clinic_type=ClinicType.DIAGNOSTIC_CENTER,
            address="123 Medical Road",
            city="Port Harcourt",
            country="Nigeria",
            phone="08012345678",
            email="clinic@test.com",
            timezone="Africa/Lagos",
            opening_time=time(8, 0),
            closing_time=time(17, 0),
        )

        assert clinic.address == "123 Medical Road"
        assert clinic.city == "Port Harcourt"
        assert clinic.country == "Nigeria"
        assert clinic.phone == "08012345678"
        assert clinic.email == "clinic@test.com"
        assert clinic.timezone == "Africa/Lagos"
        assert clinic.opening_time == time(8, 0)
        assert clinic.closing_time == time(17, 0)

    def test_strips_name(self, mock_audit_log):
        clinic = clinic_service.create_clinic(
            name="  Trimmed Clinic  "
        )

        assert clinic.name == "Trimmed Clinic"

    def test_missing_name_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service.create_clinic(
                name=None
            )

    def test_blank_name_raises_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service.create_clinic(
                name="   "
            )

    def test_missing_parent_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Parent clinic 99999 not found",
        ):
            clinic_service.create_clinic(
                name="Child Clinic",
                parent_clinic_id=99999,
            )

    def test_zero_parent_id_raises_not_found(self):
        # The service calls _get_parent_clinic() before the explicit
        # parent_clinic_id == 0 validation.
        with pytest.raises(
            NotFoundError,
            match=r"Parent clinic 0 not found",
        ):
            clinic_service.create_clinic(
                name="Invalid Parent",
                parent_clinic_id=0,
            )

    def test_headquarters_cannot_have_parent(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="A headquarters clinic cannot have a parent clinic",
        ):
            clinic_service.create_clinic(
                name="Invalid Headquarters",
                parent_clinic_id=clinic.id,
                is_headquarters=True,
            )

    def test_invalid_operating_hours_raise_validation_error(self):
        with pytest.raises(
            ValidationError,
            match="Opening time must be earlier than closing time",
        ):
            clinic_service.create_clinic(
                name="Invalid Hours",
                opening_time=time(18, 0),
                closing_time=time(8, 0),
            )

    def test_duplicate_name_under_same_parent_raises_conflict(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Existing Branch",
        )

        with pytest.raises(
            ConflictError,
            match="already exists under this parent clinic",
        ):
            clinic_service.create_clinic(
                name="Existing Branch",
                parent_clinic_id=clinic.id,
            )


# =====================================================================
# CREATE BRANCH
# =====================================================================


class TestCreateBranch:
    def test_creates_branch(
        self,
        clinic,
        mock_audit_log,
    ):
        branch = clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="New Branch",
        )

        assert branch.id is not None
        assert branch.name == "New Branch"
        assert branch.parent_clinic_id == clinic.id
        assert branch.status == ClinicStatus.ACTIVE
        assert branch.is_headquarters is False
        assert branch.clinic_type == ClinicType.GENERAL
        assert branch.ai_credits == 0
        assert branch.ai_requests_this_month == 0

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.CREATE

    def test_creates_branch_with_all_fields(
        self,
        clinic,
        mock_audit_log,
    ):
        branch = clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Dental Branch",
            clinic_type=ClinicType.DENTAL,
            address="456 Branch Road",
            city="Lagos",
            country="Nigeria",
            phone="08111111111",
            email="branch@test.com",
            timezone="Africa/Lagos",
            opening_time=time(7, 30),
            closing_time=time(18, 30),
        )

        assert branch.name == "Dental Branch"
        assert branch.clinic_type == ClinicType.DENTAL
        assert branch.address == "456 Branch Road"
        assert branch.city == "Lagos"
        assert branch.country == "Nigeria"
        assert branch.phone == "08111111111"
        assert branch.email == "branch@test.com"
        assert branch.timezone == "Africa/Lagos"
        assert branch.opening_time == time(7, 30)
        assert branch.closing_time == time(18, 30)

    def test_branch_is_active(
        self,
        clinic,
        mock_audit_log,
    ):
        branch = clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Active Branch",
        )

        assert branch.status == ClinicStatus.ACTIVE

    def test_branch_is_not_headquarters(
        self,
        clinic,
        mock_audit_log,
    ):
        branch = clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Normal Branch",
        )

        assert branch.is_headquarters is False

    def test_missing_parent_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Parent clinic 99999 not found",
        ):
            clinic_service.create_branch(
                parent_clinic_id=99999,
                name="Branch",
            )

    def test_blank_name_raises_validation_error(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service.create_branch(
                parent_clinic_id=clinic.id,
                name="   ",
            )

    def test_invalid_hours_raise_validation_error(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Opening time must be earlier than closing time",
        ):
            clinic_service.create_branch(
                parent_clinic_id=clinic.id,
                name="Invalid Hours Branch",
                opening_time=time(18, 0),
                closing_time=time(8, 0),
            )

    def test_duplicate_sibling_name_raises_conflict(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic_service.create_branch(
            parent_clinic_id=clinic.id,
            name="Duplicate Branch",
        )

        with pytest.raises(
            ConflictError,
            match="already exists under this parent clinic",
        ):
            clinic_service.create_branch(
                parent_clinic_id=clinic.id,
                name="Duplicate Branch",
            )

    def test_same_name_under_different_parents_is_allowed(
        self,
        make_clinic,
        mock_audit_log,
    ):
        parent_one = make_clinic(
            name="Parent One"
        )

        parent_two = make_clinic(
            name="Parent Two"
        )

        branch_one = clinic_service.create_branch(
            parent_clinic_id=parent_one.id,
            name="Common Branch",
        )

        branch_two = clinic_service.create_branch(
            parent_clinic_id=parent_two.id,
            name="Common Branch",
        )

        assert branch_one.id != branch_two.id
        assert branch_one.parent_clinic_id != branch_two.parent_clinic_id


# =====================================================================
# UPDATE CLINIC
# =====================================================================


class TestUpdateClinic:
    def test_updates_supported_fields(
        self,
        clinic,
        mock_audit_log,
    ):
        updated = clinic_service.update_clinic(
            clinic.id,
            name="Updated Clinic",
            clinic_type=ClinicType.SPECIALIST,
            address="New Address",
            city="Lagos",
            country="Nigeria",
            phone="08012345678",
            email="updated@test.com",
            timezone="Africa/Lagos",
            opening_time=time(8, 0),
            closing_time=time(17, 0),
        )

        assert updated.name == "Updated Clinic"
        assert updated.clinic_type == ClinicType.SPECIALIST
        assert updated.address == "New Address"
        assert updated.city == "Lagos"
        assert updated.country == "Nigeria"
        assert updated.phone == "08012345678"
        assert updated.email == "updated@test.com"
        assert updated.timezone == "Africa/Lagos"
        assert updated.opening_time == time(8, 0)
        assert updated.closing_time == time(17, 0)

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.UPDATE

    def test_updates_name_with_whitespace_trimmed(
        self,
        clinic,
        mock_audit_log,
    ):
        updated = clinic_service.update_clinic(
            clinic.id,
            name="  Updated Name  ",
        )

        assert updated.name == "Updated Name"

    def test_unknown_field_raises_validation_error(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Unsupported clinic fields",
        ):
            clinic_service.update_clinic(
                clinic.id,
                unknown_field="value",
            )

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.update_clinic(
                99999,
                name="New Name",
            )

    def test_blank_name_raises_validation_error(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Clinic name is required",
        ):
            clinic_service.update_clinic(
                clinic.id,
                name="   ",
            )

    def test_invalid_operating_hours_raise_validation_error(
        self,
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

    def test_name_conflict_is_rejected(
        self,
        make_clinic,
        mock_audit_log,
    ):
        first = make_clinic(
            name="First Clinic"
        )

        second = make_clinic(
            name="Second Clinic"
        )

        with pytest.raises(
            ConflictError,
            match="already exists under this parent clinic",
        ):
            clinic_service.update_clinic(
                second.id,
                name=first.name,
            )

    def test_same_name_on_same_clinic_is_allowed(
        self,
        clinic,
        mock_audit_log,
    ):
        result = clinic_service.update_clinic(
            clinic.id,
            name=clinic.name,
        )

        assert result.id == clinic.id
        assert result.name == clinic.name
        assert mock_audit_log == []

    def test_no_actual_changes_create_no_audit(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic_service.update_clinic(
            clinic.id,
            name=clinic.name,
            clinic_type=clinic.clinic_type,
        )

        assert mock_audit_log == []


# =====================================================================
# UPDATE BRANCH CONFIGURATION
# =====================================================================


class TestUpdateBranchConfiguration:
    def test_assigns_parent(
        self,
        make_clinic,
        mock_audit_log,
    ):
        parent = make_clinic(
            name="Parent"
        )

        child = make_clinic(
            name="Child"
        )

        updated = clinic_service.update_branch_configuration(
            child.id,
            parent_clinic_id=parent.id,
        )

        assert updated.parent_clinic_id == parent.id
        assert updated.is_headquarters is False

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.UPDATE

    def test_detaches_parent(
        self,
        make_clinic,
        mock_audit_log,
    ):
        parent = make_clinic(
            name="Parent"
        )

        child = make_clinic(
            name="Child",
            parent_clinic_id=parent.id,
        )

        updated = clinic_service.update_branch_configuration(
            child.id,
            parent_clinic_id=None,
        )

        assert updated.parent_clinic_id is None
        assert len(mock_audit_log) == 1

    def test_can_make_root_clinic_headquarters(
        self,
        clinic,
        mock_audit_log,
    ):
        updated = clinic_service.update_branch_configuration(
            clinic.id,
            is_headquarters=True,
        )

        assert updated.is_headquarters is True
        assert updated.parent_clinic_id is None

    def test_can_remove_headquarters_status(
        self,
        make_clinic,
        mock_audit_log,
    ):
        headquarters = make_clinic(
            name="Headquarters",
            is_headquarters=True,
        )

        updated = clinic_service.update_branch_configuration(
            headquarters.id,
            is_headquarters=False,
        )

        assert updated.is_headquarters is False

    def test_cannot_assign_self_as_parent(
        self,
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

    def test_missing_parent_raises_not_found(
        self,
        clinic,
    ):
        with pytest.raises(
            NotFoundError,
            match=r"Parent clinic 99999 not found",
        ):
            clinic_service.update_branch_configuration(
                clinic.id,
                parent_clinic_id=99999,
            )

    def test_prevents_circular_hierarchy(
        self,
        make_clinic,
        mock_audit_log,
    ):
        root = make_clinic(
            name="Root"
        )

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

    def test_prevents_headquarters_with_parent(
        self,
        make_clinic,
    ):
        parent = make_clinic(
            name="Parent"
        )

        child = make_clinic(
            name="Child"
        )

        with pytest.raises(
            ValidationError,
            match="A headquarters clinic cannot have a parent clinic",
        ):
            clinic_service.update_branch_configuration(
                child.id,
                parent_clinic_id=parent.id,
                is_headquarters=True,
            )

    def test_unknown_field_raises_validation_error(
        self,
        clinic,
    ):
        with pytest.raises(
            ValidationError,
            match="Unsupported branch configuration fields",
        ):
            clinic_service.update_branch_configuration(
                clinic.id,
                invalid_field=True,
            )

    def test_no_configuration_change_creates_no_audit(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic_service.update_branch_configuration(
            clinic.id,
            parent_clinic_id=clinic.parent_clinic_id,
            is_headquarters=clinic.is_headquarters,
        )

        assert mock_audit_log == []


# =====================================================================
# CHANGE STATUS
# =====================================================================


class TestChangeStatus:
    def test_changes_status(
        self,
        clinic,
        mock_audit_log,
    ):
        updated = clinic_service.change_status(
            clinic.id,
            ClinicStatus.SUSPENDED,
        )

        assert updated.status == ClinicStatus.SUSPENDED

        assert len(mock_audit_log) == 1
        assert (
            mock_audit_log[0]["action"]
            == AuditAction.STATUS_CHANGE
        )
        assert (
            mock_audit_log[0]["old_value"]["status"]
            == "active"
        )
        assert (
            mock_audit_log[0]["new_value"]["status"]
            == "suspended"
        )

    def test_changes_to_inactive(
        self,
        clinic,
        mock_audit_log,
    ):
        updated = clinic_service.change_status(
            clinic.id,
            ClinicStatus.INACTIVE,
        )

        assert updated.status == ClinicStatus.INACTIVE
        assert len(mock_audit_log) == 1

    def test_same_status_creates_no_audit(
        self,
        clinic,
        mock_audit_log,
    ):
        result = clinic_service.change_status(
            clinic.id,
            clinic.status,
        )

        assert result.id == clinic.id
        assert mock_audit_log == []

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.change_status(
                99999,
                ClinicStatus.SUSPENDED,
            )


# =====================================================================
# ADD AI CREDITS
# =====================================================================


class TestAddAICredits:
    def test_adds_ai_credits(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic.ai_credits = 10
        db.session.commit()

        updated = clinic_service.add_ai_credits(
            clinic.id,
            25,
        )

        assert updated.ai_credits == 35

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.UPDATE
        assert (
            mock_audit_log[0]["old_value"]["ai_credits"]
            == 10
        )
        assert (
            mock_audit_log[0]["new_value"]["ai_credits"]
            == 35
        )

    def test_zero_amount_raises_validation_error(
        self,
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

    def test_negative_amount_raises_validation_error(
        self,
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

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.add_ai_credits(
                99999,
                10,
            )


# =====================================================================
# REGENERATE API TOKEN
# =====================================================================


class TestRegenerateAPIToken:
    def test_generates_api_token(
        self,
        clinic,
        mock_audit_log,
    ):
        token = clinic_service.regenerate_api_token(
            clinic.id
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        assert clinic.api_token == token

        assert len(mock_audit_log) == 1
        assert mock_audit_log[0]["action"] == AuditAction.UPDATE

    def test_regenerating_token_replaces_old_token(
        self,
        clinic,
        mock_audit_log,
    ):
        first_token = clinic_service.regenerate_api_token(
            clinic.id
        )

        second_token = clinic_service.regenerate_api_token(
            clinic.id
        )

        assert first_token != second_token
        assert clinic.api_token == second_token

    def test_audit_does_not_contain_actual_token(
        self,
        clinic,
        mock_audit_log,
    ):
        token = clinic_service.regenerate_api_token(
            clinic.id
        )

        audit = mock_audit_log[0]

        assert audit["new_value"]["api_token"] == "present"
        assert token not in str(audit)

    def test_existing_token_is_marked_present(
        self,
        clinic,
        mock_audit_log,
    ):
        clinic.api_token = "old-secret-token"
        db.session.commit()

        clinic_service.regenerate_api_token(
            clinic.id
        )

        audit = mock_audit_log[0]

        assert (
            audit["old_value"]["api_token"]
            == "present"
        )

        assert (
            audit["new_value"]["api_token"]
            == "present"
        )

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.regenerate_api_token(
                99999
            )


# =====================================================================
# CONSUME AI CREDIT
# =====================================================================


class TestConsumeAICredit:
    def test_consumes_one_ai_credit(
        self,
        clinic,
    ):
        clinic.ai_credits = 10
        clinic.ai_requests_this_month = 3
        db.session.commit()

        result = clinic_service.consume_ai_credit(
            clinic.id
        )

        assert result.id == clinic.id
        assert result.ai_credits == 9
        assert result.ai_requests_this_month == 4

    def test_consuming_last_credit_is_allowed(
        self,
        clinic,
    ):
        clinic.ai_credits = 1
        clinic.ai_requests_this_month = 0
        db.session.commit()

        result = clinic_service.consume_ai_credit(
            clinic.id
        )

        assert result.ai_credits == 0
        assert result.ai_requests_this_month == 1

    def test_zero_credits_raises_validation_error(
        self,
        clinic,
    ):
        clinic.ai_credits = 0
        db.session.commit()

        with pytest.raises(
            ValidationError,
            match="Insufficient AI credits",
        ):
            clinic_service.consume_ai_credit(
                clinic.id
            )

    def test_negative_credits_raises_validation_error(
        self,
        clinic,
    ):
        clinic.ai_credits = -1
        db.session.commit()

        with pytest.raises(
            ValidationError,
            match="Insufficient AI credits",
        ):
            clinic_service.consume_ai_credit(
                clinic.id
            )

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.consume_ai_credit(
                99999
            )


# =====================================================================
# RESET MONTHLY AI USAGE
# =====================================================================


class TestResetMonthlyAIUsage:
    def test_resets_usage_for_all_clinics(
        self,
        make_clinic,
    ):
        first = make_clinic(
            name="Clinic One"
        )

        second = make_clinic(
            name="Clinic Two"
        )

        first.ai_requests_this_month = 25
        second.ai_requests_this_month = 50

        db.session.commit()

        result = clinic_service.reset_monthly_ai_usage.run()

        assert result >= 2

        db.session.refresh(first)
        db.session.refresh(second)

        assert first.ai_requests_this_month == 0
        assert second.ai_requests_this_month == 0

    def test_does_not_change_ai_credits(
        self,
        clinic,
    ):
        clinic.ai_credits = 100
        clinic.ai_requests_this_month = 25
        db.session.commit()

        clinic_service.reset_monthly_ai_usage.run()

        db.session.refresh(clinic)

        assert clinic.ai_requests_this_month == 0
        assert clinic.ai_credits == 100

    def test_returns_updated_row_count(
        self,
        make_clinic,
    ):
        make_clinic(name="Clinic One")
        make_clinic(name="Clinic Two")
        make_clinic(name="Clinic Three")

        result = clinic_service.reset_monthly_ai_usage.run()

        assert isinstance(result, int)
        assert result >= 3


# =====================================================================
# ENSURE CLINIC ACTIVE
# =====================================================================


class TestEnsureClinicActive:
    def test_returns_active_clinic(
        self,
        clinic,
    ):
        clinic.status = ClinicStatus.ACTIVE
        db.session.commit()

        result = clinic_service.ensure_clinic_active(
            clinic.id
        )

        assert result.id == clinic.id
        assert result.status == ClinicStatus.ACTIVE

    @pytest.mark.parametrize(
        "status",
        [
            ClinicStatus.INACTIVE,
            ClinicStatus.SUSPENDED,
        ],
    )
    def test_rejects_non_active_clinic(
        self,
        clinic,
        status,
    ):
        clinic.status = status
        db.session.commit()

        with pytest.raises(
            ValidationError,
            match=rf"Clinic {clinic.id} is not active",
        ):
            clinic_service.ensure_clinic_active(
                clinic.id
            )

    def test_missing_clinic_raises_not_found(self):
        with pytest.raises(
            NotFoundError,
            match=r"Clinic 99999 not found",
        ):
            clinic_service.ensure_clinic_active(
                99999
            )