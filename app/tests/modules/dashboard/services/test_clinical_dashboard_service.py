from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.enums.ai_enums import (
    AIFeature,
    AIApprovalStatus,
    AIRiskLevel,
)
from app.core.enums.appointment_enums import AppointmentStatus
from app.core.enums.chat_enums import (
    MentionType,
    MessagePriority,
    MessageStatus,
    ParticipantStatus,
)
from app.core.enums.consultation_enums import ConsultationStatus
from app.core.enums.lab_enums import LabOrderStatus
from app.core.enums.prescription_enums import PrescriptionStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
)
from app.core.exceptions import ValidationError

from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardQuerySchema,
)

from app.modules.dashboard.services.clinical_dashboard_service import (
    CLINICAL_ROLES,
    get_clinical_dashboard,
)

from app.modules.ward.models.ward_model import Admission

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today_start() -> datetime:
    return datetime.combine(
        _utcnow().date(),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def _today_at(hour: int = 12) -> datetime:
    return _today_start() + timedelta(
        hours=hour,
    )


# ============================================================================
# ACCESS / VALIDATION
# ============================================================================


def test_get_clinical_dashboard_rejects_non_clinical_role(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    with pytest.raises(
        ValidationError,
        match="Clinical dashboard is not available",
    ):
        get_clinical_dashboard(
            actor=actor,
        )


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.PARAMEDIC,
        Role.EMT,
    ],
)
def test_get_clinical_dashboard_accepts_all_clinical_roles(
    clinic,
    make_staff,
    role,
):
    staff = make_staff(
        clinic,
        role=role,
    )

    dashboard = get_clinical_dashboard(
        actor=staff.user,
    )

    assert dashboard.context.role is role
    assert dashboard.context.scope == "clinic"
    assert dashboard.context.clinic_id == clinic.id


def test_clinical_roles_constant_contains_all_supported_roles():
    assert CLINICAL_ROLES == {
        Role.DOCTOR,
        Role.NURSE,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
        Role.PARAMEDIC,
        Role.EMT,
    }


def test_get_clinical_dashboard_rejects_inactive_user(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="User account is inactive",
    ):
        get_clinical_dashboard(
            actor=actor,
        )


def test_get_clinical_dashboard_rejects_missing_clinic(
    make_user,
):
    actor = make_user(
        None,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="Clinical user is not associated with a valid clinic",
    ):
        get_clinical_dashboard(
            actor=actor,
        )


def test_get_clinical_dashboard_rejects_missing_staff_profile(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    with pytest.raises(
        ValidationError,
        match="Clinical user is not associated with a staff profile",
    ):
        get_clinical_dashboard(
            actor=actor,
        )


def test_get_clinical_dashboard_rejects_inactive_staff_profile(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ON_LEAVE,
    )

    with pytest.raises(
        ValidationError,
        match="Clinical staff profile is not active",
    ):
        get_clinical_dashboard(
            actor=staff.user,
        )


# ============================================================================
# OVERVIEW
# ============================================================================


def test_get_clinical_dashboard_builds_overview_metrics(
    clinic,
    make_staff,
    make_patient,
    make_appointment,
    make_consultation,
    make_lab_test,
    make_lab_order,
    make_prescription,
    make_ward,
    make_bed,
    db_session,
):
    from app.core.enums.lab_enums import LabOrderStatus

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    appointment = make_appointment(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=AppointmentStatus.SCHEDULED,
        scheduled_start=_today_at(),
        scheduled_end=_today_at(13),
    )

    confirmed_appointment = make_appointment(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=AppointmentStatus.CONFIRMED,
        scheduled_start=_today_at(14),
        scheduled_end=_today_at(15),
    )

    tomorrow_appointment = make_appointment(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=AppointmentStatus.SCHEDULED,
        scheduled_start=_today_at(10) + timedelta(days=1),
        scheduled_end=_today_at(11) + timedelta(days=1),
    )

    assert appointment.id != confirmed_appointment.id
    assert tomorrow_appointment.id != appointment.id

    make_consultation(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=ConsultationStatus.IN_PROGRESS,
    )

    completed_consultation = make_consultation(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=ConsultationStatus.COMPLETED,
    )

    lab_test = make_lab_test(
        clinic,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=staff,
        tests=[lab_test],
        status=LabOrderStatus.ORDERED,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=staff,
        tests=[lab_test],
        status=LabOrderStatus.COMPLETED,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=PrescriptionStatus.ACTIVE,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=staff,
        status=PrescriptionStatus.COMPLETED,
    )

    ward = make_ward(
        clinic,
    )

    occupied_bed = make_bed(
        ward,
        status=BedStatus.OCCUPIED,
    )

    admission = Admission(
        patient_id=patient.id,
        bed_id=occupied_bed.id,
        admitted_by_id=staff.id,
        status=AdmissionStatus.ADMITTED,
    )

    db_session.add(admission)
    db_session.flush()

    dashboard = get_clinical_dashboard(
        actor=staff.user,
    )

    overview = dashboard.overview

    assert overview.appointments_today == 2
    assert overview.confirmed_appointments_today == 1
    assert overview.pending_consultations == 1
    assert overview.pending_lab_orders == 1
    assert overview.active_prescriptions == 1
    assert overview.active_admissions == 1

    assert completed_consultation.id > 0


# ============================================================================
# CLINICAL ROLE-SPECIFIC LAB / PRESCRIPTION SCOPING
# ============================================================================


def test_doctor_only_sees_own_pending_lab_orders(
    clinic,
    make_staff,
    make_patient,
    make_lab_test,
    make_lab_order,
):
    doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    lab_test = make_lab_test(
        clinic,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=doctor,
        tests=[lab_test],
        status=LabOrderStatus.ORDERED,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=other_doctor,
        tests=[lab_test],
        status=LabOrderStatus.IN_PROGRESS,
    )

    dashboard = get_clinical_dashboard(
        actor=doctor.user,
    )

    assert dashboard.overview.pending_lab_orders == 1


def test_lab_technician_sees_all_pending_lab_orders_in_clinic(
    clinic,
    make_staff,
    make_patient,
    make_lab_test,
    make_lab_order,
    make_clinic,
):
    lab_technician = make_staff(
        clinic,
        role=Role.LAB_TECHNICIAN,
    )

    doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_clinic = make_clinic()

    other_doctor = make_staff(
        other_clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    other_patient = make_patient(
        other_clinic,
    )

    lab_test = make_lab_test(
        clinic,
    )

    other_lab_test = make_lab_test(
        other_clinic,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=doctor,
        tests=[lab_test],
        status=LabOrderStatus.ORDERED,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=doctor,
        tests=[lab_test],
        status=LabOrderStatus.SAMPLE_COLLECTED,
    )

    make_lab_order(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_doctor,
        tests=[other_lab_test],
        status=LabOrderStatus.ORDERED,
    )

    dashboard = get_clinical_dashboard(
        actor=lab_technician.user,
    )

    assert dashboard.overview.pending_lab_orders == 2


def test_doctor_only_sees_own_active_prescriptions(
    clinic,
    make_staff,
    make_patient,
    make_prescription,
):
    doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=doctor,
        status=PrescriptionStatus.ACTIVE,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=other_doctor,
        status=PrescriptionStatus.ACTIVE,
    )

    dashboard = get_clinical_dashboard(
        actor=doctor.user,
    )

    assert dashboard.overview.active_prescriptions == 1


def test_pharmacist_sees_all_active_prescriptions_in_clinic(
    clinic,
    make_staff,
    make_patient,
    make_prescription,
    make_clinic,
):
    pharmacist = make_staff(
        clinic,
        role=Role.PHARMACIST,
    )

    doctor = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_clinic = make_clinic()

    other_doctor = make_staff(
        other_clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    other_patient = make_patient(
        other_clinic,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=doctor,
        status=PrescriptionStatus.ACTIVE,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=pharmacist,
        status=PrescriptionStatus.ACTIVE,
    )

    make_prescription(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_doctor,
        status=PrescriptionStatus.ACTIVE,
    )

    dashboard = get_clinical_dashboard(
        actor=pharmacist.user,
    )

    assert dashboard.overview.active_prescriptions == 2


# ============================================================================
# CLINIC ISOLATION
# ============================================================================


def test_clinical_dashboard_enforces_clinic_isolation(
    clinic,
    make_clinic,
    make_staff,
    make_patient,
    make_appointment,
    make_consultation,
    make_lab_test,
    make_lab_order,
    make_prescription,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_clinic = make_clinic()

    other_staff = make_staff(
        other_clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    other_patient = make_patient(
        other_clinic,
    )

    make_appointment(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        status=AppointmentStatus.SCHEDULED,
        scheduled_start=_today_at(),
        scheduled_end=_today_at(13),
    )

    make_appointment(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_staff,
        status=AppointmentStatus.CONFIRMED,
        scheduled_start=_today_at(),
        scheduled_end=_today_at(13),
    )

    make_consultation(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        status=ConsultationStatus.IN_PROGRESS,
    )

    make_consultation(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_staff,
        status=ConsultationStatus.IN_PROGRESS,
    )

    lab_test = make_lab_test(
        clinic,
    )

    other_lab_test = make_lab_test(
        other_clinic,
    )

    make_lab_order(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        tests=[lab_test],
        status=LabOrderStatus.ORDERED,
    )

    make_lab_order(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_staff,
        tests=[other_lab_test],
        status=LabOrderStatus.ORDERED,
    )

    make_prescription(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        status=PrescriptionStatus.ACTIVE,
    )

    make_prescription(
        clinic=other_clinic,
        patient=other_patient,
        staff=other_staff,
        status=PrescriptionStatus.ACTIVE,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    assert dashboard.overview.appointments_today == 1
    assert dashboard.overview.pending_consultations == 1
    assert dashboard.overview.pending_lab_orders == 1
    assert dashboard.overview.active_prescriptions == 1


# ============================================================================
# AI AGGREGATES
# ============================================================================


def test_clinical_dashboard_builds_ai_summary_for_authenticated_user(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    now = datetime.now(
        timezone.utc,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.DRUG_INTERACTION_CHECK,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=3,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost=Decimal("0.030000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.TRIAGE_ASSISTANT,
        risk_level=AIRiskLevel.HIGH,
        approval_status=AIApprovalStatus.APPROVED,
        credits_used=2,
        input_tokens=80,
        output_tokens=40,
        total_tokens=120,
        estimated_cost=Decimal("0.020000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.LAB_RESULT_INTERPRETER,
        risk_level=AIRiskLevel.LOW,
        approval_status=AIApprovalStatus.REJECTED,
        credits_used=1,
        input_tokens=20,
        output_tokens=10,
        total_tokens=30,
        estimated_cost=Decimal("0.010000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=other_staff.user,
        feature_used=AIFeature.DRUG_INTERACTION_CHECK,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=10,
        input_tokens=500,
        output_tokens=250,
        total_tokens=750,
        estimated_cost=Decimal("0.100000"),
        created_at=now,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    ai = dashboard.ai

    assert ai.overview.ai_requests == 3
    assert ai.overview.pending_reviews == 1
    assert ai.overview.high_risk_results == 1
    assert ai.overview.critical_risk_results == 1
    assert ai.overview.approved_results == 1
    assert ai.overview.rejected_results == 1

    assert {
        item.feature: item.request_count
        for item in ai.feature_usage
    } == {
        AIFeature.DRUG_INTERACTION_CHECK: 1,
        AIFeature.TRIAGE_ASSISTANT: 1,
        AIFeature.LAB_RESULT_INTERPRETER: 1,
    }

    assert {
        item.risk_level: item.count
        for item in ai.risk_summary
    } == {
        AIRiskLevel.LOW: 1,
        AIRiskLevel.HIGH: 1,
        AIRiskLevel.CRITICAL: 1,
    }

    assert {
        item.approval_status: item.count
        for item in ai.review_summary
    } == {
        AIApprovalStatus.PENDING: 1,
        AIApprovalStatus.APPROVED: 1,
        AIApprovalStatus.REJECTED: 1,
    }


def test_clinical_dashboard_excludes_ai_logs_outside_selected_period(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    today = _utcnow().date()
    yesterday = today - timedelta(days=1)

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        created_at=_today_at(),
        credits_used=1,
        total_tokens=10,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        created_at=datetime.combine(
            yesterday,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        + timedelta(hours=12),
        credits_used=5,
        total_tokens=50,
    )

    query = DashboardQuerySchema(
        date_from=today,
        date_to=today,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
        query=query,
    )

    assert dashboard.ai.overview.ai_requests == 1


# ============================================================================
# CHAT
# ============================================================================


def test_clinical_dashboard_builds_chat_summary_and_priority_alert(
    clinic,
    make_staff,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
    make_message_mention,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    other_user = make_user(
        clinic,
        role=Role.NURSE,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor_staff.user,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=actor_staff.user,
        status=ParticipantStatus.ACCEPTED,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=other_user,
        status=ParticipantStatus.ACCEPTED,
    )

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=other_user,
        status=MessageStatus.SENT,
        priority=MessagePriority.URGENT,
    )

    make_message_read_receipt(
        clinic=clinic,
        message=message,
        user=actor_staff.user,
    )

    make_message_mention(
        clinic=clinic,
        message=message,
        mention_type=MentionType.USER,
        mentioned_user=actor_staff.user,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    chat = dashboard.chat

    assert chat.unread_messages == 1
    assert chat.unread_conversations == 1
    assert chat.mentions == 1
    assert chat.priority_messages == 1
    assert chat.recent_messages == 1

    assert any(
        alert.key == "priority_chat_messages"
        and alert.severity == "critical"
        and alert.count == 1
        for alert in dashboard.alerts
    )


# ============================================================================
# AI ALERTS
# ============================================================================


def test_clinical_dashboard_creates_ai_alerts(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    now = datetime.now(
        timezone.utc,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        created_at=now,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    assert {
        alert.key: (
            alert.severity,
            alert.count,
        )
        for alert in dashboard.alerts
    } == {
        "critical_ai_results": (
            "critical",
            1,
        ),
        "pending_ai_reviews": (
            "warning",
            1,
        ),
    }


def test_clinical_dashboard_does_not_create_empty_alerts(
    clinic,
    make_staff,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    assert dashboard.alerts == []


# ============================================================================
# CONTEXT / METRICS / ACTIVITY
# ============================================================================


def test_clinical_dashboard_builds_expected_context(
    clinic,
    make_staff,
):
    actor_staff = make_staff(
        clinic,
        role=Role.NURSE,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    assert dashboard.context.role is Role.NURSE
    assert dashboard.context.scope == "clinic"
    assert dashboard.context.clinic_id == clinic.id
    assert dashboard.context.generated_at is not None


def test_clinical_dashboard_builds_expected_metrics(
    clinic,
    make_staff,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    metrics = {
        metric.key: metric
        for metric in dashboard.metrics
    }

    assert set(metrics) == {
        "appointments",
        "pending_consultations",
        "pending_labs",
        "ai_requests",
        "unread_chat",
    }

    assert metrics["appointments"].value == 0
    assert metrics["pending_consultations"].value == 0
    assert metrics["pending_labs"].value == 0
    assert metrics["ai_requests"].value == 0
    assert metrics["unread_chat"].value == 0

    assert metrics["appointments"].unit == "appointments"
    assert metrics["pending_consultations"].unit == "consultations"
    assert metrics["pending_labs"].unit == "orders"
    assert metrics["ai_requests"].unit == "requests"
    assert metrics["unread_chat"].unit == "messages"


def test_clinical_dashboard_returns_recent_activity(
    clinic,
    make_staff,
    make_audit_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    make_audit_log(
        user=actor_staff.user,
        entity_type="Patient",
        entity_id=1,
        description="Clinical dashboard test activity",
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
    )

    assert len(dashboard.recent_activity) == 1

    activity = dashboard.recent_activity[0]

    assert activity.entity_type == "Patient"
    assert activity.entity_id == 1
    assert activity.action is not None
    assert activity.occurred_at is not None


# ============================================================================
# PERIOD FILTERING
# ============================================================================


def test_clinical_dashboard_applies_selected_period_to_appointments(
    clinic,
    make_staff,
    make_patient,
    make_appointment,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
    )

    selected_date = _utcnow().date()

    make_appointment(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        status=AppointmentStatus.SCHEDULED,
        scheduled_start=_today_at(),
        scheduled_end=_today_at(13),
    )

    make_appointment(
        clinic=clinic,
        patient=patient,
        staff=actor_staff,
        status=AppointmentStatus.SCHEDULED,
        scheduled_start=_today_at() + timedelta(days=1),
        scheduled_end=_today_at(13) + timedelta(days=1),
    )

    query = DashboardQuerySchema(
        date_from=selected_date,
        date_to=selected_date,
    )

    dashboard = get_clinical_dashboard(
        actor=actor_staff.user,
        query=query,
    )

    assert dashboard.overview.appointments_today == 1
