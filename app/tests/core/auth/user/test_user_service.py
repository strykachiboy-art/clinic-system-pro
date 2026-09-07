import pytest

from app.core.audit.services import audit_service
from app.core.auth.user.services import user_service
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    ValidationError,
)
from app.core.auth.user.models.user_model import User


# ============================================================================
# GET USER
# ============================================================================


def test_get_user_returns_existing_user(
    db_session,
    user,
):
    result = user_service.get_user(user.id)

    assert result.id == user.id
    assert result.email == user.email


@pytest.mark.parametrize(
    "user_id",
    [
        0,
        -1,
        None,
        True,
        False,
        "1",
    ],
)
def test_get_user_rejects_invalid_user_id(
    db_session,
    user_id,
):
    """
    Current implementation does not explicitly validate the ID.

    This test is intentionally marked as expected-to-fail until
    get_user() receives the same positive-ID validation used by
    the hardened services.
    """
    with pytest.raises(ValidationError):
        user_service.get_user(user_id)


def test_get_user_raises_when_user_does_not_exist(
    db_session,
):
    with pytest.raises(
        ValidationError,
        match=r"User 999999 not found",
    ):
        user_service.get_user(999999)


# ============================================================================
# GET USER BY EMAIL
# ============================================================================


@pytest.mark.parametrize(
    "email",
    [
        None,
        "",
    ],
)
def test_get_user_by_email_returns_none_for_empty_email(
    db_session,
    email,
):
    assert user_service.get_user_by_email(email) is None


def test_get_user_by_email_normalizes_email(
    db_session,
    user,
):
    result = user_service.get_user_by_email(
        f"  {user.email.upper()}  "
    )

    assert result is not None
    assert result.id == user.id


def test_get_user_by_email_returns_none_when_missing(
    db_session,
):
    result = user_service.get_user_by_email(
        "missing-user@example.com"
    )

    assert result is None


# ============================================================================
# REGISTER USER
# ============================================================================


@pytest.mark.parametrize(
    "email",
    [
        None,
        "",
        "invalid-email",
        "missing-at-symbol.com",
    ],
)
def test_register_user_rejects_invalid_email(
    db_session,
    email,
):
    with pytest.raises(
        ValidationError,
        match="A valid email is required",
    ):
        user_service.register_user(
            email,
            "StrongPass123",
            Role.PATIENT,
        )


@pytest.mark.parametrize(
    "password",
    [
        None,
        "",
        "short",
        "1234567",
    ],
)
def test_register_user_rejects_weak_password(
    db_session,
    password,
):
    with pytest.raises(
        ValidationError,
        match="Password must be at least 8 characters",
    ):
        user_service.register_user(
            "new-user@example.com",
            password,
            Role.PATIENT,
        )


@pytest.mark.parametrize(
    "role",
    [
        None,
        "patient",
        "admin",
        1,
    ],
)
def test_register_user_rejects_invalid_role(
    db_session,
    role,
):
    with pytest.raises(
        ValidationError,
        match="Invalid user role",
    ):
        user_service.register_user(
            "new-user@example.com",
            "StrongPass123",
            role,
        )


def test_register_user_normalizes_email(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    user = user_service.register_user(
        "  NEW-USER@Example.COM  ",
        "StrongPass123",
        Role.PATIENT,
    )

    assert user.email == "new-user@example.com"
    assert user.role == Role.PATIENT
    assert user.id is not None


def test_register_user_rejects_duplicate_email(
    db_session,
    user,
):
    with pytest.raises(
        ConflictError,
        match="already registered",
    ):
        user_service.register_user(
            user.email.upper(),
            "StrongPass123",
            Role.PATIENT,
        )


def test_register_user_sets_password(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    user = user_service.register_user(
        "password-user@example.com",
        "StrongPass123",
        Role.PATIENT,
    )

    db_session.flush()

    assert user.check_password("StrongPass123")
    assert not user.check_password("WrongPassword123")


def test_register_user_creates_audit_log(
    db_session,
    monkeypatch,
):
    calls = []

    def fake_audit(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        fake_audit,
    )

    user = user_service.register_user(
        "audited-user@example.com",
        "StrongPass123",
        Role.PATIENT,
    )

    assert len(calls) == 1

    audit = calls[0]

    assert audit["action"] == AuditAction.CREATE
    assert audit["entity_type"] == "User"
    assert audit["entity_id"] == user.id
    assert "audited-user@example.com" in audit["description"]


# ============================================================================
# AUTHENTICATE USER
# ============================================================================


@pytest.mark.parametrize(
    "email,password",
    [
        (None, "StrongPass123"),
        ("", "StrongPass123"),
        ("user@example.com", None),
        ("user@example.com", ""),
    ],
)
def test_authenticate_user_requires_credentials(
    db_session,
    email,
    password,
):
    with pytest.raises(
        ValidationError,
        match="Email and password are required",
    ):
        user_service.authenticate_user(
            email,
            password,
        )


def test_authenticate_user_rejects_unknown_user(
    db_session,
):
    with pytest.raises(
        ValidationError,
        match="Invalid email or password",
    ):
        user_service.authenticate_user(
            "missing@example.com",
            "StrongPass123",
        )


def test_authenticate_user_rejects_wrong_password(
    db_session,
    user,
):
    user.set_password("CorrectPass123")
    db_session.commit()

    with pytest.raises(
        ValidationError,
        match="Invalid email or password",
    ):
        user_service.authenticate_user(
            user.email,
            "WrongPass123",
        )


def test_authenticate_user_rejects_inactive_user(
    db_session,
    user,
):
    user.set_password("CorrectPass123")
    user.is_active = False
    db_session.commit()

    with pytest.raises(
        ValidationError,
        match="This account has been deactivated",
    ):
        user_service.authenticate_user(
            user.email,
            "CorrectPass123",
        )


def test_authenticate_user_returns_tokens(
    app,
    db_session,
    user,
    monkeypatch,
):
    user.set_password("CorrectPass123")
    user.is_active = True
    db_session.commit()

    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        result = user_service.authenticate_user(
            user.email,
            "CorrectPass123",
        )

    assert result["access_token"]
    assert result["refresh_token"]
    assert result["user_id"] == user.id
    assert result["role"] == user.role.value


def test_authenticate_user_creates_login_audit(
    app,
    db_session,
    user,
    monkeypatch,
):
    user.set_password("CorrectPass123")
    user.is_active = True
    db_session.commit()

    calls = []

    def fake_audit(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        fake_audit,
    )

    with app.app_context():
        user_service.authenticate_user(
            user.email,
            "CorrectPass123",
        )

    assert len(calls) == 1

    audit = calls[0]

    assert audit["action"] == AuditAction.LOGIN
    assert audit["entity_type"] == "User"
    assert audit["entity_id"] == user.id
    assert audit["user_id"] == user.id


def test_authenticate_user_updates_last_login(
    app,
    db_session,
    user,
    monkeypatch,
):
    user.set_password("CorrectPass123")
    user.is_active = True
    db_session.commit()

    monkeypatch.setattr(
        user_service,
        "create_audit_log",
        lambda **kwargs: None,
    )

    with app.app_context():
        user_service.authenticate_user(
            user.email,
            "CorrectPass123",
        )

    db_session.refresh(user)

    assert user.last_login_at is not None