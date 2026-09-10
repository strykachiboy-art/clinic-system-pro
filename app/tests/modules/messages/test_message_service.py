from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.message_enums import (
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.messages.models.message_model import Message
from app.modules.messages.services import message_service as service


def create_message_users(make_user, clinic):
    sender = make_user(
        clinic,
        email=f"sender-{clinic.id}@test.com",
    )

    recipient = make_user(
        clinic,
        email=f"recipient-{clinic.id}@test.com",
    )

    return sender, recipient


def assert_same_datetime(actual, expected):
    assert actual.replace(tzinfo=None) == expected.replace(
        tzinfo=None
    )


def make_page(
    items,
    *,
    total=None,
    page=1,
    per_page=50,
):
    return type(
        "Pagination",
        (),
        {
            "items": list(items),
            "total": (
                len(items)
                if total is None
                else total
            ),
            "page": page,
            "per_page": per_page,
        },
    )()


# CREATE


def test_create_message_success(
    db_session,
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Hello",
        body="Test message",
    )

    assert message.id is not None
    assert message.clinic_id == clinic.id
    assert message.sender_id == sender.id
    assert message.recipient_id == recipient.id
    assert message.subject == "Hello"
    assert message.body == "Test message"
    assert message.message_type == MessageType.DIRECT
    assert message.priority == MessagePriority.NORMAL
    assert message.status == MessageStatus.SENT
    assert message.parent_message_id is None
    assert message.sent_at is not None


def test_create_message_normalizes_subject(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="   Hello World   ",
        body="Body",
    )

    assert message.subject == "Hello World"


def test_create_message_normalizes_body(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Subject",
        body="   Hello body   ",
    )

    assert message.body == "Hello body"


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("clinic_id", 0),
        ("sender_id", 0),
        ("recipient_id", 0),
        ("clinic_id", -1),
        ("sender_id", -1),
        ("recipient_id", -1),
        ("clinic_id", True),
        ("sender_id", True),
        ("recipient_id", True),
        ("clinic_id", "1"),
        ("sender_id", "1"),
        ("recipient_id", "1"),
    ],
)
def test_create_message_rejects_invalid_ids(
    clinic,
    make_user,
    field_name,
    value,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    kwargs = {
        "clinic_id": clinic.id,
        "sender_id": sender.id,
        "recipient_id": recipient.id,
        "subject": "Subject",
        "body": "Body",
    }

    kwargs[field_name] = value

    with pytest.raises(ValidationError):
        service.create_message(**kwargs)


def test_create_message_rejects_missing_clinic(
    make_user,
    clinic,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(NotFoundError):
        service.create_message(
            clinic_id=999999,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_missing_sender(
    clinic,
    make_user,
):
    recipient = make_user(
        clinic,
        email="recipient@test.com",
    )

    with pytest.raises(NotFoundError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=999999,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_missing_recipient(
    clinic,
    make_user,
):
    sender = make_user(
        clinic,
        email="sender@test.com",
    )

    with pytest.raises(NotFoundError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=999999,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_cross_clinic_sender(
    make_clinic,
    make_user,
):
    clinic_one = make_clinic(name="Clinic One")
    clinic_two = make_clinic(name="Clinic Two")

    sender = make_user(
        clinic_two,
        email="sender@clinic-two.test",
    )
    recipient = make_user(
        clinic_one,
        email="recipient@clinic-one.test",
    )

    with pytest.raises(NotFoundError):
        service.create_message(
            clinic_id=clinic_one.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_cross_clinic_recipient(
    make_clinic,
    make_user,
):
    clinic_one = make_clinic(name="Clinic One")
    clinic_two = make_clinic(name="Clinic Two")

    sender = make_user(
        clinic_one,
        email="sender@clinic-one.test",
    )
    recipient = make_user(
        clinic_two,
        email="recipient@clinic-two.test",
    )

    with pytest.raises(NotFoundError):
        service.create_message(
            clinic_id=clinic_one.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_inactive_sender(
    clinic,
    make_user,
):
    sender = make_user(
        clinic,
        email="inactive-sender@test.com",
        is_active=False,
    )
    recipient = make_user(
        clinic,
        email="recipient@test.com",
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_inactive_recipient(
    clinic,
    make_user,
):
    sender = make_user(
        clinic,
        email="sender@test.com",
    )
    recipient = make_user(
        clinic,
        email="inactive-recipient@test.com",
        is_active=False,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
        )


def test_create_message_rejects_self_message(
    clinic,
    make_user,
):
    sender = make_user(
        clinic,
        email="self@test.com",
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=sender.id,
            subject="Subject",
            body="Body",
        )


@pytest.mark.parametrize(
    "subject",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_create_message_rejects_invalid_subject(
    clinic,
    make_user,
    subject,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject=subject,
            body="Body",
        )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_create_message_rejects_invalid_body(
    clinic,
    make_user,
    body,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body=body,
        )


def test_create_message_rejects_subject_over_255_chars(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="x" * 256,
            body="Body",
        )


@pytest.mark.parametrize(
    "message_type",
    [
        "invalid",
        123,
        None,
    ],
)
def test_create_message_rejects_invalid_message_type(
    clinic,
    make_user,
    message_type,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
            message_type=message_type,
        )


@pytest.mark.parametrize(
    "priority",
    [
        "invalid",
        123,
        None,
    ],
)
def test_create_message_rejects_invalid_priority(
    clinic,
    make_user,
    priority,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject="Subject",
            body="Body",
            priority=priority,
        )


@pytest.mark.parametrize(
    "message_type",
    list(MessageType),
)
def test_create_message_accepts_all_message_types(
    clinic,
    make_user,
    message_type,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Subject",
        body="Body",
        message_type=message_type,
    )

    assert message.message_type == message_type


@pytest.mark.parametrize(
    "priority",
    list(MessagePriority),
)
def test_create_message_accepts_all_priorities(
    clinic,
    make_user,
    priority,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Subject",
        body="Body",
        priority=priority,
    )

    assert message.priority == priority


# REPLIES


def test_create_message_reply_success(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    original = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Original",
        body="Original body",
    )

    reply = service.create_message(
        clinic_id=clinic.id,
        sender_id=recipient.id,
        recipient_id=sender.id,
        subject="Re: Original",
        body="Reply body",
        parent_message_id=original.id,
    )

    assert reply.parent_message_id == original.id
    assert reply.parent_message.id == original.id


def test_create_message_rejects_reply_from_wrong_user(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    third_user = make_user(
        clinic,
        email="third@test.com",
    )

    original = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Original",
        body="Original body",
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=third_user.id,
            recipient_id=sender.id,
            subject="Reply",
            body="Reply body",
            parent_message_id=original.id,
        )


def test_create_message_rejects_reply_to_wrong_recipient(
    clinic,
    make_user,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    third_user = make_user(
        clinic,
        email="third@test.com",
    )

    original = service.create_message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Original",
        body="Original body",
    )

    with pytest.raises(ValidationError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=recipient.id,
            recipient_id=third_user.id,
            subject="Reply",
            body="Reply body",
            parent_message_id=original.id,
        )


def test_create_message_rejects_reply_to_deleted_parent(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    deleted_parent = make_message(
        clinic,
        sender,
        recipient,
        deleted_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ConflictError):
        service.create_message(
            clinic_id=clinic.id,
            sender_id=recipient.id,
            recipient_id=sender.id,
            subject="Reply",
            body="Reply body",
            parent_message_id=deleted_parent.id,
        )


# UPDATE


def test_update_message_subject(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        subject="Original",
    )

    updated = service.update_message(
        message_id=message.id,
        user_id=sender.id,
        clinic_id=clinic.id,
        subject="Updated",
    )

    assert updated.subject == "Updated"


def test_update_message_body(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    updated = service.update_message(
        message_id=message.id,
        user_id=sender.id,
        clinic_id=clinic.id,
        body="Updated body",
    )

    assert updated.body == "Updated body"


def test_update_message_priority(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    updated = service.update_message(
        message_id=message.id,
        user_id=sender.id,
        clinic_id=clinic.id,
        priority=MessagePriority.URGENT,
    )

    assert updated.priority == MessagePriority.URGENT


@pytest.mark.parametrize(
    "user_role",
    ["sender", "recipient"],
)
def test_update_message_allows_participants(
    clinic,
    make_user,
    make_message,
    user_role,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    user_id = (
        sender.id
        if user_role == "sender"
        else recipient.id
    )

    updated = service.update_message(
        message_id=message.id,
        user_id=user_id,
        clinic_id=clinic.id,
        subject="Updated",
    )

    assert updated.subject == "Updated"


def test_update_message_rejects_unauthorized_user(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic,
        email="outsider@test.com",
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.update_message(
            message_id=message.id,
            user_id=outsider.id,
            clinic_id=clinic.id,
            subject="Hacked",
        )


def test_update_message_rejects_cross_clinic_access(
    make_clinic,
    make_user,
    make_message,
):
    clinic_one = make_clinic(name="Clinic One")
    clinic_two = make_clinic(name="Clinic Two")

    sender, recipient = create_message_users(
        make_user,
        clinic_one,
    )

    outsider = make_user(
        clinic_two,
        email="outsider@clinic-two.test",
    )

    message = make_message(
        clinic_one,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.update_message(
            message_id=message.id,
            user_id=outsider.id,
            clinic_id=clinic_two.id,
            subject="Hacked",
        )


def test_update_message_rejects_deleted_message(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        deleted_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ConflictError):
        service.update_message(
            message_id=message.id,
            user_id=sender.id,
            clinic_id=clinic.id,
            subject="Updated",
        )


def test_update_message_rejects_non_sent_message(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        status=MessageStatus.ARCHIVED,
    )

    with pytest.raises(ConflictError):
        service.update_message(
            message_id=message.id,
            user_id=sender.id,
            clinic_id=clinic.id,
            subject="Updated",
        )


def test_update_message_rejects_unknown_field(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(ValidationError):
        service.update_message(
            message_id=message.id,
            user_id=sender.id,
            clinic_id=clinic.id,
            sender_id=999,
        )


def test_update_message_without_fields_returns_same_message(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.update_message(
        message_id=message.id,
        user_id=sender.id,
        clinic_id=clinic.id,
    )

    assert result.id == message.id
    assert result.subject == message.subject


# INBOX


def test_get_inbox_returns_recipient_messages(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    other = make_user(
        clinic,
        email="other@test.com",
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Inbox message",
    )

    make_message(
        clinic,
        sender,
        other,
        subject="Other message",
    )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
    )

    assert result.total == 1
    assert result.page == 1
    assert result.per_page == service.DEFAULT_PER_PAGE
    assert len(result.items) == 1
    assert result.items[0].recipient_id == recipient.id
    assert result.items[0].subject == "Inbox message"


def test_get_inbox_unread_only(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Unread",
        read_at=None,
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Read",
        read_at=datetime.now(timezone.utc),
    )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
        unread_only=True,
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].subject == "Unread"


def test_get_inbox_excludes_deleted_messages(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Visible",
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].subject == "Visible"


def test_get_inbox_is_tenant_isolated(
    make_clinic,
    make_user,
    make_message,
):
    clinic_one = make_clinic(name="Clinic One")
    clinic_two = make_clinic(name="Clinic Two")

    sender_one, recipient_one = create_message_users(
        make_user,
        clinic_one,
    )

    sender_two, recipient_two = create_message_users(
        make_user,
        clinic_two,
    )

    make_message(
        clinic_one,
        sender_one,
        recipient_one,
        subject="Clinic One",
    )

    make_message(
        clinic_two,
        sender_two,
        recipient_two,
        subject="Clinic Two",
    )

    result = service.get_inbox(
        user_id=recipient_one.id,
        clinic_id=clinic_one.id,
    )

    assert result.total == 1
    assert result.items[0].subject == "Clinic One"


@pytest.mark.parametrize(
    "page,per_page",
    [
        (1, 1),
        (2, 2),
        (3, 10),
        (1, service.MAX_PER_PAGE),
    ],
)
def test_get_inbox_accepts_valid_pagination(
    clinic,
    make_user,
    make_message,
    page,
    per_page,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    for index in range(4):
        make_message(
            clinic,
            sender,
            recipient,
            subject=f"Message {index}",
        )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
        page=page,
        per_page=per_page,
    )

    assert result.page == page
    assert result.per_page == per_page
    assert result.total == 4


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (True, 50),
        (1, 0),
        (1, -1),
        (1, True),
        (1, service.MAX_PER_PAGE + 1),
    ],
)
def test_get_inbox_rejects_invalid_pagination(
    clinic,
    make_user,
    page,
    per_page,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.get_inbox(
            user_id=recipient.id,
            clinic_id=clinic.id,
            page=page,
            per_page=per_page,
        )


def test_get_inbox_returns_empty_last_page(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    for index in range(3):
        make_message(
            clinic,
            sender,
            recipient,
            subject=f"Message {index}",
        )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
        page=2,
        per_page=5,
    )

    assert result.total == 3
    assert result.page == 2
    assert result.per_page == 5
    assert result.items == []


def test_get_inbox_orders_newest_first(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    now = datetime.now(timezone.utc)

    older = make_message(
        clinic,
        sender,
        recipient,
        subject="Older",
        created_at=now,
    )

    newer = make_message(
        clinic,
        sender,
        recipient,
        subject="Newer",
        created_at=now + timedelta(minutes=1),
    )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
    )

    assert [
        message.id
        for message in result.items
    ] == [
        newer.id,
        older.id,
    ]


def test_get_inbox_uses_id_as_deterministic_tiebreaker(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    timestamp = datetime.now(timezone.utc)

    first = make_message(
        clinic,
        sender,
        recipient,
        subject="First",
        created_at=timestamp,
    )

    second = make_message(
        clinic,
        sender,
        recipient,
        subject="Second",
        created_at=timestamp,
    )

    result = service.get_inbox(
        user_id=recipient.id,
        clinic_id=clinic.id,
    )

    assert [
        message.id
        for message in result.items
    ] == sorted(
        [first.id, second.id],
        reverse=True,
    )


# SENT


def test_get_sent_messages_returns_sender_messages(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    other = make_user(
        clinic,
        email="other@test.com",
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Sent",
    )

    make_message(
        clinic,
        other,
        recipient,
        subject="Other",
    )

    result = service.get_sent_messages(
        user_id=sender.id,
        clinic_id=clinic.id,
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].sender_id == sender.id
    assert result.items[0].subject == "Sent"


def test_get_sent_messages_excludes_deleted(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Visible",
    )

    make_message(
        clinic,
        sender,
        recipient,
        subject="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )

    result = service.get_sent_messages(
        user_id=sender.id,
        clinic_id=clinic.id,
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].subject == "Visible"


@pytest.mark.parametrize(
    "page,per_page",
    [
        (1, 1),
        (2, 2),
        (3, 10),
        (1, service.MAX_PER_PAGE),
    ],
)
def test_get_sent_messages_accepts_valid_pagination(
    clinic,
    make_user,
    make_message,
    page,
    per_page,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    for index in range(4):
        make_message(
            clinic,
            sender,
            recipient,
            subject=f"Message {index}",
        )

    result = service.get_sent_messages(
        user_id=sender.id,
        clinic_id=clinic.id,
        page=page,
        per_page=per_page,
    )

    assert result.page == page
    assert result.per_page == per_page
    assert result.total == 4


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (True, 50),
        (1, 0),
        (1, -1),
        (1, True),
        (1, service.MAX_PER_PAGE + 1),
    ],
)
def test_get_sent_messages_rejects_invalid_pagination(
    clinic,
    make_user,
    page,
    per_page,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    with pytest.raises(ValidationError):
        service.get_sent_messages(
            user_id=sender.id,
            clinic_id=clinic.id,
            page=page,
            per_page=per_page,
        )


def test_get_sent_messages_returns_empty_last_page(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    for index in range(3):
        make_message(
            clinic,
            sender,
            recipient,
            subject=f"Message {index}",
        )

    result = service.get_sent_messages(
        user_id=sender.id,
        clinic_id=clinic.id,
        page=2,
        per_page=5,
    )

    assert result.total == 3
    assert result.page == 2
    assert result.per_page == 5
    assert result.items == []


def test_get_sent_messages_orders_newest_first(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    now = datetime.now(timezone.utc)

    older = make_message(
        clinic,
        sender,
        recipient,
        subject="Older",
        created_at=now,
    )

    newer = make_message(
        clinic,
        sender,
        recipient,
        subject="Newer",
        created_at=now + timedelta(minutes=1),
    )

    result = service.get_sent_messages(
        user_id=sender.id,
        clinic_id=clinic.id,
    )

    assert [
        message.id
        for message in result.items
    ] == [
        newer.id,
        older.id,
    ]


# SINGLE MESSAGE


def test_get_message_for_sender(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.get_message_for_user(
        message.id,
        sender.id,
        clinic.id,
    )

    assert result.id == message.id


def test_get_message_for_recipient(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.get_message_for_user(
        message.id,
        recipient.id,
        clinic.id,
    )

    assert result.id == message.id


def test_get_message_for_user_rejects_unrelated_user(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic,
        email="outsider@test.com",
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.get_message_for_user(
            message.id,
            outsider.id,
            clinic.id,
        )


def test_get_message_for_user_rejects_deleted_message(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        deleted_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ConflictError):
        service.get_message_for_user(
            message.id,
            sender.id,
            clinic.id,
        )


# MARK READ


def test_mark_message_read_success(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.mark_message_read(
        message.id,
        recipient.id,
        clinic.id,
    )

    assert result.read_at is not None


def test_mark_message_read_only_recipient(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.mark_message_read(
            message.id,
            sender.id,
            clinic.id,
        )


def test_mark_message_read_is_idempotent(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    original_read_at = datetime.now(timezone.utc)

    message = make_message(
        clinic,
        sender,
        recipient,
        read_at=original_read_at,
    )

    result = service.mark_message_read(
        message.id,
        recipient.id,
        clinic.id,
    )

    assert_same_datetime(
        result.read_at,
        original_read_at,
    )


# ARCHIVE


def test_archive_message_success(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.archive_message(
        message.id,
        sender.id,
        clinic.id,
    )

    assert result.status == MessageStatus.ARCHIVED


@pytest.mark.parametrize(
    "user_role",
    ["sender", "recipient"],
)
def test_archive_message_allows_participants(
    clinic,
    make_user,
    make_message,
    user_role,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    user_id = (
        sender.id
        if user_role == "sender"
        else recipient.id
    )

    result = service.archive_message(
        message.id,
        user_id,
        clinic.id,
    )

    assert result.status == MessageStatus.ARCHIVED


def test_archive_message_is_idempotent(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        status=MessageStatus.ARCHIVED,
    )

    result = service.archive_message(
        message.id,
        sender.id,
        clinic.id,
    )

    assert result.status == MessageStatus.ARCHIVED


def test_archive_message_rejects_unauthorized_user(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic,
        email="outsider@test.com",
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.archive_message(
            message.id,
            outsider.id,
            clinic.id,
        )


def test_archive_message_rejects_deleted_message(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
        deleted_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ConflictError):
        service.archive_message(
            message.id,
            sender.id,
            clinic.id,
        )


# DELETE


def test_delete_message_soft_deletes_record(
    db_session,
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.delete_message(
        message.id,
        sender.id,
        clinic.id,
    )

    assert result.deleted_at is not None

    stored = db_session.get(
        Message,
        message.id,
    )

    assert stored is not None
    assert stored.deleted_at is not None


def test_delete_message_allows_recipient(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    result = service.delete_message(
        message.id,
        recipient.id,
        clinic.id,
    )

    assert result.deleted_at is not None


def test_delete_message_rejects_unauthorized_user(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic,
        email="outsider@test.com",
    )

    message = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.delete_message(
            message.id,
            outsider.id,
            clinic.id,
        )


def test_delete_message_is_idempotent(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    deleted_at = datetime.now(timezone.utc)

    message = make_message(
        clinic,
        sender,
        recipient,
        deleted_at=deleted_at,
    )

    result = service.delete_message(
        message.id,
        sender.id,
        clinic.id,
    )

    assert_same_datetime(
        result.deleted_at,
        deleted_at,
    )


# THREADS


def test_get_message_thread_returns_root(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
        subject="Root",
    )

    result = service.get_message_thread(
        root.id,
        sender.id,
        clinic.id,
    )

    assert result.total == 1
    assert result.page == 1
    assert result.per_page == service.DEFAULT_PER_PAGE
    assert [
        message.id
        for message in result.items
    ] == [
        root.id,
    ]


def test_get_message_thread_returns_full_chain(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
        subject="Root",
    )

    reply_one = make_message(
        clinic,
        recipient,
        sender,
        subject="Reply One",
        parent_message=root,
    )

    reply_two = make_message(
        clinic,
        sender,
        recipient,
        subject="Reply Two",
        parent_message=reply_one,
    )

    result = service.get_message_thread(
        reply_two.id,
        sender.id,
        clinic.id,
    )

    assert result.total == 3
    assert [
        message.id
        for message in result.items
    ] == [
        root.id,
        reply_one.id,
        reply_two.id,
    ]


def test_get_message_thread_excludes_deleted_messages(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
        subject="Root",
    )

    deleted_reply = make_message(
        clinic,
        recipient,
        sender,
        subject="Deleted",
        parent_message=root,
        deleted_at=datetime.now(timezone.utc),
    )

    visible_reply = make_message(
        clinic,
        sender,
        recipient,
        subject="Visible",
        parent_message=root,
    )

    result = service.get_message_thread(
        root.id,
        sender.id,
        clinic.id,
    )

    ids = [
        message.id
        for message in result.items
    ]

    assert root.id in ids
    assert visible_reply.id in ids
    assert deleted_reply.id not in ids


def test_get_message_thread_rejects_unauthorized_user(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    outsider = make_user(
        clinic,
        email="outsider@test.com",
    )

    root = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.get_message_thread(
            root.id,
            outsider.id,
            clinic.id,
        )


def test_get_message_thread_rejects_cross_clinic_access(
    make_clinic,
    make_user,
    make_message,
):
    clinic_one = make_clinic(name="Clinic One")
    clinic_two = make_clinic(name="Clinic Two")

    sender, recipient = create_message_users(
        make_user,
        clinic_one,
    )

    outsider = make_user(
        clinic_two,
        email="outsider@clinic-two.test",
    )

    root = make_message(
        clinic_one,
        sender,
        recipient,
    )

    with pytest.raises(NotFoundError):
        service.get_message_thread(
            root.id,
            outsider.id,
            clinic_two.id,
        )


def test_get_message_thread_supports_pagination(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
        subject="Root",
    )

    previous = root

    for index in range(1, 5):
        current_sender = (
            recipient
            if index % 2
            else sender
        )
        current_recipient = (
            sender
            if index % 2
            else recipient
        )

        previous = make_message(
            clinic,
            current_sender,
            current_recipient,
            subject=f"Reply {index}",
            parent_message=previous,
        )

    result = service.get_message_thread(
        root.id,
        sender.id,
        clinic.id,
        page=2,
        per_page=2,
    )

    assert result.total == 5
    assert result.page == 2
    assert result.per_page == 2
    assert len(result.items) == 2


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (True, 50),
        (1, 0),
        (1, -1),
        (1, True),
        (1, service.MAX_PER_PAGE + 1),
    ],
)
def test_get_message_thread_rejects_invalid_pagination(
    clinic,
    make_user,
    make_message,
    page,
    per_page,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
    )

    with pytest.raises(ValidationError):
        service.get_message_thread(
            root.id,
            sender.id,
            clinic.id,
            page=page,
            per_page=per_page,
        )


def test_get_message_thread_returns_empty_last_page(
    clinic,
    make_user,
    make_message,
):
    sender, recipient = create_message_users(
        make_user,
        clinic,
    )

    root = make_message(
        clinic,
        sender,
        recipient,
        subject="Root",
    )

    make_message(
        clinic,
        recipient,
        sender,
        subject="Reply",
        parent_message=root,
    )

    result = service.get_message_thread(
        root.id,
        sender.id,
        clinic.id,
        page=2,
        per_page=5,
    )

    assert result.total == 2
    assert result.page == 2
    assert result.per_page == 5
    assert result.items == []


# VALIDATION / HELPERS


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        None,
        "1",
        1.5,
        True,
        False,
        [],
        {},
    ],
)
def test_validate_positive_id_rejects_invalid_values(
    value,
):
    with pytest.raises(ValidationError):
        service._validate_positive_id(
            value,
            "Message ID",
        )


@pytest.mark.parametrize(
    "value",
    [
        1,
        2,
        999,
    ],
)
def test_validate_positive_id_returns_valid_value(
    value,
):
    assert (
        service._validate_positive_id(
            value,
            "Message ID",
        )
        == value
    )


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (True, 50),
        ("1", 50),
        (1, 0),
        (1, -1),
        (1, True),
        (1, "50"),
        (1, service.MAX_PER_PAGE + 1),
    ],
)
def test_validate_pagination_rejects_invalid_values(
    page,
    per_page,
):
    with pytest.raises(ValidationError):
        service._validate_pagination(
            page,
            per_page,
        )


def test_validate_pagination_returns_valid_values():
    assert service._validate_pagination(
        2,
        100,
    ) == (
        2,
        100,
    )


def test_get_message_rejects_invalid_message_id(
    clinic,
):
    with pytest.raises(ValidationError):
        service._get_message(
            0,
            clinic_id=clinic.id,
        )


def test_get_user_rejects_invalid_user_id(
    clinic,
):
    with pytest.raises(ValidationError):
        service._get_user(
            0,
            clinic_id=clinic.id,
        )