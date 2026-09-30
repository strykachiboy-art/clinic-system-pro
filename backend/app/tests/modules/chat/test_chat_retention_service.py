from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.message_model import Message
from app.modules.chat.services.chat_retention_service import (
    ChatRetentionService,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_conversation(clinic, user):
    conversation = Conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
    )
    db.session.add(conversation)
    db.session.flush()
    return conversation


def _make_message(
    clinic,
    conversation,
    user,
    *,
    created_at: datetime,
    content: str = "Test message",
):
    message = Message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content=content,
        created_at=created_at,
    )
    db.session.add(message)
    db.session.flush()
    return message


def test_get_cutoff_delegates_to_policy_service(
    monkeypatch,
):
    now = _utcnow()
    expected_cutoff = now - timedelta(days=90)

    def fake_get_retention_cutoff(
        *,
        clinic_id,
        now,
    ):
        assert clinic_id == 123
        return expected_cutoff

    monkeypatch.setattr(
        ChatRetentionService.__module__
        + ".ChatPolicyService.get_retention_cutoff",
        fake_get_retention_cutoff,
    )

    result = ChatRetentionService.get_cutoff(
        clinic_id=123,
        now=now,
    )

    assert result == expected_cutoff


def test_get_cutoff_uses_current_time_when_not_supplied(
    monkeypatch,
):
    expected_cutoff = _utcnow() - timedelta(days=30)
    captured = {}

    def fake_get_retention_cutoff(
        *,
        clinic_id,
        now,
    ):
        captured["clinic_id"] = clinic_id
        captured["now"] = now
        return expected_cutoff

    monkeypatch.setattr(
        ChatRetentionService.__module__
        + ".ChatPolicyService.get_retention_cutoff",
        fake_get_retention_cutoff,
    )

    result = ChatRetentionService.get_cutoff(
        clinic_id=10,
    )

    assert result == expected_cutoff
    assert captured["clinic_id"] == 10
    assert captured["now"].tzinfo is not None


def test_get_expired_message_ids_returns_oldest_first(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    now = _utcnow()
    cutoff = now - timedelta(days=30)

    first = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff - timedelta(days=3),
    )

    second = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff - timedelta(days=2),
    )

    _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff + timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.get_expired_message_ids(
        clinic.id,
        now=now,
    )

    assert result == [first.id, second.id]


def test_get_expired_message_ids_uses_message_id_as_tiebreaker(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    now = _utcnow()
    cutoff = now - timedelta(days=30)
    created_at = cutoff - timedelta(days=1)

    first = _make_message(
        clinic,
        conversation,
        user,
        created_at=created_at,
        content="first",
    )

    second = _make_message(
        clinic,
        conversation,
        user,
        created_at=created_at,
        content="second",
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.get_expired_message_ids(
        clinic.id,
        now=now,
    )

    assert result == [first.id, second.id]


def test_get_expired_message_ids_respects_limit(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    now = _utcnow()
    cutoff = now - timedelta(days=30)

    messages = [
        _make_message(
            clinic,
            conversation,
            user,
            created_at=cutoff - timedelta(days=index + 1),
        )
        for index in range(5)
    ]

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.get_expired_message_ids(
        clinic.id,
        now=now,
        limit=2,
    )

    assert result == [
        messages[4].id,
        messages[3].id,
    ]


def test_get_expired_message_ids_caps_large_limit(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    captured = {}

    original_execute = db.session.execute

    def execute(statement, *args, **kwargs):
        captured["statement"] = statement
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(
        db.session,
        "execute",
        execute,
    )

    ChatRetentionService.get_expired_message_ids(
        clinic.id,
        limit=999999,
    )

    assert captured["statement"] is not None


def test_get_expired_message_ids_returns_empty_for_invalid_clinic():
    assert (
        ChatRetentionService.get_expired_message_ids(
            clinic_id=0,
        )
        == []
    )

    assert (
        ChatRetentionService.get_expired_message_ids(
            clinic_id=-1,
        )
        == []
    )


@pytest.mark.parametrize(
    "limit",
    [0, -1, -100],
)
def test_get_expired_message_ids_returns_empty_for_invalid_limit(
    make_clinic,
    limit,
):
    clinic = make_clinic()

    result = ChatRetentionService.get_expired_message_ids(
        clinic.id,
        limit=limit,
    )

    assert result == []


def test_clinic_isolation(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic_one = make_clinic()
    clinic_two = make_clinic()

    user_one = make_user(clinic=clinic_one)
    user_two = make_user(clinic=clinic_two)

    conversation_one = _make_conversation(
        clinic_one,
        user_one,
    )

    conversation_two = _make_conversation(
        clinic_two,
        user_two,
    )

    cutoff = _utcnow() - timedelta(days=30)

    message_one = _make_message(
        clinic_one,
        conversation_one,
        user_one,
        created_at=cutoff - timedelta(days=1),
    )

    message_two = _make_message(
        clinic_two,
        conversation_two,
        user_two,
        created_at=cutoff - timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.get_expired_message_ids(
        clinic_one.id,
    )

    assert result == [message_one.id]
    assert message_two.id not in result


def test_non_expired_messages_are_preserved(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    message = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff + timedelta(seconds=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.get_expired_message_ids(
        clinic.id,
    )

    assert result == []
    assert db.session.get(Message, message.id) is not None


def test_delete_expired_messages_deletes_only_expired_messages(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    expired_one = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff - timedelta(days=2),
    )

    expired_two = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff - timedelta(days=1),
    )

    active = _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff + timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.delete_expired_messages(
        clinic.id,
    )

    assert result == 2

    assert db.session.get(
        Message,
        expired_one.id,
    ) is None

    assert db.session.get(
        Message,
        expired_two.id,
    ) is None

    assert db.session.get(
        Message,
        active.id,
    ) is not None


def test_delete_expired_messages_does_not_delete_other_clinic(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic_one = make_clinic()
    clinic_two = make_clinic()

    user_one = make_user(clinic=clinic_one)
    user_two = make_user(clinic=clinic_two)

    conversation_one = _make_conversation(
        clinic_one,
        user_one,
    )

    conversation_two = _make_conversation(
        clinic_two,
        user_two,
    )

    cutoff = _utcnow() - timedelta(days=30)

    message_one = _make_message(
        clinic_one,
        conversation_one,
        user_one,
        created_at=cutoff - timedelta(days=1),
    )

    message_two = _make_message(
        clinic_two,
        conversation_two,
        user_two,
        created_at=cutoff - timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.delete_expired_messages(
        clinic_one.id,
    )

    assert result == 1

    assert db.session.get(
        Message,
        message_one.id,
    ) is None

    assert db.session.get(
        Message,
        message_two.id,
    ) is not None


def test_delete_expired_messages_returns_zero_when_nothing_expired(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff + timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.delete_expired_messages(
        clinic.id,
    )

    assert result == 0


def test_delete_expired_messages_respects_batch_limit(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    messages = [
        _make_message(
            clinic,
            conversation,
            user,
            created_at=cutoff - timedelta(days=index + 1),
        )
        for index in range(5)
    ]

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    result = ChatRetentionService.delete_expired_messages(
        clinic.id,
        limit=2,
    )

    assert result == 2

    assert db.session.get(
        Message,
        messages[4].id,
    ) is None

    assert db.session.get(
        Message,
        messages[3].id,
    ) is None

    assert db.session.get(
        Message,
        messages[0].id,
    ) is not None

    assert db.session.get(
        Message,
        messages[1].id,
    ) is not None

    assert db.session.get(
        Message,
        messages[2].id,
    ) is not None


def test_delete_expired_messages_rolls_back_on_failure(
    make_clinic,
    make_user,
    monkeypatch,
):
    clinic = make_clinic()
    user = make_user(clinic=clinic)
    conversation = _make_conversation(clinic, user)

    cutoff = _utcnow() - timedelta(days=30)

    _make_message(
        clinic,
        conversation,
        user,
        created_at=cutoff - timedelta(days=1),
    )

    monkeypatch.setattr(
        ChatRetentionService,
        "get_cutoff",
        lambda clinic_id, now=None: cutoff,
    )

    original_rollback = db.session.rollback
    rollback_called = {"value": False}

    def failing_execute(*args, **kwargs):
        raise RuntimeError("database failure")

    def tracking_rollback():
        rollback_called["value"] = True
        return original_rollback()

    monkeypatch.setattr(
        db.session,
        "execute",
        failing_execute,
    )

    monkeypatch.setattr(
        db.session,
        "rollback",
        tracking_rollback,
    )

    with pytest.raises(
        RuntimeError,
        match="database failure",
    ):
        ChatRetentionService.delete_expired_messages(
            clinic.id,
        )

    assert rollback_called["value"] is True


def test_message_child_relationships_are_configured_for_retention_cascade():
    assert "delete-orphan" in Message.attachments.property.cascade
    assert "delete-orphan" in Message.mentions.property.cascade
    assert "delete-orphan" in Message.pins.property.cascade
    assert "delete-orphan" in Message.read_receipts.property.cascade
    assert "delete-orphan" in Message.revisions.property.cascade
    assert "delete-orphan" in Message.reactions.property.cascade

    assert Message.attachments.property.passive_deletes is True
    assert Message.mentions.property.passive_deletes is True
    assert Message.pins.property.passive_deletes is True
    assert Message.read_receipts.property.passive_deletes is True
    assert Message.revisions.property.passive_deletes is True
    assert Message.reactions.property.passive_deletes is True