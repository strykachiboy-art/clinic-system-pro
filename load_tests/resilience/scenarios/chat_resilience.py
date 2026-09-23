from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationType,
)
from app.modules.chat.models.chat_outbox_model import (
    ChatOutbox,
)
from app.modules.chat.models.message_model import (
    Message,
)
from app.modules.chat.services.conversation_service import (
    create_conversation,
)
from app.modules.chat.services.message_service import (
    create_message,
)
from app.modules.chat.workers.chat_outbox_worker import (
    claim_pending_events,
    mark_event_failed,
    requeue_stale_processing_events,
    retry_failed_event,
)

from load_tests.resilience.common.assertions import (
    assert_http_status,
    assert_success_response,
)
from load_tests.resilience.common.network import (
    NetworkFault,
    inject_network_conditions,
)
from load_tests.resilience.profiles.high_latency import (
    PROFILE as HIGH_LATENCY_PROFILE,
)
from load_tests.resilience.profiles.intermittent import (
    PROFILE as INTERMITTENT_PROFILE,
)
from load_tests.resilience.profiles.packet_loss import (
    PROFILE as PACKET_LOSS_PROFILE,
)
from load_tests.resilience.profiles.slow_2g import (
    PROFILE as SLOW_2G_PROFILE,
)


CHAT_BASE = "/api/v1/chat"


def _auth_headers(
    auth_headers_for,
    user,
) -> dict[str, str]:
    headers = auth_headers_for(
        user,
    ).copy()

    headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Load-Test-ID": "resilience-chat",
        }
    )

    return headers


def _make_conversation(
    clinic,
    user,
    make_user,
):
    other_user = make_user(
        clinic=clinic,
    )

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[
            other_user.id,
        ],
    )

    return conversation, other_user


def _create_message(
    clinic,
    user,
    conversation,
):
    return create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Resilience clinical chat message",
    )


def _assert_same_utc_datetime(
    actual: datetime,
    expected: datetime,
) -> None:
    if actual.tzinfo is None:
        actual = actual.replace(
            tzinfo=timezone.utc,
        )
    else:
        actual = actual.astimezone(
            timezone.utc,
        )

    if expected.tzinfo is None:
        expected = expected.replace(
            tzinfo=timezone.utc,
        )
    else:
        expected = expected.astimezone(
            timezone.utc,
        )

    assert actual == expected


def test_chat_message_recovers_after_packet_loss(
    client,
    clinic,
    user,
    make_user,
    auth_headers_for,
    monkeypatch,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_drop",
        lambda profile, rng: True,
    )

    try:
        inject_network_conditions(
            PACKET_LOSS_PROFILE,
            seed=123,
        )
    except NetworkFault:
        pass
    else:
        raise AssertionError(
            "Expected NetworkFault"
        )

    response = client.post(
        f"{CHAT_BASE}/conversations/"
        f"{conversation.id}/messages",
        json={
            "message_type": "text",
            "content": "Recovered after packet loss",
            "priority": "normal",
        },
        headers=_auth_headers(
            auth_headers_for,
            user,
        ),
    )

    assert_http_status(
        response,
        201,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["conversation_id"] == (
        conversation.id
    )
    assert body["data"]["sender_id"] == user.id
    assert body["data"]["content"] == (
        "Recovered after packet loss"
    )

    messages = db.session.execute(
        db.select(Message).where(
            Message.clinic_id == clinic.id,
            Message.conversation_id == conversation.id,
        )
    ).scalars().all()

    assert len(messages) == 1

    outbox_events = db.session.execute(
        db.select(ChatOutbox).where(
            ChatOutbox.clinic_id == clinic.id,
            ChatOutbox.message_id == messages[0].id,
        )
    ).scalars().all()

    assert len(outbox_events) == 1


def test_chat_message_recovers_after_interruption(
    client,
    clinic,
    user,
    make_user,
    auth_headers_for,
    monkeypatch,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.should_interrupt",
        lambda profile, rng: True,
    )

    try:
        inject_network_conditions(
            INTERMITTENT_PROFILE,
            seed=123,
        )
    except NetworkFault:
        pass
    else:
        raise AssertionError(
            "Expected NetworkFault"
        )

    response = client.post(
        f"{CHAT_BASE}/conversations/"
        f"{conversation.id}/messages",
        json={
            "message_type": "text",
            "content": "Recovered after interruption",
            "priority": "normal",
        },
        headers=_auth_headers(
            auth_headers_for,
            user,
        ),
    )

    assert_http_status(
        response,
        201,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["data"]["conversation_id"] == (
        conversation.id
    )
    assert body["data"]["content"] == (
        "Recovered after interruption"
    )


def test_chat_message_succeeds_under_slow_2g(
    client,
    clinic,
    user,
    make_user,
    auth_headers_for,
    monkeypatch,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        SLOW_2G_PROFILE,
        payload_bytes=2048,
        seed=123,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/"
        f"{conversation.id}/messages",
        json={
            "message_type": "text",
            "content": "Slow 2G message",
            "priority": "normal",
        },
        headers=_auth_headers(
            auth_headers_for,
            user,
        ),
    )

    assert_http_status(
        response,
        201,
    )

    assert_success_response(
        response,
    )

    assert delays == [
        0.7 + (2048 * 8 / (50 * 1000))
    ]


def test_chat_message_read_recovers_under_high_latency(
    client,
    clinic,
    user,
    make_user,
    auth_headers_for,
    monkeypatch,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    _create_message(
        clinic,
        user,
        conversation,
    )

    delays: list[float] = []

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        delays.append,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/"
        f"{conversation.id}/messages",
        headers=_auth_headers(
            auth_headers_for,
            user,
        ),
    )

    assert_http_status(
        response,
        200,
    )

    assert_success_response(
        response,
    )

    body = response.get_json()

    assert body["total"] == 1
    assert body["data"][0]["conversation_id"] == (
        conversation.id
    )

    assert delays == [1.2]


def test_outbox_message_enters_pending_state_after_creation(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    message = _create_message(
        clinic,
        user,
        conversation,
    )

    event = db.session.execute(
        db.select(ChatOutbox).where(
            ChatOutbox.message_id == message.id,
            ChatOutbox.clinic_id == clinic.id,
        )
    ).scalar_one()

    assert event.status == "pending"
    assert event.attempts == 0
    assert event.message_id == message.id


def test_outbox_failed_event_returns_to_pending(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    message = _create_message(
        clinic,
        user,
        conversation,
    )

    now = datetime(
        2030,
        1,
        1,
        tzinfo=timezone.utc,
    )

    claimed = claim_pending_events(
        limit=10,
        now=now,
    )

    event = next(
        event
        for event in claimed
        if event.message_id == message.id
    )

    failed = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Synthetic resilience failure",
        max_attempts=5,
        failed_at=now,
    )

    assert failed.status == "pending"
    assert failed.attempts == 1
    assert failed.last_error == (
        "Synthetic resilience failure"
    )

    _assert_same_utc_datetime(
        failed.available_at,
        now + timedelta(seconds=1),
    )


def test_failed_outbox_event_can_be_retried(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    message = _create_message(
        clinic,
        user,
        conversation,
    )

    now = datetime(
        2030,
        1,
        1,
        tzinfo=timezone.utc,
    )

    claimed = claim_pending_events(
        limit=10,
        now=now,
    )

    event = next(
        event
        for event in claimed
        if event.message_id == message.id
    )

    failed = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Retryable resilience failure",
        max_attempts=1,
        failed_at=now,
    )

    assert failed.status == "failed"

    retried = retry_failed_event(
        event_id=event.id,
        clinic_id=clinic.id,
        available_at=now + timedelta(
            seconds=5
        ),
    )

    assert retried.status == "pending"

    _assert_same_utc_datetime(
        retried.available_at,
        now + timedelta(seconds=5),
    )

    assert retried.last_error is None


def test_stale_processing_event_is_requeued(
    clinic,
    user,
    make_user,
    no_audit,
):
    conversation, _ = _make_conversation(
        clinic,
        user,
        make_user,
    )

    message = _create_message(
        clinic,
        user,
        conversation,
    )

    claim_time = datetime(
        2030,
        1,
        1,
        tzinfo=timezone.utc,
    )

    claimed = claim_pending_events(
        limit=10,
        now=claim_time,
    )

    event = next(
        event
        for event in claimed
        if event.message_id == message.id
    )

    recovery_time = (
        claim_time
        + timedelta(seconds=301)
    )

    requeued = requeue_stale_processing_events(
        stale_after_seconds=300,
        now=recovery_time,
        clinic_id=clinic.id,
        limit=10,
    )

    assert len(requeued) == 1
    assert requeued[0].id == event.id
    assert requeued[0].status == "pending"

    _assert_same_utc_datetime(
        requeued[0].available_at,
        recovery_time,
    )

    assert requeued[0].last_error == (
        "Processing lease expired"
    )


def test_cross_clinic_chat_request_remains_isolated_after_latency(
    client,
    make_clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    no_audit,
):
    clinic_a = make_clinic(
        name="Resilience Clinic A",
    )
    clinic_b = make_clinic(
        name="Resilience Clinic B",
    )

    user_a = make_user(
        clinic=clinic_a,
    )

    user_b = make_user(
        clinic=clinic_b,
    )

    conversation, _ = _make_conversation(
        clinic_b,
        user_b,
        make_user,
    )

    monkeypatch.setattr(
        "load_tests.resilience.common.network.sleep",
        lambda seconds: None,
    )

    inject_network_conditions(
        HIGH_LATENCY_PROFILE,
        seed=123,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/"
        f"{conversation.id}/messages",
        headers=_auth_headers(
            auth_headers_for,
            user_a,
        ),
    )

    assert_http_status(
        response,
        404,
    )