from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from app.core.enums.audit_enums import AuditAction
from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.extensions import db
from app.modules.staff.models.excuse_model import Excuse
from app.modules.staff.models.staff_model import LeaveRequest
from app.modules.staff.services import excuse_service


# ============================================================================
# HELPERS
# ============================================================================


def _make_leave(
    staff_id: int,
    *,
    leave_type: LeaveType = LeaveType.ANNUAL,
    status: LeaveStatus = LeaveStatus.PENDING,
    start_date: date | None = None,
    end_date: date | None = None,
    reason: str | None = "Annual leave",
    reviewed_by_user_id: int | None = None,
    reviewed_at=None,
):
    """
    Create a valid LeaveRequest directly for excuse-service tests.
    """

    start_date = start_date or date.today() + timedelta(days=5)
    end_date = end_date or start_date + timedelta(days=2)

    leave = LeaveRequest(
        staff_id=staff_id,
        leave_type=leave_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        reviewed_by_user_id=reviewed_by_user_id,
        reviewed_at=reviewed_at,
    )

    db.session.add(leave)
    db.session.flush()

    return leave


def _make_excuse(
    staff_id: int,
    *,
    leave_request_id: int | None = None,
    excuse_type: ExcuseType = ExcuseType.MEDICAL,
    status: ExcuseStatus = ExcuseStatus.PENDING,
    description: str = "Medical excuse",
    document_url: str | None = None,
    rejection_reason: str | None = None,
    reviewed_by_user_id: int | None = None,
    reviewed_at=None,
):
    """
    Create an Excuse directly for lookup/review tests.
    """

    excuse = Excuse(
        staff_id=staff_id,
        leave_request_id=leave_request_id,
        excuse_type=excuse_type,
        status=status,
        description=description,
        document_url=document_url,
        rejection_reason=rejection_reason,
        reviewed_by_user_id=reviewed_by_user_id,
        reviewed_at=reviewed_at,
    )

    db.session.add(excuse)
    db.session.flush()

    return excuse


# ============================================================================
# CREATE EXCUSE
# ============================================================================


def test_create_excuse_success(
    clinic,
    make_staff,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    audit = Mock()

    monkeypatch.setattr(
        excuse_service,
        "create_audit_log",
        audit,
    )

    result = excuse_service.create_excuse(
        clinic_id=clinic.id,
        staff_id=staff.id,
        excuse_type=ExcuseType.MEDICAL,
        description="  Doctor's medical excuse  ",
        document_url="  https://example.com/document.pdf  ",
    )

    assert result.id is not None
    assert result.staff_id == staff.id
    assert result.leave_request_id is None
    assert result.excuse_type == ExcuseType.MEDICAL
    assert result.status == ExcuseStatus.PENDING
    assert result.description == "Doctor's medical excuse"
    assert result.document_url == "https://example.com/document.pdf"
    assert result.rejection_reason is None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "Excuse"
    assert kwargs["entity_id"] == result.id
    assert kwargs["user_id"] == staff.user_id


def test_create_excuse_without_linked_user_succeeds(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    staff.user_id = None
    db.session.flush()

    result = excuse_service.create_excuse(
        clinic_id=clinic.id,
        staff_id=staff.id,
        excuse_type=ExcuseType.MEDICAL,
        description="Medical excuse",
    )

    assert result.staff_id == staff.id
    assert result.status == ExcuseStatus.PENDING
    assert result.leave_request_id is None


def test_create_excuse_links_valid_leave_request(
    clinic,
    make_staff,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    leave = _make_leave(
        staff.id,
    )

    audit = Mock()

    monkeypatch.setattr(
        excuse_service,
        "create_audit_log",
        audit,
    )

    result = excuse_service.create_excuse(
        clinic_id=clinic.id,
        staff_id=staff.id,
        excuse_type=ExcuseType.MEDICAL,
        description="Medical excuse",
        leave_request_id=leave.id,
    )

    assert result.leave_request_id == leave.id
    assert result.staff_id == staff.id

    kwargs = audit.call_args.kwargs

    assert kwargs["new_value"]["leave_request_id"] == leave.id


def test_create_excuse_rejects_foreign_staff(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(NotFoundError):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description="Medical excuse",
        )


@pytest.mark.parametrize(
    "status",
    [
        StaffStatus.SUSPENDED,
        StaffStatus.TERMINATED,
    ],
)
def test_create_excuse_rejects_staff_who_cannot_submit(
    clinic,
    make_staff,
    status,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        status=status,
    )

    with pytest.raises(
        ConflictError,
        match="cannot submit an excuse",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description="Medical excuse",
        )


@pytest.mark.parametrize(
    "description",
    [
        None,
        "",
        "   ",
    ],
)
def test_create_excuse_rejects_missing_description(
    clinic,
    make_staff,
    description,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="Excuse description is required",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description=description,
        )


def test_create_excuse_rejects_long_description(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="cannot exceed 2000 characters",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description="x" * 2001,
        )


def test_create_excuse_rejects_invalid_excuse_type(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="Invalid excuse type",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type="medical",
            description="Medical excuse",
        )


def test_create_excuse_normalizes_empty_document_url_to_none(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    result = excuse_service.create_excuse(
        clinic_id=clinic.id,
        staff_id=staff.id,
        excuse_type=ExcuseType.MEDICAL,
        description="Medical excuse",
        document_url="   ",
    )

    assert result.document_url is None


def test_create_excuse_rejects_long_document_url(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="Document URL cannot exceed 500 characters",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description="Medical excuse",
            document_url="x" * 501,
        )


def test_create_excuse_rejects_foreign_leave_request(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    foreign_staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    leave = _make_leave(
        foreign_staff.id,
    )

    with pytest.raises(NotFoundError):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff.id,
            excuse_type=ExcuseType.MEDICAL,
            description="Medical excuse",
            leave_request_id=leave.id,
        )


def test_create_excuse_rejects_leave_request_for_different_staff(
    clinic,
    make_staff,
):
    staff_a = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    staff_b = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    leave = _make_leave(
        staff_b.id,
    )

    with pytest.raises(
        ConflictError,
        match="does not belong",
    ):
        excuse_service.create_excuse(
            clinic_id=clinic.id,
            staff_id=staff_a.id,
            excuse_type=ExcuseType.MEDICAL,
            description="Medical excuse",
            leave_request_id=leave.id,
        )


# ============================================================================
# LOOKUPS
# ============================================================================


def test_get_excuse_returns_clinic_owned_excuse(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    excuse = _make_excuse(
        staff.id,
    )

    result = excuse_service.get_excuse(
        excuse_id=excuse.id,
        clinic_id=clinic.id,
    )

    assert result.id == excuse.id


def test_get_excuse_enforces_clinic_isolation(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(NotFoundError):
        excuse_service.get_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
        )


def test_get_excuse_missing_raises_not_found(
    clinic,
):
    with pytest.raises(NotFoundError):
        excuse_service.get_excuse(
            excuse_id=999999,
            clinic_id=clinic.id,
        )


# ============================================================================
# LIST EXCUSES
# ============================================================================


def test_list_excuses_returns_only_requested_clinic(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    local_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    foreign_staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    local_excuse = _make_excuse(
        local_staff.id,
    )

    foreign_excuse = _make_excuse(
        foreign_staff.id,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
    )

    ids = {excuse.id for excuse in results}

    assert local_excuse.id in ids
    assert foreign_excuse.id not in ids


def test_list_excuses_filters_by_staff(
    clinic,
    make_staff,
):
    staff_a = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    staff_b = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    matching = _make_excuse(
        staff_a.id,
    )

    _make_excuse(
        staff_b.id,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
        staff_id=staff_a.id,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {matching.id}


def test_list_excuses_filters_by_leave_request(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    leave = _make_leave(
        staff.id,
    )

    matching = _make_excuse(
        staff.id,
        leave_request_id=leave.id,
    )

    _make_excuse(
        staff.id,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
        leave_request_id=leave.id,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {matching.id}


def test_list_excuses_filters_by_type(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    medical = _make_excuse(
        staff.id,
        excuse_type=ExcuseType.MEDICAL,
    )

    _make_excuse(
        staff.id,
        excuse_type=ExcuseType.PERSONAL,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
        excuse_type=ExcuseType.MEDICAL,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {medical.id}


def test_list_excuses_filters_by_status(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    pending = _make_excuse(
        staff.id,
        status=ExcuseStatus.PENDING,
    )

    _make_excuse(
        staff.id,
        status=ExcuseStatus.REJECTED,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
        status=ExcuseStatus.PENDING,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {pending.id}


def test_list_excuses_supports_combined_filters(
    clinic,
    make_staff,
):
    staff_a = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    staff_b = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    leave = _make_leave(
        staff_a.id,
    )

    matching = _make_excuse(
        staff_a.id,
        leave_request_id=leave.id,
        excuse_type=ExcuseType.MEDICAL,
        status=ExcuseStatus.PENDING,
    )

    _make_excuse(
        staff_a.id,
        excuse_type=ExcuseType.PERSONAL,
        status=ExcuseStatus.PENDING,
    )

    _make_excuse(
        staff_b.id,
        leave_request_id=leave.id,
        excuse_type=ExcuseType.MEDICAL,
        status=ExcuseStatus.PENDING,
    )

    results = excuse_service.list_excuses(
        clinic_id=clinic.id,
        staff_id=staff_a.id,
        leave_request_id=leave.id,
        excuse_type=ExcuseType.MEDICAL,
        status=ExcuseStatus.PENDING,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {matching.id}


# ============================================================================
# STAFF EXCUSES / MY EXCUSES
# ============================================================================


def test_list_staff_excuses_returns_staff_excuses(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    first = _make_excuse(
        staff.id,
    )

    second = _make_excuse(
        staff.id,
        description="Second excuse",
    )

    results = excuse_service.list_staff_excuses(
        clinic_id=clinic.id,
        staff_id=staff.id,
    )

    ids = {excuse.id for excuse in results}

    assert ids == {first.id, second.id}


def test_list_staff_excuses_enforces_staff_clinic(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(NotFoundError):
        excuse_service.list_staff_excuses(
            clinic_id=clinic.id,
            staff_id=staff.id,
        )


def test_get_my_excuses_delegates_to_staff_scope(
    clinic,
    make_staff,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    expected = [Mock(), Mock()]

    list_staff_mock = Mock(
        return_value=expected,
    )

    monkeypatch.setattr(
        excuse_service,
        "list_staff_excuses",
        list_staff_mock,
    )

    result = excuse_service.get_my_excuses(
        clinic_id=clinic.id,
        staff_id=staff.id,
    )

    assert result == expected

    list_staff_mock.assert_called_once_with(
        clinic_id=clinic.id,
        staff_id=staff.id,
    )


# ============================================================================
# APPROVE EXCUSE
# ============================================================================


def test_approve_excuse_success(
    clinic,
    make_staff,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
        status=ExcuseStatus.PENDING,
        rejection_reason="Old reason",
    )

    audit = Mock()

    monkeypatch.setattr(
        excuse_service,
        "create_audit_log",
        audit,
    )

    result = excuse_service.approve_excuse(
        excuse_id=excuse.id,
        clinic_id=clinic.id,
        reviewer_user_id=reviewer.user_id,
    )

    assert result.status == ExcuseStatus.APPROVED
    assert result.rejection_reason is None
    assert result.reviewed_by_user_id == reviewer.user_id
    assert result.reviewed_at is not None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.STATUS_CHANGE
    assert kwargs["entity_type"] == "Excuse"
    assert kwargs["entity_id"] == excuse.id
    assert kwargs["user_id"] == reviewer.user_id
    assert kwargs["old_value"]["status"] == ExcuseStatus.PENDING.value
    assert kwargs["new_value"]["status"] == ExcuseStatus.APPROVED.value


@pytest.mark.parametrize(
    "status",
    [
        ExcuseStatus.APPROVED,
        ExcuseStatus.REJECTED,
    ],
)
def test_approve_excuse_rejects_non_pending_status(
    clinic,
    make_staff,
    status,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
        status=status,
    )

    with pytest.raises(
        ConflictError,
        match="already",
    ):
        excuse_service.approve_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_approve_excuse_requires_admin(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Only administrators",
    ):
        excuse_service.approve_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_approve_excuse_rejects_inactive_reviewer(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
        user_is_active=False,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Inactive users",
    ):
        excuse_service.approve_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_approve_excuse_rejects_reviewer_from_other_clinic(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=other_clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(NotFoundError):
        excuse_service.approve_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_approve_excuse_rejects_foreign_excuse(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(NotFoundError):
        excuse_service.approve_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


# ============================================================================
# REJECT EXCUSE
# ============================================================================


def test_reject_excuse_success_with_reason(
    clinic,
    make_staff,
    monkeypatch,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    audit = Mock()

    monkeypatch.setattr(
        excuse_service,
        "create_audit_log",
        audit,
    )

    result = excuse_service.reject_excuse(
        excuse_id=excuse.id,
        clinic_id=clinic.id,
        reviewer_user_id=reviewer.user_id,
        reason="  Documentation incomplete  ",
    )

    assert result.status == ExcuseStatus.REJECTED
    assert result.rejection_reason == "Documentation incomplete"
    assert result.reviewed_by_user_id == reviewer.user_id
    assert result.reviewed_at is not None

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.STATUS_CHANGE
    assert kwargs["entity_type"] == "Excuse"
    assert kwargs["entity_id"] == excuse.id
    assert kwargs["user_id"] == reviewer.user_id
    assert kwargs["new_value"]["status"] == ExcuseStatus.REJECTED.value
    assert kwargs["new_value"]["rejection_reason"] == (
        "Documentation incomplete"
    )


def test_reject_excuse_allows_no_reason(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    result = excuse_service.reject_excuse(
        excuse_id=excuse.id,
        clinic_id=clinic.id,
        reviewer_user_id=reviewer.user_id,
        reason=None,
    )

    assert result.status == ExcuseStatus.REJECTED
    assert result.rejection_reason is None


def test_reject_excuse_rejects_blank_reason(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Rejection reason cannot be empty",
    ):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
            reason="   ",
        )


def test_reject_excuse_rejects_long_reason(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Rejection reason cannot exceed 2000 characters",
    ):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
            reason="x" * 2001,
        )


@pytest.mark.parametrize(
    "status",
    [
        ExcuseStatus.APPROVED,
        ExcuseStatus.REJECTED,
    ],
)
def test_reject_excuse_rejects_non_pending_status(
    clinic,
    make_staff,
    status,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
        status=status,
    )

    with pytest.raises(
        ConflictError,
        match="already",
    ):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_reject_excuse_requires_admin(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.RECEPTIONIST,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Only administrators",
    ):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_reject_excuse_rejects_inactive_reviewer(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
        user_is_active=False,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(
        ValidationError,
        match="Inactive users",
    ):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )


def test_reject_excuse_rejects_foreign_excuse(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        clinic=other_clinic,
        role=Role.DOCTOR,
    )

    reviewer = make_staff(
        clinic=clinic,
        role=Role.ADMIN,
    )

    excuse = _make_excuse(
        staff.id,
    )

    with pytest.raises(NotFoundError):
        excuse_service.reject_excuse(
            excuse_id=excuse.id,
            clinic_id=clinic.id,
            reviewer_user_id=reviewer.user_id,
        )