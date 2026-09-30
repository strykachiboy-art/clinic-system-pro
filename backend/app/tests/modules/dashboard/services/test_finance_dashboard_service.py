from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count

import pytest

from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.core.enums.chat_enums import (
    MessagePriority,
    MessageStatus,
    ParticipantStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError

from app.modules.billing.models.billing_model import (
    Invoice,
    Payment,
)

from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardQuerySchema,
)
from app.modules.dashboard.services.finance_dashboard_service import (
    get_finance_dashboard,
)


# ============================================================================
# TEST HELPERS
# ============================================================================


_invoice_counter = count(1)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _date_at(
    target_date: date,
    hour: int = 12,
) -> datetime:
    return datetime.combine(
        target_date,
        time.min,
        tzinfo=timezone.utc,
    ) + timedelta(hours=hour)


def _make_invoice(
    db_session,
    *,
    clinic,
    patient,
    total_amount=Decimal("100.00"),
    amount_paid=Decimal("0.00"),
    status=InvoiceStatus.ISSUED,
    created_at=None,
):
    invoice = Invoice(
        clinic_id=clinic.id,
        patient_id=patient.id,
        invoice_number=(
            f"FIN-INV-{next(_invoice_counter):06d}"
        ),
        total_amount=total_amount,
        amount_paid=amount_paid,
        status=status,
        created_at=(
            created_at
            if created_at is not None
            else _utcnow()
        ),
    )

    db_session.add(invoice)
    db_session.flush()

    return invoice


def _make_payment(
    db_session,
    *,
    invoice,
    amount=Decimal("25.00"),
    status=PaymentStatus.SUCCESSFUL,
    created_at=None,
):
    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        method=PaymentMethod.CASH,
        status=status,
        created_at=(
            created_at
            if created_at is not None
            else _utcnow()
        ),
    )

    db_session.add(payment)
    db_session.flush()

    return payment


# ============================================================================
# ACCESS CONTROL
# ============================================================================


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
        Role.PARAMEDIC,
        Role.EMT,
        Role.DRIVER,
        Role.AMBULANCE_DISPATCHER,
        Role.AMBULANCE_COORDINATOR,
        Role.OTHER,
    ],
)
def test_get_finance_dashboard_rejects_non_accountant_roles(
    clinic,
    make_user,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    with pytest.raises(
        ValidationError,
        match="Finance dashboard is not available",
    ):
        get_finance_dashboard(
            actor=actor,
        )


def test_get_finance_dashboard_allows_accountant(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.context.role is Role.ACCOUNTANT
    assert result.context.scope == "clinic"
    assert result.context.clinic_id == clinic.id


def test_get_finance_dashboard_rejects_inactive_accountant(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="User account is inactive",
    ):
        get_finance_dashboard(
            actor=actor,
        )


def test_get_finance_dashboard_rejects_accountant_without_clinic(
    make_user,
):
    actor = make_user(
        clinic=None,
        role=Role.ACCOUNTANT,
    )

    with pytest.raises(
        ValidationError,
        match="valid clinic",
    ):
        get_finance_dashboard(
            actor=actor,
        )


def test_get_finance_dashboard_rejects_accountant_with_invalid_clinic_id(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    actor.clinic_id = 0

    with pytest.raises(
        ValidationError,
        match="valid clinic",
    ):
        get_finance_dashboard(
            actor=actor,
        )


# ============================================================================
# EMPTY DASHBOARD
# ============================================================================


def test_get_finance_dashboard_returns_zeroed_dashboard_when_empty(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.outstanding_invoice_count == 0
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("0")
    )
    assert result.overview.overdue_invoice_count == 0
    assert (
        result.overview.overdue_invoice_amount
        == Decimal("0")
    )
    assert result.overview.successful_payments_today == 0
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("0")
    )
    assert result.overview.pending_payment_count == 0

    assert result.ai.total_ai_requests == 0
    assert result.ai.total_credits_used == 0
    assert result.ai.estimated_cost == Decimal("0")

    assert result.chat.unread_messages == 0
    assert result.chat.unread_conversations == 0
    assert result.chat.mentions == 0
    assert result.chat.priority_messages == 0
    assert result.chat.recent_messages == 0

    assert result.alerts == []
    assert result.recent_activity == []


# ============================================================================
# OUTSTANDING INVOICES
# ============================================================================


def test_get_finance_dashboard_counts_outstanding_invoices(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.ISSUED,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("200.00"),
        amount_paid=Decimal("50.00"),
        status=InvoiceStatus.PARTIALLY_PAID,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("300.00"),
        amount_paid=Decimal("100.00"),
        status=InvoiceStatus.OVERDUE,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.outstanding_invoice_count == 3
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("425.00")
    )


def test_get_finance_dashboard_excludes_fully_paid_invoice_from_outstanding(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("100.00"),
        status=InvoiceStatus.PAID,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.outstanding_invoice_count == 0
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("0")
    )


@pytest.mark.parametrize(
    "status",
    [
        InvoiceStatus.DRAFT,
        InvoiceStatus.PAID,
        InvoiceStatus.CANCELLED,
    ],
)
def test_get_finance_dashboard_excludes_non_outstanding_invoice_statuses(
    db_session,
    clinic,
    patient,
    make_user,
    status,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        status=status,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.outstanding_invoice_count == 0
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("0")
    )


# ============================================================================
# OVERDUE INVOICES
# ============================================================================


def test_get_finance_dashboard_counts_overdue_invoices(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.OVERDUE,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("300.00"),
        amount_paid=Decimal("125.00"),
        status=InvoiceStatus.OVERDUE,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.overdue_invoice_count == 2
    assert (
        result.overview.overdue_invoice_amount
        == Decimal("250.00")
    )


def test_get_finance_dashboard_uses_overdue_status_for_overdue_count(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.ISSUED,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.overdue_invoice_count == 0
    assert (
        result.overview.overdue_invoice_amount
        == Decimal("0")
    )


# ============================================================================
# SUCCESSFUL PAYMENTS
# ============================================================================


def test_get_finance_dashboard_counts_successful_payments_in_period(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(selected_date, 9),
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("75.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(selected_date, 15),
    )

    query = DashboardQuerySchema(
        date_from=selected_date,
        date_to=selected_date,
    )

    result = get_finance_dashboard(
        actor=actor,
        query=query,
    )

    assert result.overview.successful_payments_today == 2
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("125.00")
    )


@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.PENDING,
        PaymentStatus.FAILED,
        PaymentStatus.REFUNDED,
    ],
)
def test_get_finance_dashboard_excludes_non_successful_payments(
    db_session,
    clinic,
    patient,
    make_user,
    status,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=status,
        created_at=_utcnow(),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.successful_payments_today == 0
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("0")
    )


def test_get_finance_dashboard_excludes_successful_payments_outside_period(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()
    previous_date = selected_date - timedelta(days=1)

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(selected_date, 12),
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("100.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(previous_date, 12),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
    )

    assert result.overview.successful_payments_today == 1
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("50.00")
    )


def test_get_finance_dashboard_excludes_payment_at_period_end_boundary(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()
    next_date = selected_date + timedelta(days=1)

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(selected_date, 23),
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("100.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(next_date, 0),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
    )

    assert result.overview.successful_payments_today == 1
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("50.00")
    )


# ============================================================================
# PENDING PAYMENTS
# ============================================================================


def test_get_finance_dashboard_counts_pending_payments(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("25.00"),
        status=PaymentStatus.PENDING,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.PENDING,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.pending_payment_count == 2


def test_get_finance_dashboard_pending_payment_count_is_not_period_filtered(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()
    previous_date = selected_date - timedelta(days=5)

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("25.00"),
        status=PaymentStatus.PENDING,
        created_at=_date_at(previous_date, 12),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
    )

    assert result.overview.pending_payment_count == 1


# ============================================================================
# CLINIC ISOLATION
# ============================================================================


def test_get_finance_dashboard_enforces_clinic_isolation(
    db_session,
    clinic,
    make_clinic,
    patient,
    make_patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    other_clinic = make_clinic()
    other_patient = make_patient(other_clinic)

    clinic_invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.ISSUED,
    )

    other_invoice = _make_invoice(
        db_session,
        clinic=other_clinic,
        patient=other_patient,
        total_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        status=InvoiceStatus.ISSUED,
    )

    _make_payment(
        db_session,
        invoice=clinic_invoice,
        amount=Decimal("40.00"),
        status=PaymentStatus.SUCCESSFUL,
    )

    _make_payment(
        db_session,
        invoice=other_invoice,
        amount=Decimal("999.00"),
        status=PaymentStatus.SUCCESSFUL,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.outstanding_invoice_count == 1
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("75.00")
    )

    assert result.overview.successful_payments_today == 1
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("40.00")
    )


# ============================================================================
# AI COST
# ============================================================================


def test_get_finance_dashboard_builds_ai_cost_summary(
    clinic,
    make_user,
    make_ai_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=2,
        estimated_cost=Decimal("0.020000"),
        created_at=_date_at(selected_date, 10),
    )

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=3,
        estimated_cost=Decimal("0.030000"),
        created_at=_date_at(selected_date, 11),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
    )

    assert result.ai.total_ai_requests == 2
    assert result.ai.total_credits_used == 5
    assert (
        result.ai.estimated_cost
        == Decimal("0.050000")
    )


def test_get_finance_dashboard_excludes_ai_logs_outside_period(
    clinic,
    make_user,
    make_ai_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    selected_date = _utcnow().date()
    previous_date = selected_date - timedelta(days=1)

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=2,
        estimated_cost=Decimal("0.020000"),
        created_at=_date_at(selected_date, 12),
    )

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=10,
        estimated_cost=Decimal("0.100000"),
        created_at=_date_at(previous_date, 12),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
    )

    assert result.ai.total_ai_requests == 1
    assert result.ai.total_credits_used == 2
    assert (
        result.ai.estimated_cost
        == Decimal("0.020000")
    )


def test_get_finance_dashboard_excludes_ai_logs_from_other_clinic(
    clinic,
    make_clinic,
    make_user,
    make_ai_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    other_clinic = make_clinic()

    other_user = make_user(
        other_clinic,
        role=Role.ACCOUNTANT,
    )

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=2,
        estimated_cost=Decimal("0.020000"),
    )

    make_ai_log(
        clinic=other_clinic,
        user=other_user,
        credits_used=20,
        estimated_cost=Decimal("0.200000"),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.ai.total_ai_requests == 1
    assert result.ai.total_credits_used == 2
    assert (
        result.ai.estimated_cost
        == Decimal("0.020000")
    )


# ============================================================================
# CHAT SUMMARY
# ============================================================================


def test_get_finance_dashboard_includes_chat_summary(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.chat.unread_messages == 0
    assert result.chat.unread_conversations == 0
    assert result.chat.mentions == 0
    assert result.chat.priority_messages == 0
    assert result.chat.recent_messages == 0


def test_get_finance_dashboard_creates_priority_chat_alert(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    sender = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=actor,
        status=ParticipantStatus.ACCEPTED,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=sender,
        status=ParticipantStatus.ACCEPTED,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.URGENT,
        created_at=_utcnow(),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.chat.priority_messages == 1

    alert = next(
        item
        for item in result.alerts
        if item.key == "priority_chat_messages"
    )

    assert alert.severity == "critical"
    assert alert.count == 1


# ============================================================================
# ALERTS
# ============================================================================


def test_get_finance_dashboard_creates_overdue_invoice_alert(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.OVERDUE,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    alert = next(
        item
        for item in result.alerts
        if item.key == "overdue_invoices"
    )

    assert alert.severity == "warning"
    assert alert.title == "Overdue invoices"
    assert alert.count == 1


def test_get_finance_dashboard_creates_pending_payment_alert(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.PENDING,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    alert = next(
        item
        for item in result.alerts
        if item.key == "pending_payments"
    )

    assert alert.severity == "warning"
    assert alert.title == "Pending payments"
    assert alert.count == 1


def test_get_finance_dashboard_returns_multiple_alerts_when_conditions_exist(
    db_session,
    clinic,
    patient,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    sender = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status=InvoiceStatus.OVERDUE,
    )

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("25.00"),
        status=PaymentStatus.PENDING,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=actor,
        status=ParticipantStatus.ACCEPTED,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=sender,
        status=ParticipantStatus.ACCEPTED,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.STAT,
        created_at=_utcnow(),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert {
        alert.key
        for alert in result.alerts
    } == {
        "overdue_invoices",
        "pending_payments",
        "priority_chat_messages",
    }


# ============================================================================
# METRICS
# ============================================================================


def test_get_finance_dashboard_builds_expected_metrics(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    invoice_one = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("200.00"),
        amount_paid=Decimal("50.00"),
        status=InvoiceStatus.ISSUED,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("300.00"),
        amount_paid=Decimal("100.00"),
        status=InvoiceStatus.OVERDUE,
    )

    _make_payment(
        db_session,
        invoice=invoice_one,
        amount=Decimal("75.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_utcnow(),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert [
        metric.key
        for metric in result.metrics
    ] == [
        "outstanding_balance",
        "overdue_balance",
        "payments_received",
        "ai_cost",
        "unread_chat_messages",
    ]

    assert result.metrics[0].value == Decimal("350.00")
    assert result.metrics[0].unit == "currency"

    assert result.metrics[1].value == Decimal("200.00")
    assert result.metrics[1].unit == "currency"

    assert result.metrics[2].value == Decimal("75.00")
    assert result.metrics[2].unit == "currency"

    assert result.metrics[3].value == Decimal("0")
    assert result.metrics[3].unit == "currency"

    assert result.metrics[4].value == 0
    assert result.metrics[4].unit == "messages"


# ============================================================================
# RECENT ACTIVITY
# ============================================================================


def test_get_finance_dashboard_includes_recent_clinic_activity(
    clinic,
    make_user,
    make_audit_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    log = make_audit_log(
        user=actor,
        entity_type="Invoice",
        entity_id=123,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert len(result.recent_activity) == 1
    assert result.recent_activity[0].entity_type == "Invoice"
    assert result.recent_activity[0].entity_id == 123
    assert (
        result.recent_activity[0].action
        == log.action.value
    )


def test_get_finance_dashboard_excludes_other_clinic_activity(
    clinic,
    make_clinic,
    make_user,
    make_audit_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    other_clinic = make_clinic()

    other_actor = make_user(
        other_clinic,
        role=Role.ACCOUNTANT,
    )

    make_audit_log(
        user=actor,
        entity_type="Invoice",
        entity_id=100,
    )

    make_audit_log(
        user=other_actor,
        entity_type="Invoice",
        entity_id=200,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert len(result.recent_activity) == 1
    assert result.recent_activity[0].entity_id == 100


# ============================================================================
# QUERY / PERIOD RESOLUTION
# ============================================================================


def test_get_finance_dashboard_respects_custom_date_range(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    start_date = date(2026, 9, 10)
    end_date = date(2026, 9, 12)

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("25.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(start_date, 9),
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("50.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(end_date, 23),
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("100.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(
            end_date + timedelta(days=1),
            1,
        ),
    )

    result = get_finance_dashboard(
        actor=actor,
        query=DashboardQuerySchema(
            date_from=start_date,
            date_to=end_date,
        ),
    )

    assert result.overview.successful_payments_today == 2
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("75.00")
    )


def test_get_finance_dashboard_defaults_to_current_day(
    db_session,
    clinic,
    patient,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    today = _utcnow().date()

    invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
    )

    _make_payment(
        db_session,
        invoice=invoice,
        amount=Decimal("40.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_date_at(today, 12),
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.overview.successful_payments_today == 1
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("40.00")
    )


# ============================================================================
# COMPLETE INTEGRATED SUMMARY
# ============================================================================


def test_get_finance_dashboard_builds_complete_summary(
    db_session,
    clinic,
    patient,
    make_user,
    make_ai_log,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_audit_log,
):
    actor = make_user(
        clinic,
        role=Role.ACCOUNTANT,
    )

    sender = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    issued_invoice = _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("500.00"),
        amount_paid=Decimal("150.00"),
        status=InvoiceStatus.ISSUED,
    )

    _make_invoice(
        db_session,
        clinic=clinic,
        patient=patient,
        total_amount=Decimal("300.00"),
        amount_paid=Decimal("100.00"),
        status=InvoiceStatus.OVERDUE,
    )

    _make_payment(
        db_session,
        invoice=issued_invoice,
        amount=Decimal("75.00"),
        status=PaymentStatus.SUCCESSFUL,
        created_at=_utcnow(),
    )

    _make_payment(
        db_session,
        invoice=issued_invoice,
        amount=Decimal("25.00"),
        status=PaymentStatus.PENDING,
        created_at=_utcnow(),
    )

    make_ai_log(
        clinic=clinic,
        user=actor,
        credits_used=4,
        estimated_cost=Decimal("0.040000"),
        created_at=_utcnow(),
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=actor,
        status=ParticipantStatus.ACCEPTED,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=sender,
        status=ParticipantStatus.ACCEPTED,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.URGENT,
        created_at=_utcnow(),
    )

    make_audit_log(
        user=actor,
        entity_type="Invoice",
        entity_id=999,
    )

    result = get_finance_dashboard(
        actor=actor,
    )

    assert result.context.role is Role.ACCOUNTANT
    assert result.context.scope == "clinic"
    assert result.context.clinic_id == clinic.id

    assert result.overview.outstanding_invoice_count == 2
    assert (
        result.overview.outstanding_invoice_amount
        == Decimal("550.00")
    )

    assert result.overview.overdue_invoice_count == 1
    assert (
        result.overview.overdue_invoice_amount
        == Decimal("200.00")
    )

    assert result.overview.successful_payments_today == 1
    assert (
        result.overview.successful_payments_today_amount
        == Decimal("75.00")
    )

    assert result.overview.pending_payment_count == 1

    assert result.ai.total_ai_requests == 1
    assert result.ai.total_credits_used == 4
    assert (
        result.ai.estimated_cost
        == Decimal("0.040000")
    )

    assert result.chat.priority_messages == 1

    assert [
        metric.key
        for metric in result.metrics
    ] == [
        "outstanding_balance",
        "overdue_balance",
        "payments_received",
        "ai_cost",
        "unread_chat_messages",
    ]

    assert {
        alert.key
        for alert in result.alerts
    } == {
        "overdue_invoices",
        "pending_payments",
        "priority_chat_messages",
    }

    assert len(result.recent_activity) == 1
    assert result.recent_activity[0].entity_type == "Invoice"
