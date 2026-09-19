from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.enums.ai_enums import (
    AIFeature,
    AIApprovalStatus,
    AIRiskLevel,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.chat_enums import (
    MentionType,
    MessagePriority,
    MessageStatus,
    ParticipantStatus,
    ReadReceiptStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError

from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardQuerySchema,
    DashboardPeriodSchema,
)
from app.modules.dashboard.services import dashboard_widget_service


# ============================================================================
# TEST HELPERS
# ============================================================================


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


# ============================================================================
# ID VALIDATION
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
        1.0,
    ],
)
def test_validate_positive_id_rejects_invalid_values(
    value,
):
    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        dashboard_widget_service._validate_positive_id(
            value,
            "Test ID",
        )


def test_validate_positive_id_accepts_positive_integer():
    assert (
        dashboard_widget_service._validate_positive_id(
            1,
            "Test ID",
        )
        is None
    )


# ============================================================================
# DASHBOARD PERIOD RESOLUTION
# ============================================================================


def test_resolve_dashboard_period_defaults_to_today():
    result = dashboard_widget_service.resolve_dashboard_period(
        None,
    )

    today = _utcnow().date()

    assert result.date_from == today
    assert result.date_to == today


def test_resolve_dashboard_period_accepts_both_dates():
    query = DashboardQuerySchema(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 15),
    )

    result = dashboard_widget_service.resolve_dashboard_period(
        query,
    )

    assert result.date_from == date(2026, 9, 1)
    assert result.date_to == date(2026, 9, 15)


def test_resolve_dashboard_period_uses_single_date_from_as_both_bounds():
    query = DashboardQuerySchema(
        date_from=date(2026, 9, 10),
    )

    result = dashboard_widget_service.resolve_dashboard_period(
        query,
    )

    assert result.date_from == date(2026, 9, 10)
    assert result.date_to == date(2026, 9, 10)


def test_resolve_dashboard_period_uses_single_date_to_as_both_bounds():
    query = DashboardQuerySchema(
        date_to=date(2026, 9, 12),
    )

    result = dashboard_widget_service.resolve_dashboard_period(
        query,
    )

    assert result.date_from == date(2026, 9, 12)
    assert result.date_to == date(2026, 9, 12)


def test_resolve_dashboard_period_preserves_multi_day_range():
    query = DashboardQuerySchema(
        date_from=date(2026, 9, 5),
        date_to=date(2026, 9, 20),
    )

    result = dashboard_widget_service.resolve_dashboard_period(
        query,
    )

    assert result == DashboardPeriodSchema(
        date_from=date(2026, 9, 5),
        date_to=date(2026, 9, 20),
    )


# ============================================================================
# PERIOD BOUNDS
# ============================================================================


def test_period_bounds_returns_start_of_first_day_and_start_of_following_day():
    period = DashboardPeriodSchema(
        date_from=date(2026, 9, 10),
        date_to=date(2026, 9, 12),
    )

    start, end = dashboard_widget_service.period_bounds(
        period,
    )

    assert start == datetime(
        2026,
        9,
        10,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )

    assert end == datetime(
        2026,
        9,
        13,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )


def test_period_bounds_is_half_open():
    period = DashboardPeriodSchema(
        date_from=date(2026, 9, 10),
        date_to=date(2026, 9, 10),
    )

    start, end = dashboard_widget_service.period_bounds(
        period,
    )

    assert end > start
    assert end - start == timedelta(days=1)


# ============================================================================
# DASHBOARD CONTEXT
# ============================================================================


def test_build_dashboard_context():
    generated_before = _utcnow()

    result = dashboard_widget_service.build_dashboard_context(
        role=Role.DOCTOR,
        scope="clinic",
        clinic_id=10,
    )

    generated_after = _utcnow()

    assert result.role is Role.DOCTOR
    assert result.scope == "clinic"
    assert result.clinic_id == 10
    assert generated_before <= result.generated_at <= generated_after


def test_build_dashboard_context_supports_system_scope_without_clinic():
    result = dashboard_widget_service.build_dashboard_context(
        role=Role.SUPER_ADMIN,
        scope="system",
        clinic_id=None,
    )

    assert result.role is Role.SUPER_ADMIN
    assert result.scope == "system"
    assert result.clinic_id is None


# ============================================================================
# SCALAR / METRIC HELPERS
# ============================================================================


def test_count_scalar_returns_integer(
    db,
):
    from app.core.auth.user.models.user_model import User

    statement = db.select(
        db.func.count(User.id),
    ).select_from(
        User,
    )

    result = dashboard_widget_service.count_scalar(
        statement,
    )

    assert result == 0
    assert isinstance(result, int)


def test_decimal_scalar_returns_zero_decimal_for_null(
    db,
):
    statement = db.select(
        db.func.sum(
            db.literal(None),
        ),
    )

    result = dashboard_widget_service.decimal_scalar(
        statement,
    )

    assert result == Decimal("0")
    assert isinstance(result, Decimal)


def test_decimal_scalar_preserves_decimal_value(
    db,
):
    statement = db.select(
        db.literal(
            Decimal("123.45"),
        ),
    )

    result = dashboard_widget_service.decimal_scalar(
        statement,
    )

    assert result == Decimal("123.45")
    assert isinstance(result, Decimal)


def test_decimal_scalar_converts_numeric_value_to_decimal(
    db,
):
    statement = db.select(
        db.literal(25),
    )

    result = dashboard_widget_service.decimal_scalar(
        statement,
    )

    assert result == Decimal("25")
    assert isinstance(result, Decimal)


def test_build_metric():
    result = dashboard_widget_service.build_metric(
        key="appointments",
        label="Appointments",
        value=12,
        unit="appointments",
    )

    assert result.key == "appointments"
    assert result.label == "Appointments"
    assert result.value == 12
    assert result.unit == "appointments"
    assert result.trend is None


def test_build_metric_accepts_decimal_value():
    result = dashboard_widget_service.build_metric(
        key="cost",
        label="Estimated cost",
        value=Decimal("12.50"),
        unit="USD",
    )

    assert result.value == Decimal("12.50")
    assert result.unit == "USD"


# ============================================================================
# RECENT ACTIVITY
# ============================================================================


def test_build_recent_activity_returns_clinic_activity_only(
    clinic,
    make_clinic,
    make_user,
    make_audit_log,
):
    clinic_user = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    other_clinic = make_clinic()

    other_user = make_user(
        other_clinic,
        role=Role.DOCTOR,
    )

    clinic_log = make_audit_log(
        user=clinic_user,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=101,
    )

    make_audit_log(
        user=other_user,
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=202,
    )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=clinic.id,
    )

    assert len(result) == 1
    assert result[0].entity_type == "Patient"
    assert result[0].entity_id == 101
    assert result[0].action == clinic_log.action.value


def test_build_recent_activity_system_scope_includes_multiple_clinics(
    clinic,
    make_clinic,
    make_user,
    make_audit_log,
):
    clinic_user = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    other_clinic = make_clinic()

    other_user = make_user(
        other_clinic,
        role=Role.DOCTOR,
    )

    make_audit_log(
        user=clinic_user,
        entity_type="Patient",
        entity_id=101,
    )

    make_audit_log(
        user=other_user,
        entity_type="Appointment",
        entity_id=202,
    )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=None,
    )

    assert len(result) == 2
    assert {
        (item.entity_type, item.entity_id)
        for item in result
    } == {
        ("Patient", 101),
        ("Appointment", 202),
    }


def test_build_recent_activity_orders_newest_first(
    clinic,
    make_user,
    make_audit_log,
    db_session,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    now = _utcnow()

    older = make_audit_log(
        user=actor,
        entity_type="Patient",
        entity_id=1,
        created_at=now - timedelta(minutes=10),
    )

    newer = make_audit_log(
        user=actor,
        entity_type="Patient",
        entity_id=2,
        created_at=now,
    )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=clinic.id,
    )

    assert [item.entity_id for item in result] == [
        newer.entity_id,
        older.entity_id,
    ]


def test_build_recent_activity_respects_limit(
    clinic,
    make_user,
    make_audit_log,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    for entity_id in range(1, 6):
        make_audit_log(
            user=actor,
            entity_type="Patient",
            entity_id=entity_id,
        )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=clinic.id,
        limit=3,
    )

    assert len(result) == 3


def test_build_recent_activity_excludes_non_positive_entity_ids(
    clinic,
    make_user,
    make_audit_log,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    make_audit_log(
        user=actor,
        entity_type="Patient",
        entity_id=0,
    )

    make_audit_log(
        user=actor,
        entity_type="Patient",
        entity_id=-1,
    )

    make_audit_log(
        user=actor,
        entity_type="Patient",
        entity_id=10,
    )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=clinic.id,
    )

    assert len(result) == 1
    assert result[0].entity_id == 10


def test_build_recent_activity_excludes_global_audit_from_clinic_scope(
    clinic,
    make_audit_log,
):
    make_audit_log(
        user=None,
        user_id=None,
        entity_type="System",
        entity_id=1,
    )

    result = dashboard_widget_service.build_recent_activity(
        clinic_id=clinic.id,
    )

    assert result == []


# ============================================================================
# CHAT SUMMARY - VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", 0),
        ("user_id", -1),
        ("user_id", True),
        ("user_id", "1"),
        ("clinic_id", 0),
        ("clinic_id", -1),
        ("clinic_id", True),
        ("clinic_id", "1"),
    ],
)
def test_build_chat_summary_rejects_invalid_ids(
    field,
    value,
):
    kwargs = {
        "user_id": 1,
        "clinic_id": 1,
        "period": DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    }

    kwargs[field] = value

    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        dashboard_widget_service.build_chat_summary(
            **kwargs,
        )


# ============================================================================
# CHAT SUMMARY - EMPTY / PARTICIPATION
# ============================================================================


def test_build_chat_summary_returns_zeroes_when_user_has_no_conversations(
    clinic,
    make_user,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=period,
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.mentions == 0
    assert result.priority_messages == 0
    assert result.recent_messages == 0


def test_build_chat_summary_ignores_pending_participant(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=actor,
        status=ParticipantStatus.PENDING,
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
        created_at=_date_at(date.today()),
    )

    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=period,
    )

    assert result.recent_messages == 0
    assert result.priority_messages == 0


# ============================================================================
# CHAT SUMMARY - COUNTS
# ============================================================================


def test_build_chat_summary_counts_unread_messages_and_conversations(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
    )

    conversation_one = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    conversation_two = make_conversation(
        clinic=clinic,
        created_by=actor,
    )

    for conversation in (
        conversation_one,
        conversation_two,
    ):
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

    message_one = make_message(
        clinic=clinic,
        conversation=conversation_one,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(date.today(), 10),
    )

    message_two = make_message(
        clinic=clinic,
        conversation=conversation_one,
        sender=sender,
        status=MessageStatus.EDITED,
        created_at=_date_at(date.today(), 11),
    )

    message_three = make_message(
        clinic=clinic,
        conversation=conversation_two,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(date.today(), 12),
    )

    for message in (
        message_one,
        message_two,
        message_three,
    ):
        make_message_read_receipt(
            clinic=clinic,
            message=message,
            user=actor,
            status=ReadReceiptStatus.DELIVERED,
        )

    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=period,
    )

    assert result.unread_messages == 3
    assert result.unread_conversations == 2
    assert result.recent_messages == 3


def test_build_chat_summary_read_receipt_is_not_unread(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
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

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(date.today()),
    )

    make_message_read_receipt(
        clinic=clinic,
        message=message,
        user=actor,
        status=ReadReceiptStatus.READ,
    )

    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=period,
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.recent_messages == 1


def test_build_chat_summary_ignores_own_messages_for_unread_and_priority(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    actor = make_user(
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

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=actor,
        status=MessageStatus.SENT,
        priority=MessagePriority.STAT,
        created_at=_date_at(date.today()),
    )

    make_message_read_receipt(
        clinic=clinic,
        message=message,
        user=actor,
        status=ReadReceiptStatus.DELIVERED,
    )

    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=period,
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.priority_messages == 0
    assert result.recent_messages == 1


def test_build_chat_summary_counts_mentions_for_user(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_mention,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
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

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(date.today()),
    )

    make_message_mention(
        clinic=clinic,
        message=message,
        mention_type=MentionType.USER,
        mentioned_user=actor,
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.mentions == 1


def test_build_chat_summary_counts_urgent_and_stat_messages(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
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
        created_at=_date_at(date.today(), 10),
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.STAT,
        created_at=_date_at(date.today(), 11),
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.NORMAL,
        created_at=_date_at(date.today(), 12),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.priority_messages == 2
    assert result.recent_messages == 3


@pytest.mark.parametrize(
    "message_status",
    [
        MessageStatus.PENDING,
        MessageStatus.FAILED,
        MessageStatus.DELETED,
    ],
)
def test_build_chat_summary_excludes_non_visible_message_statuses(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    message_status,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
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
        status=message_status,
        priority=MessagePriority.STAT,
        created_at=_date_at(date.today()),
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.priority_messages == 0
    assert result.recent_messages == 0


def test_build_chat_summary_enforces_clinic_isolation(
    clinic,
    make_clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
    )

    other_clinic = make_clinic()

    other_actor = make_user(
        other_clinic,
        role=Role.DOCTOR,
    )

    other_sender = make_user(
        other_clinic,
        role=Role.NURSE,
    )

    conversation = make_conversation(
        clinic=other_clinic,
        created_by=other_actor,
    )

    make_conversation_participant(
        clinic=other_clinic,
        conversation=conversation,
        user=other_actor,
        status=ParticipantStatus.ACCEPTED,
    )

    make_conversation_participant(
        clinic=other_clinic,
        conversation=conversation,
        user=other_sender,
        status=ParticipantStatus.ACCEPTED,
    )

    message = make_message(
        clinic=other_clinic,
        conversation=conversation,
        sender=other_sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.STAT,
        created_at=_date_at(date.today()),
    )

    make_message_read_receipt(
        clinic=other_clinic,
        message=message,
        user=other_actor,
        status=ReadReceiptStatus.DELIVERED,
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.priority_messages == 0
    assert result.recent_messages == 0


def test_build_chat_summary_excludes_messages_outside_period(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
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

    yesterday = date.today() - timedelta(days=1)

    today_message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(date.today()),
    )

    yesterday_message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        created_at=_date_at(yesterday),
    )

    make_message_read_receipt(
        clinic=clinic,
        message=today_message,
        user=actor,
        status=ReadReceiptStatus.DELIVERED,
    )

    make_message_read_receipt(
        clinic=clinic,
        message=yesterday_message,
        user=actor,
        status=ReadReceiptStatus.DELIVERED,
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.unread_messages == 1
    assert result.unread_conversations == 1
    assert result.recent_messages == 1


def test_build_chat_summary_ignores_archived_conversation(
    clinic,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    make_message_read_receipt,
):
    from app.core.enums.chat_enums import ConversationStatus

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    sender = make_user(
        clinic,
        role=Role.NURSE,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=actor,
        status=ConversationStatus.ARCHIVED,
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

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=sender,
        status=MessageStatus.SENT,
        priority=MessagePriority.STAT,
        created_at=_date_at(date.today()),
    )

    make_message_read_receipt(
        clinic=clinic,
        message=message,
        user=actor,
        status=ReadReceiptStatus.DELIVERED,
    )

    result = dashboard_widget_service.build_chat_summary(
        user_id=actor.id,
        clinic_id=clinic.id,
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result.unread_messages == 0
    assert result.unread_conversations == 0
    assert result.priority_messages == 0
    assert result.recent_messages == 0


# ============================================================================
# AI AGGREGATES - EMPTY
# ============================================================================


def test_build_ai_aggregates_returns_zeroes_when_empty(
    app,
):
    period = DashboardPeriodSchema(
        date_from=date.today(),
        date_to=date.today(),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=period,
    )

    assert result["total_ai_requests"] == 0
    assert result["total_credits_used"] == 0
    assert result["total_input_tokens"] == 0
    assert result["total_output_tokens"] == 0
    assert result["total_tokens"] == 0
    assert result["estimated_cost"] == Decimal("0")
    assert result["pending_reviews"] == 0
    assert result["approved_reviews"] == 0
    assert result["rejected_reviews"] == 0
    assert result["low_risk_results"] == 0
    assert result["medium_risk_results"] == 0
    assert result["high_risk_results"] == 0
    assert result["critical_risk_results"] == 0
    assert result["feature_usage"] == []
    assert result["risk_summary"] == []
    assert result["approval_summary"] == []


# ============================================================================
# AI AGGREGATES - VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "clinic_id",
    [
        0,
        -1,
        True,
        "1",
    ],
)
def test_build_ai_aggregates_rejects_invalid_clinic_id(
    clinic_id,
):
    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        dashboard_widget_service.build_ai_aggregates(
            period=DashboardPeriodSchema(
                date_from=date.today(),
                date_to=date.today(),
            ),
            clinic_id=clinic_id,
        )


@pytest.mark.parametrize(
    "user_id",
    [
        0,
        -1,
        True,
        "1",
    ],
)
def test_build_ai_aggregates_rejects_invalid_user_id(
    user_id,
):
    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        dashboard_widget_service.build_ai_aggregates(
            period=DashboardPeriodSchema(
                date_from=date.today(),
                date_to=date.today(),
            ),
            user_id=user_id,
        )


# ============================================================================
# AI AGGREGATES - FULL SUMMARY
# ============================================================================


def test_build_ai_aggregates_builds_complete_summary(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    now = _utcnow()

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.DRUG_INTERACTION_CHECK,
        risk_level=AIRiskLevel.LOW,
        approval_status=AIApprovalStatus.APPROVED,
        credits_used=2,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost=Decimal("0.020000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.TRIAGE_ASSISTANT,
        risk_level=AIRiskLevel.MEDIUM,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=3,
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        estimated_cost=Decimal("0.030000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.LAB_RESULT_INTERPRETER,
        risk_level=AIRiskLevel.HIGH,
        approval_status=AIApprovalStatus.REJECTED,
        credits_used=4,
        input_tokens=300,
        output_tokens=150,
        total_tokens=450,
        estimated_cost=Decimal("0.040000"),
        created_at=now,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        feature_used=AIFeature.DRUG_INTERACTION_CHECK,
        risk_level=AIRiskLevel.CRITICAL,
        approval_status=AIApprovalStatus.PENDING,
        credits_used=5,
        input_tokens=400,
        output_tokens=200,
        total_tokens=600,
        estimated_cost=Decimal("0.050000"),
        created_at=now,
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert result["total_ai_requests"] == 4
    assert result["total_credits_used"] == 14
    assert result["total_input_tokens"] == 1000
    assert result["total_output_tokens"] == 500
    assert result["total_tokens"] == 1500
    assert result["estimated_cost"] == Decimal("0.140000")

    assert result["pending_reviews"] == 2
    assert result["approved_reviews"] == 1
    assert result["rejected_reviews"] == 1

    assert result["low_risk_results"] == 1
    assert result["medium_risk_results"] == 1
    assert result["high_risk_results"] == 1
    assert result["critical_risk_results"] == 1

    assert {
        item["feature"]: item
        for item in result["feature_usage"]
    } == {
        AIFeature.DRUG_INTERACTION_CHECK: {
            "feature": AIFeature.DRUG_INTERACTION_CHECK,
            "request_count": 2,
            "credits_used": 7,
            "estimated_cost": Decimal("0.070000"),
        },
        AIFeature.TRIAGE_ASSISTANT: {
            "feature": AIFeature.TRIAGE_ASSISTANT,
            "request_count": 1,
            "credits_used": 3,
            "estimated_cost": Decimal("0.030000"),
        },
        AIFeature.LAB_RESULT_INTERPRETER: {
            "feature": AIFeature.LAB_RESULT_INTERPRETER,
            "request_count": 1,
            "credits_used": 4,
            "estimated_cost": Decimal("0.040000"),
        },
    }

    assert {
        item["risk_level"]: item["count"]
        for item in result["risk_summary"]
    } == {
        AIRiskLevel.LOW: 1,
        AIRiskLevel.MEDIUM: 1,
        AIRiskLevel.HIGH: 1,
        AIRiskLevel.CRITICAL: 1,
    }

    assert {
        item["approval_status"]: item["count"]
        for item in result["approval_summary"]
    } == {
        AIApprovalStatus.PENDING: 2,
        AIApprovalStatus.APPROVED: 1,
        AIApprovalStatus.REJECTED: 1,
    }


# ============================================================================
# AI AGGREGATES - CLINIC / USER ISOLATION
# ============================================================================


def test_build_ai_aggregates_filters_by_clinic(
    clinic,
    make_clinic,
    make_staff,
    make_ai_log,
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

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=2,
        created_at=_utcnow(),
    )

    make_ai_log(
        clinic=other_clinic,
        user=other_staff.user,
        credits_used=10,
        created_at=_utcnow(),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
    )

    assert result["total_ai_requests"] == 1
    assert result["total_credits_used"] == 2


def test_build_ai_aggregates_filters_by_user(
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
        role=Role.NURSE,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=2,
        created_at=_utcnow(),
    )

    make_ai_log(
        clinic=clinic,
        user=other_staff.user,
        credits_used=10,
        created_at=_utcnow(),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert result["total_ai_requests"] == 1
    assert result["total_credits_used"] == 2


def test_build_ai_aggregates_without_scope_filters_includes_multiple_clinics(
    clinic,
    make_clinic,
    make_staff,
    make_ai_log,
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

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=2,
        created_at=_utcnow(),
    )

    make_ai_log(
        clinic=other_clinic,
        user=other_staff.user,
        credits_used=10,
        created_at=_utcnow(),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
    )

    assert result["total_ai_requests"] == 2
    assert result["total_credits_used"] == 12


# ============================================================================
# AI AGGREGATES - PERIOD FILTERING
# ============================================================================


def test_build_ai_aggregates_excludes_logs_outside_period(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    today = date.today()
    yesterday = today - timedelta(days=1)

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=2,
        created_at=_date_at(today, 12),
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=10,
        created_at=_date_at(yesterday, 12),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=today,
            date_to=today,
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert result["total_ai_requests"] == 1
    assert result["total_credits_used"] == 2


def test_build_ai_aggregates_excludes_end_boundary(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    selected_date = date.today()
    next_date = selected_date + timedelta(days=1)

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=2,
        created_at=_date_at(selected_date, 23),
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=10,
        created_at=_date_at(next_date, 0),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=selected_date,
            date_to=selected_date,
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert result["total_ai_requests"] == 1
    assert result["total_credits_used"] == 2


# ============================================================================
# AI AGGREGATES - NULL VALUES
# ============================================================================


def test_build_ai_aggregates_handles_null_token_and_cost_values(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    make_ai_log(
        clinic=clinic,
        user=actor_staff.user,
        credits_used=3,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost=None,
        created_at=_utcnow(),
    )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert result["total_ai_requests"] == 1
    assert result["total_credits_used"] == 3
    assert result["total_input_tokens"] == 0
    assert result["total_output_tokens"] == 0
    assert result["total_tokens"] == 0
    assert result["estimated_cost"] == Decimal("0")


# ============================================================================
# AI AGGREGATES - DETERMINISTIC GROUP ORDER
# ============================================================================


def test_build_ai_aggregates_sorts_feature_usage_deterministically(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    for feature in (
        AIFeature.LAB_RESULT_INTERPRETER,
        AIFeature.DRUG_INTERACTION_CHECK,
        AIFeature.TRIAGE_ASSISTANT,
    ):
        make_ai_log(
            clinic=clinic,
            user=actor_staff.user,
            feature_used=feature,
            created_at=_utcnow(),
        )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert [
        item["feature"]
        for item in result["feature_usage"]
    ] == sorted(
        [
            AIFeature.LAB_RESULT_INTERPRETER,
            AIFeature.DRUG_INTERACTION_CHECK,
            AIFeature.TRIAGE_ASSISTANT,
        ],
        key=lambda item: item.value,
    )


def test_build_ai_aggregates_sorts_risk_summary_deterministically(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    for risk_level in (
        AIRiskLevel.CRITICAL,
        AIRiskLevel.LOW,
        AIRiskLevel.HIGH,
        AIRiskLevel.MEDIUM,
    ):
        make_ai_log(
            clinic=clinic,
            user=actor_staff.user,
            risk_level=risk_level,
            created_at=_utcnow(),
        )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert [
        item["risk_level"]
        for item in result["risk_summary"]
    ] == sorted(
        [
            AIRiskLevel.CRITICAL,
            AIRiskLevel.LOW,
            AIRiskLevel.HIGH,
            AIRiskLevel.MEDIUM,
        ],
        key=lambda item: item.value,
    )


def test_build_ai_aggregates_sorts_approval_summary_deterministically(
    clinic,
    make_staff,
    make_ai_log,
):
    actor_staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    for approval_status in (
        AIApprovalStatus.REJECTED,
        AIApprovalStatus.APPROVED,
        AIApprovalStatus.PENDING,
    ):
        make_ai_log(
            clinic=clinic,
            user=actor_staff.user,
            approval_status=approval_status,
            created_at=_utcnow(),
        )

    result = dashboard_widget_service.build_ai_aggregates(
        period=DashboardPeriodSchema(
            date_from=date.today(),
            date_to=date.today(),
        ),
        clinic_id=clinic.id,
        user_id=actor_staff.user.id,
    )

    assert [
        item["approval_status"]
        for item in result["approval_summary"]
    ] == sorted(
        [
            AIApprovalStatus.REJECTED,
            AIApprovalStatus.APPROVED,
            AIApprovalStatus.PENDING,
        ],
        key=lambda item: item.value,
    )