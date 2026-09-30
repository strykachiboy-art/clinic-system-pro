from __future__ import annotations

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.core.enums.ai_enums import (
    AIFeature,
    AIApprovalStatus,
    AIRiskLevel,
)
from app.core.enums.clinic_enums import (
    ClinicStatus,
)
from app.core.enums.role_enums import (
    Role,
)
from app.core.exceptions import (
    ValidationError,
)

from app.extensions import db

from app.modules.ai.models.ai_model import (
    AILog,
)
from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardQuerySchema,
)
from app.modules.dashboard.services import (
    super_admin_dashboard_service,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_ai_log(
    db_session,
    clinic,
    *,
    feature=AIFeature.DRUG_INTERACTION_CHECK,
    risk_level=AIRiskLevel.LOW,
    approval_status=AIApprovalStatus.PENDING,
    credits_used=1,
    input_tokens=100,
    output_tokens=50,
    total_tokens=150,
    estimated_cost="0.010000",
    created_at=None,
    user_id=None,
    patient_id=None,
):
    ai_log = AILog(
        clinic_id=clinic.id,
        patient_id=patient_id,
        user_id=user_id,
        feature_used=feature,
        risk_level=risk_level,
        model="test-model",
        model_version="test-version",
        input_context_version="v1",
        generated_by_system=True,
        input_data={},
        output_data={},
        approval_status=approval_status,
        credits_used=credits_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=Decimal(str(estimated_cost)),
        cost_currency="USD",
        created_at=created_at or _utcnow(),
    )

    db_session.add(ai_log)
    db_session.flush()

    return ai_log


@pytest.fixture
def dashboard_helpers(monkeypatch):
    recent_activity = []

    recent_activity_mock = Mock(
        return_value=recent_activity,
    )

    monkeypatch.setattr(
        super_admin_dashboard_service,
        "build_recent_activity",
        recent_activity_mock,
    )

    return recent_activity_mock


@pytest.fixture
def super_admin(
    make_user,
):
    return make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
    )


def test_rejects_non_super_admin_role(
    make_user,
    clinic,
    dashboard_helpers,
):
    actor = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    with pytest.raises(
        ValidationError,
        match="Super administrator dashboard is not available",
    ):
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=actor,
        )


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
        Role.PATIENT,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.RECEPTIONIST,
        Role.ACCOUNTANT,
        Role.PARAMEDIC,
        Role.EMT,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.OTHER,
    ],
)
def test_rejects_all_non_super_admin_roles(
    make_user,
    clinic,
    dashboard_helpers,
    role,
):
    actor = make_user(
        clinic=clinic,
        role=role,
    )

    with pytest.raises(
        ValidationError,
        match="Super administrator dashboard is not available",
    ):
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=actor,
        )


def test_accepts_super_admin_role(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.context.role is Role.SUPER_ADMIN
    assert result.context.scope == "system"
    assert result.context.clinic_id is None


def test_rejects_inactive_super_admin(
    make_user,
    dashboard_helpers,
):
    actor = make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="User account is inactive",
    ):
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=actor,
        )


def test_super_admin_does_not_require_clinic(
    make_user,
    dashboard_helpers,
):
    actor = make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=actor,
        )
    )

    assert result.context.scope == "system"
    assert result.context.clinic_id is None


def test_empty_dashboard_returns_zero_counts(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.overview.total_clinics == 0
    assert result.overview.active_clinics == 0
    assert result.overview.suspended_clinics == 0
    assert result.overview.total_users == 1
    assert result.overview.active_users == 1
    assert result.overview.total_staff == 0
    assert result.overview.total_patients == 0

    assert result.access_control.total_users == 1
    assert result.access_control.active_users == 1
    assert result.access_control.inactive_users == 0
    assert result.access_control.total_admins == 0
    assert result.access_control.active_admins == 0
    assert result.access_control.total_super_admins == 1
    assert result.access_control.users_by_role == {
        Role.SUPER_ADMIN.value: 1,
    }

    assert result.ai.overview.total_ai_requests == 0
    assert result.ai.overview.total_credits_used == 0
    assert result.ai.overview.total_input_tokens == 0
    assert result.ai.overview.total_output_tokens == 0
    assert result.ai.overview.total_tokens == 0
    assert result.ai.overview.estimated_cost == Decimal("0")
    assert result.ai.overview.pending_reviews == 0
    assert result.ai.overview.approved_reviews == 0
    assert result.ai.overview.rejected_reviews == 0
    assert result.ai.overview.low_risk_results == 0
    assert result.ai.overview.medium_risk_results == 0
    assert result.ai.overview.high_risk_results == 0
    assert result.ai.overview.critical_risk_results == 0

    assert result.ai.feature_usage == []
    assert result.ai.risk_summary == []
    assert result.ai.approval_summary == []

    assert result.alerts == []


def test_counts_total_active_and_suspended_clinics(
    super_admin,
    make_clinic,
    dashboard_helpers,
):
    make_clinic(
        name="Active Clinic One",
        status=ClinicStatus.ACTIVE,
    )

    make_clinic(
        name="Active Clinic Two",
        status=ClinicStatus.ACTIVE,
    )

    make_clinic(
        name="Suspended Clinic",
        status=ClinicStatus.SUSPENDED,
    )

    make_clinic(
        name="Inactive Clinic",
        status=ClinicStatus.INACTIVE,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.overview.total_clinics == 4
    assert result.overview.active_clinics == 2
    assert result.overview.suspended_clinics == 1


def test_suspended_clinics_create_warning_alert(
    super_admin,
    make_clinic,
    dashboard_helpers,
):
    make_clinic(
        name="Suspended Clinic One",
        status=ClinicStatus.SUSPENDED,
    )

    make_clinic(
        name="Suspended Clinic Two",
        status=ClinicStatus.SUSPENDED,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert len(result.alerts) == 1

    alert = result.alerts[0]

    assert alert.key == "suspended_clinics"
    assert alert.severity == "warning"
    assert alert.title == "Suspended clinics"
    assert alert.count == 2
    assert (
        alert.description
        == "Clinics currently marked as suspended."
    )


def test_counts_users_and_active_users(
    super_admin,
    make_user,
    clinic,
    dashboard_helpers,
):
    make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=True,
    )

    make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        is_active=True,
    )

    make_user(
        clinic=clinic,
        role=Role.PATIENT,
        is_active=False,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.overview.total_users == 4
    assert result.overview.active_users == 3


def test_counts_staff_system_wide(
    super_admin,
    make_staff,
    clinic,
    dashboard_helpers,
):
    make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    make_staff(
        clinic=clinic,
        role=Role.NURSE,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.overview.total_staff == 2


def test_counts_patients_system_wide(
    super_admin,
    make_patient,
    clinic,
    dashboard_helpers,
):
    make_patient(
        clinic=clinic,
    )

    make_patient(
        clinic=clinic,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.overview.total_patients == 2


def test_access_control_counts_admins_and_super_admins(
    super_admin,
    make_user,
    clinic,
    dashboard_helpers,
):
    make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=True,
    )

    make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=False,
    )

    make_user(
        clinic=clinic,
        role=Role.SUPER_ADMIN,
        is_active=True,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.access_control.total_users == 4
    assert result.access_control.active_users == 3
    assert result.access_control.inactive_users == 1

    assert result.access_control.total_admins == 2
    assert result.access_control.active_admins == 1
    assert result.access_control.total_super_admins == 2


def test_users_by_role_contains_all_present_roles(
    super_admin,
    make_user,
    clinic,
    dashboard_helpers,
):
    make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    make_user(
        clinic=clinic,
        role=Role.PATIENT,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.access_control.users_by_role == {
        Role.ADMIN.value: 2,
        Role.DOCTOR.value: 1,
        Role.PATIENT.value: 1,
        Role.SUPER_ADMIN.value: 1,
    }


def test_access_control_inactive_users_are_derived_correctly(
    super_admin,
    make_user,
    clinic,
    dashboard_helpers,
):
    make_user(
        clinic=clinic,
        role=Role.ADMIN,
        is_active=True,
    )

    make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        is_active=False,
    )

    make_user(
        clinic=clinic,
        role=Role.PATIENT,
        is_active=False,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.access_control.total_users == 4
    assert result.access_control.active_users == 2
    assert result.access_control.inactive_users == 2


def test_ai_aggregates_count_requests_usage_and_cost(
    super_admin,
    db_session,
    make_clinic,
    dashboard_helpers,
):
    clinic_one = make_clinic(
        name="AI Clinic One",
    )

    clinic_two = make_clinic(
        name="AI Clinic Two",
    )

    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic_one,
        feature=AIFeature.DRUG_INTERACTION_CHECK,
        risk_level=AIRiskLevel.LOW,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=3,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost="0.010000",
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic_two,
        feature=AIFeature.TRIAGE_ASSISTANT,
        risk_level=AIRiskLevel.HIGH,
        approval_status=AIApprovalStatus.APPROVED,
        credits_used=5,
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        estimated_cost="0.025000",
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    ai = result.ai.overview

    assert ai.total_ai_requests == 2
    assert ai.total_credits_used == 8
    assert ai.total_input_tokens == 300
    assert ai.total_output_tokens == 150
    assert ai.total_tokens == 450
    assert ai.estimated_cost == Decimal("0.035000")

    assert ai.pending_reviews == 1
    assert ai.approved_reviews == 1
    assert ai.rejected_reviews == 0

    assert ai.low_risk_results == 1
    assert ai.medium_risk_results == 0
    assert ai.high_risk_results == 1
    assert ai.critical_risk_results == 0


def test_ai_aggregates_include_all_risk_levels(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.LOW,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.MEDIUM,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.HIGH,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.CRITICAL,
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    ai = result.ai.overview

    assert ai.low_risk_results == 1
    assert ai.medium_risk_results == 1
    assert ai.high_risk_results == 1
    assert ai.critical_risk_results == 1


def test_ai_aggregates_include_all_approval_states(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.PENDING,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.APPROVED,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.REJECTED,
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    ai = result.ai.overview

    assert ai.pending_reviews == 1
    assert ai.approved_reviews == 1
    assert ai.rejected_reviews == 1


def test_ai_feature_usage_is_grouped_and_sorted(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic,
        feature=AIFeature.TRIAGE_ASSISTANT,
        credits_used=3,
        estimated_cost="0.030000",
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        feature=AIFeature.TRIAGE_ASSISTANT,
        credits_used=2,
        estimated_cost="0.020000",
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        feature=AIFeature.DRUG_INTERACTION_CHECK,
        credits_used=4,
        estimated_cost="0.040000",
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    usage = result.ai.feature_usage

    assert len(usage) == 2

    assert usage[0].feature is (
        AIFeature.DRUG_INTERACTION_CHECK
    )
    assert usage[0].request_count == 1
    assert usage[0].credits_used == 4
    assert usage[0].estimated_cost == Decimal(
        "0.040000"
    )

    assert usage[1].feature is (
        AIFeature.TRIAGE_ASSISTANT
    )
    assert usage[1].request_count == 2
    assert usage[1].credits_used == 5
    assert usage[1].estimated_cost == Decimal(
        "0.050000"
    )


def test_ai_risk_summary_is_grouped_and_sorted(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.HIGH,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.LOW,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.HIGH,
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    summary = result.ai.risk_summary

    assert [
        item.risk_level
        for item in summary
    ] == [
        AIRiskLevel.HIGH,
        AIRiskLevel.LOW,
    ]

    counts = {
        item.risk_level: item.count
        for item in summary
    }

    assert counts[AIRiskLevel.HIGH] == 2
    assert counts[AIRiskLevel.LOW] == 1


def test_ai_approval_summary_is_grouped_and_sorted(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    today = _utcnow()

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.REJECTED,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.PENDING,
        created_at=today,
    )

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.APPROVED,
        created_at=today,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    summary = result.ai.approval_summary

    assert [
        item.approval_status
        for item in summary
    ] == [
        AIApprovalStatus.APPROVED,
        AIApprovalStatus.PENDING,
        AIApprovalStatus.REJECTED,
    ]

    counts = {
        item.approval_status: item.count
        for item in summary
    }

    assert counts[AIApprovalStatus.APPROVED] == 1
    assert counts[AIApprovalStatus.PENDING] == 1
    assert counts[AIApprovalStatus.REJECTED] == 1


def test_critical_ai_results_create_critical_alert(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.CRITICAL,
        created_at=_utcnow(),
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.CRITICAL,
        created_at=_utcnow(),
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    alert = next(
        item
        for item in result.alerts
        if item.key == "critical_ai_results"
    )

    assert alert.severity == "critical"
    assert alert.title == "Critical AI results"
    assert alert.count == 2
    assert (
        alert.description
        == (
            "AI results classified at critical risk "
            "within the selected dashboard period."
        )
    )


def test_pending_ai_reviews_create_warning_alert(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.PENDING,
        created_at=_utcnow(),
    )

    _make_ai_log(
        db_session,
        clinic,
        approval_status=AIApprovalStatus.PENDING,
        created_at=_utcnow(),
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    alert = next(
        item
        for item in result.alerts
        if item.key == "pending_ai_reviews"
    )

    assert alert.severity == "warning"
    assert alert.title == "Pending AI reviews"
    assert alert.count == 2
    assert (
        alert.description
        == "AI results awaiting review."
    )


def test_multiple_super_admin_alerts_are_returned_in_expected_order(
    super_admin,
    db_session,
    make_clinic,
    dashboard_helpers,
):
    make_clinic(
        name="Suspended Alert Clinic",
        status=ClinicStatus.SUSPENDED,
    )

    _make_ai_log(
        db_session,
        make_clinic(
            name="AI Alert Clinic",
        ),
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        created_at=_utcnow(),
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert [
        alert.key
        for alert in result.alerts
    ] == [
        "suspended_clinics",
        "critical_ai_results",
        "pending_ai_reviews",
    ]


def test_ai_period_filter_excludes_logs_outside_selected_period(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    target_date = _utcnow().date() - timedelta(days=5)

    inside = datetime.combine(
        target_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=10)

    outside = inside + timedelta(days=3)

    _make_ai_log(
        db_session,
        clinic,
        credits_used=10,
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        estimated_cost="1.000000",
        created_at=inside,
    )

    _make_ai_log(
        db_session,
        clinic,
        credits_used=20,
        input_tokens=2000,
        output_tokens=1000,
        total_tokens=3000,
        estimated_cost="2.000000",
        created_at=outside,
    )

    query = DashboardQuerySchema(
        date_from=target_date,
        date_to=target_date,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
            query=query,
        )
    )

    assert result.ai.overview.total_ai_requests == 1
    assert result.ai.overview.total_credits_used == 10
    assert result.ai.overview.total_input_tokens == 1000
    assert result.ai.overview.total_output_tokens == 500
    assert result.ai.overview.total_tokens == 1500
    assert result.ai.overview.estimated_cost == Decimal(
        "1.000000"
    )


def test_ai_period_filter_is_independent_of_clinic(
    super_admin,
    db_session,
    make_clinic,
    dashboard_helpers,
):
    target_date = _utcnow().date()

    clinic_one = make_clinic(
        name="System Clinic One",
    )

    clinic_two = make_clinic(
        name="System Clinic Two",
    )

    created_at = datetime.combine(
        target_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=8)

    _make_ai_log(
        db_session,
        clinic_one,
        credits_used=2,
        created_at=created_at,
    )

    _make_ai_log(
        db_session,
        clinic_two,
        credits_used=3,
        created_at=created_at,
    )

    query = DashboardQuerySchema(
        date_from=target_date,
        date_to=target_date,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
            query=query,
        )
    )

    assert result.ai.overview.total_ai_requests == 2
    assert result.ai.overview.total_credits_used == 5


def test_metrics_have_expected_keys(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert [
        metric.key
        for metric in result.metrics
    ] == [
        "active_clinics",
        "active_users",
        "administrators",
        "ai_requests",
    ]


def test_metrics_have_expected_units(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    metrics = {
        metric.key: metric
        for metric in result.metrics
    }

    assert metrics["active_clinics"].unit == "clinics"
    assert metrics["active_users"].unit == "users"
    assert metrics["administrators"].unit == "users"
    assert metrics["ai_requests"].unit == "requests"


def test_metrics_reflect_dashboard_values(
    super_admin,
    make_clinic,
    make_user,
    clinic,
    db_session,
    dashboard_helpers,
):
    make_clinic(
        name="Metric Active Clinic",
        status=ClinicStatus.ACTIVE,
    )

    make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    _make_ai_log(
        db_session,
        clinic,
        created_at=_utcnow(),
        credits_used=3,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    metrics = {
        metric.key: metric
        for metric in result.metrics
    }

    assert metrics["active_clinics"].value == 2
    assert metrics["active_users"].value == 2
    assert metrics["administrators"].value == 1
    assert metrics["ai_requests"].value == 1


def test_recent_activity_is_requested_system_wide(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    dashboard_helpers.assert_called_once_with(
        clinic_id=None,
    )

    assert result.recent_activity == (
        dashboard_helpers.return_value
    )


def test_context_is_system_scoped(
    super_admin,
    dashboard_helpers,
):
    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
        )
    )

    assert result.context.role is Role.SUPER_ADMIN
    assert result.context.scope == "system"
    assert result.context.clinic_id is None
    assert result.context.generated_at is not None


def test_custom_period_is_passed_to_ai_aggregates(
    super_admin,
    monkeypatch,
    dashboard_helpers,
):
    target_date = date.today() - timedelta(days=7)

    ai_data = {
        "total_ai_requests": 0,
        "total_credits_used": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost": Decimal("0"),
        "pending_reviews": 0,
        "approved_reviews": 0,
        "rejected_reviews": 0,
        "low_risk_results": 0,
        "medium_risk_results": 0,
        "high_risk_results": 0,
        "critical_risk_results": 0,
        "feature_usage": [],
        "risk_summary": [],
        "approval_summary": [],
    }

    ai_mock = Mock(
        return_value=ai_data,
    )

    monkeypatch.setattr(
        super_admin_dashboard_service,
        "build_ai_aggregates",
        ai_mock,
    )

    query = DashboardQuerySchema(
        date_from=target_date,
        date_to=target_date,
    )

    super_admin_dashboard_service.get_super_admin_dashboard(
        actor=super_admin,
        query=query,
    )

    ai_mock.assert_called_once()

    period = ai_mock.call_args.kwargs["period"]

    assert period.date_from == target_date
    assert period.date_to == target_date


def test_complete_super_admin_dashboard_summary(
    super_admin,
    make_clinic,
    make_user,
    make_patient,
    make_staff,
    db_session,
    dashboard_helpers,
):
    active_clinic = make_clinic(
        name="Complete Active Clinic",
        status=ClinicStatus.ACTIVE,
    )

    suspended_clinic = make_clinic(
        name="Complete Suspended Clinic",
        status=ClinicStatus.SUSPENDED,
    )

    make_user(
        clinic=active_clinic,
        role=Role.ADMIN,
        is_active=True,
    )

    make_user(
        clinic=active_clinic,
        role=Role.DOCTOR,
        is_active=True,
    )

    make_user(
        clinic=suspended_clinic,
        role=Role.PATIENT,
        is_active=False,
    )

    make_staff(
        clinic=active_clinic,
        role=Role.DOCTOR,
    )

    make_staff(
        clinic=suspended_clinic,
        role=Role.NURSE,
    )

    make_patient(
        clinic=active_clinic,
    )

    make_patient(
        clinic=suspended_clinic,
    )

    target_date = _utcnow().date()

    created_at = datetime.combine(
        target_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=12)

    _make_ai_log(
        db_session,
        active_clinic,
        feature=AIFeature.LAB_RESULT_INTERPRETER,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=7,
        input_tokens=400,
        output_tokens=200,
        total_tokens=600,
        estimated_cost="0.075000",
        created_at=created_at,
    )

    query = DashboardQuerySchema(
        date_from=target_date,
        date_to=target_date,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
            query=query,
        )
    )

    assert result.context.role is Role.SUPER_ADMIN
    assert result.context.scope == "system"
    assert result.context.clinic_id is None

    assert result.overview.total_clinics == 2
    assert result.overview.active_clinics == 1
    assert result.overview.suspended_clinics == 1

    assert result.overview.total_users == 6
    assert result.overview.active_users == 5
    assert result.overview.total_staff == 2
    assert result.overview.total_patients == 2

    assert result.access_control.total_users == 6
    assert result.access_control.active_users == 5
    assert result.access_control.inactive_users == 1
    assert result.access_control.total_admins == 1
    assert result.access_control.active_admins == 1
    assert result.access_control.total_super_admins == 1

    assert (
        result.access_control.users_by_role[
            Role.SUPER_ADMIN.value
        ]
        == 1
    )

    assert (
        result.access_control.users_by_role[
            Role.ADMIN.value
        ]
        == 1
    )

    assert (
        result.access_control.users_by_role[
            Role.DOCTOR.value
        ]
        == 2
    )

    assert (
        result.access_control.users_by_role[
            Role.PATIENT.value
        ]
        == 1
    )

    assert (
        result.access_control.users_by_role[
            Role.NURSE.value
        ]
        == 1
    )

    assert result.ai.overview.total_ai_requests == 1
    assert result.ai.overview.total_credits_used == 7
    assert result.ai.overview.total_input_tokens == 400
    assert result.ai.overview.total_output_tokens == 200
    assert result.ai.overview.total_tokens == 600
    assert result.ai.overview.estimated_cost == Decimal(
        "0.075000"
    )

    assert result.ai.overview.pending_reviews == 1
    assert result.ai.overview.approved_reviews == 0
    assert result.ai.overview.rejected_reviews == 0

    assert result.ai.overview.low_risk_results == 0
    assert result.ai.overview.medium_risk_results == 0
    assert result.ai.overview.high_risk_results == 0
    assert result.ai.overview.critical_risk_results == 1

    assert len(result.ai.feature_usage) == 1
    assert (
        result.ai.feature_usage[0].feature
        is AIFeature.LAB_RESULT_INTERPRETER
    )

    assert len(result.ai.risk_summary) == 1
    assert (
        result.ai.risk_summary[0].risk_level
        is AIRiskLevel.CRITICAL
    )

    assert len(result.ai.approval_summary) == 1
    assert (
        result.ai.approval_summary[0].approval_status
        is AIApprovalStatus.PENDING
    )

    assert [
        alert.key
        for alert in result.alerts
    ] == [
        "suspended_clinics",
        "critical_ai_results",
        "pending_ai_reviews",
    ]

    metrics = {
        metric.key: metric
        for metric in result.metrics
    }

    assert metrics["active_clinics"].value == 1
    assert metrics["active_users"].value == 5
    assert metrics["administrators"].value == 1
    assert metrics["ai_requests"].value == 1


def test_ai_records_outside_selected_period_do_not_create_alerts(
    super_admin,
    db_session,
    clinic,
    dashboard_helpers,
):
    target_date = _utcnow().date() - timedelta(days=3)

    outside = datetime.combine(
        target_date + timedelta(days=2),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    _make_ai_log(
        db_session,
        clinic,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        created_at=outside,
    )

    query = DashboardQuerySchema(
        date_from=target_date,
        date_to=target_date,
    )

    result = (
        super_admin_dashboard_service.get_super_admin_dashboard(
            actor=super_admin,
            query=query,
        )
    )

    assert result.ai.overview.total_ai_requests == 0
    assert result.ai.overview.critical_risk_results == 0
    assert result.ai.overview.pending_reviews == 0
    assert result.alerts == []