import pytest
from unittest.mock import MagicMock, patch

from app.core.enums.role_enums import Role
from app.core.exceptions import ConflictError, ValidationError
from app.core.auth.user.models.user_model import User
from app.core.auth.user.models.user_auth_identity_model import UserAuthIdentity
from app.core.auth.user.schema.user_schema import GoogleUserInfoSchema

from app.core.auth.user.services import google_auth_service


# ---------------------------------------------------------------------------
# OAuth state
# ---------------------------------------------------------------------------


def test_create_google_oauth_state_raises_when_redis_unavailable():
    with patch.object(
        google_auth_service,
        "redis_client",
        None,
    ):
        with pytest.raises(ValidationError, match="Redis is not available"):
            google_auth_service.create_google_oauth_state()


def test_create_google_oauth_state_stores_state(app):
    redis_mock = MagicMock()

    with patch.object(
        google_auth_service,
        "redis_client",
        redis_mock,
    ):
        state = google_auth_service.create_google_oauth_state()

    assert state
    redis_mock.setex.assert_called_once_with(
        f"{google_auth_service.GOOGLE_OAUTH_STATE_PREFIX}{state}",
        google_auth_service.GOOGLE_OAUTH_STATE_TTL,
        "1",
    )


def test_validate_google_oauth_state_requires_state(app):
    with pytest.raises(ValidationError, match="OAuth state is required"):
        google_auth_service.validate_google_oauth_state("")


def test_validate_google_oauth_state_raises_when_redis_unavailable(app):
    with patch.object(
        google_auth_service,
        "redis_client",
        None,
    ):
        with pytest.raises(ValidationError, match="Redis is not available"):
            google_auth_service.validate_google_oauth_state("state")


def test_validate_google_oauth_state_rejects_invalid_state(app):
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    with patch.object(
        google_auth_service,
        "redis_client",
        redis_mock,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid or expired OAuth state",
        ):
            google_auth_service.validate_google_oauth_state("bad-state")

    redis_mock.delete.assert_not_called()


def test_validate_google_oauth_state_accepts_and_deletes_valid_state(app):
    redis_mock = MagicMock()
    redis_mock.get.return_value = "1"

    with patch.object(
        google_auth_service,
        "redis_client",
        redis_mock,
    ):
        google_auth_service.validate_google_oauth_state("valid-state")

    redis_mock.get.assert_called_once_with(
        f"{google_auth_service.GOOGLE_OAUTH_STATE_PREFIX}valid-state"
    )
    redis_mock.delete.assert_called_once_with(
        f"{google_auth_service.GOOGLE_OAUTH_STATE_PREFIX}valid-state"
    )


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


def test_get_google_authorization_url_requires_client_id(app):
    app.config["GOOGLE_CLIENT_ID"] = None
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    with pytest.raises(
        ValidationError,
        match="GOOGLE_CLIENT_ID is missing",
    ):
        google_auth_service.get_google_authorization_url()


def test_get_google_authorization_url_requires_redirect_uri(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_REDIRECT_URI"] = None

    with pytest.raises(
        ValidationError,
        match="GOOGLE_REDIRECT_URI is missing",
    ):
        google_auth_service.get_google_authorization_url()


def test_get_google_authorization_url_returns_url_and_state(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_REDIRECT_URI"] = (
        "http://localhost/api/auth/google/callback"
    )

    with patch.object(
        google_auth_service,
        "create_google_oauth_state",
        return_value="test-state",
    ):
        authorization_url, state = (
            google_auth_service.get_google_authorization_url()
        )

    assert state == "test-state"
    assert authorization_url.startswith(
        google_auth_service.GOOGLE_AUTHORIZATION_URL
    )
    assert "client_id=client-id" in authorization_url
    assert "response_type=code" in authorization_url
    assert "state=test-state" in authorization_url
    assert "scope=openid+email+profile" in authorization_url


# ---------------------------------------------------------------------------
# Google authorization code exchange
# ---------------------------------------------------------------------------


def test_exchange_google_code_requires_code(app):
    with pytest.raises(
        ValidationError,
        match="Google authorization code is required",
    ):
        google_auth_service.exchange_google_code("")


def test_exchange_google_code_requires_configuration(app):
    app.config["GOOGLE_CLIENT_ID"] = None
    app.config["GOOGLE_CLIENT_SECRET"] = None
    app.config["GOOGLE_REDIRECT_URI"] = None

    with pytest.raises(
        ValidationError,
        match="Google OAuth is not configured",
    ):
        google_auth_service.exchange_google_code("code")


def test_exchange_google_code_requires_redirect_uri(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = None

    with pytest.raises(
        ValidationError,
        match="redirect URI is not configured",
    ):
        google_auth_service.exchange_google_code("code")


def test_exchange_google_code_handles_request_failure(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    with patch.object(
        google_auth_service.requests,
        "post",
        side_effect=google_auth_service.requests.RequestException(
            "network error"
        ),
    ):
        with pytest.raises(
            ValidationError,
            match="Unable to communicate with Google",
        ):
            google_auth_service.exchange_google_code("code")


def test_exchange_google_code_handles_google_error(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    response = MagicMock()
    response.ok = False
    response.json.return_value = {
        "error_description": "Invalid authorization code"
    }

    with patch.object(
        google_auth_service.requests,
        "post",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid authorization code",
        ):
            google_auth_service.exchange_google_code("code")


def test_exchange_google_code_handles_google_error_without_description(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    response = MagicMock()
    response.ok = False
    response.json.return_value = {}

    with patch.object(
        google_auth_service.requests,
        "post",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Google authorization failed",
        ):
            google_auth_service.exchange_google_code("code")


def test_exchange_google_code_handles_invalid_json(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    response = MagicMock()
    response.ok = True
    response.json.side_effect = ValueError()

    with patch.object(
        google_auth_service.requests,
        "post",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid response received from Google",
        ):
            google_auth_service.exchange_google_code("code")


def test_exchange_google_code_requires_access_token(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "token_type": "Bearer",
    }

    with patch.object(
        google_auth_service.requests,
        "post",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Google did not return an access token",
        ):
            google_auth_service.exchange_google_code("code")


def test_exchange_google_code_success(app):
    app.config["GOOGLE_CLIENT_ID"] = "client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "client-secret"
    app.config["GOOGLE_REDIRECT_URI"] = "http://localhost/callback"

    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "access_token": "google-access-token",
        "refresh_token": "google-refresh-token",
    }

    with patch.object(
        google_auth_service.requests,
        "post",
        return_value=response,
    ) as post_mock:
        result = google_auth_service.exchange_google_code("auth-code")

    assert result["access_token"] == "google-access-token"

    post_mock.assert_called_once()
    _, kwargs = post_mock.call_args

    assert kwargs["data"]["code"] == "auth-code"
    assert kwargs["data"]["client_id"] == "client-id"
    assert kwargs["data"]["client_secret"] == "client-secret"
    assert kwargs["data"]["redirect_uri"] == "http://localhost/callback"
    assert kwargs["data"]["grant_type"] == "authorization_code"
    assert kwargs["timeout"] == 10


# ---------------------------------------------------------------------------
# Google user information
# ---------------------------------------------------------------------------


def test_get_google_user_info_requires_access_token():
    with pytest.raises(
        ValidationError,
        match="Google access token is required",
    ):
        google_auth_service.get_google_user_info("")


def test_get_google_user_info_handles_request_failure():
    with patch.object(
        google_auth_service.requests,
        "get",
        side_effect=google_auth_service.requests.RequestException(
            "network error"
        ),
    ):
        with pytest.raises(
            ValidationError,
            match="Unable to retrieve Google user information",
        ):
            google_auth_service.get_google_user_info("token")


def test_get_google_user_info_handles_http_failure():
    response = MagicMock()
    response.ok = False

    with patch.object(
        google_auth_service.requests,
        "get",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Unable to verify Google account",
        ):
            google_auth_service.get_google_user_info("token")


def test_get_google_user_info_handles_invalid_json():
    response = MagicMock()
    response.ok = True
    response.json.side_effect = ValueError()

    with patch.object(
        google_auth_service.requests,
        "get",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid user information received from Google",
        ):
            google_auth_service.get_google_user_info("token")


@pytest.mark.parametrize(
    "data",
    [
        {"email": "user@example.com", "email_verified": True},
        {"sub": "google-123", "email_verified": True},
        {"sub": "google-123", "email": None, "email_verified": True},
    ],
)
def test_get_google_user_info_requires_complete_account_data(data):
    response = MagicMock()
    response.ok = True
    response.json.return_value = data

    with patch.object(
        google_auth_service.requests,
        "get",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Google account information is incomplete",
        ):
            google_auth_service.get_google_user_info("token")


def test_get_google_user_info_requires_verified_email():
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "sub": "google-123",
        "email": "user@example.com",
        "email_verified": False,
    }

    with patch.object(
        google_auth_service.requests,
        "get",
        return_value=response,
    ):
        with pytest.raises(
            ValidationError,
            match="Google email address is not verified",
        ):
            google_auth_service.get_google_user_info("token")


def test_get_google_user_info_success():
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "sub": "google-123",
        "email": "User@example.com",
        "email_verified": True,
        "given_name": "John",
        "family_name": "Doe",
        "picture": "https://example.com/photo.jpg",
    }

    with patch.object(
        google_auth_service.requests,
        "get",
        return_value=response,
    ) as get_mock:
        result = google_auth_service.get_google_user_info(
            "google-access-token"
        )

    assert isinstance(result, GoogleUserInfoSchema)
    assert result.provider_user_id == "google-123"
    assert result.email == "User@example.com"
    assert result.first_name == "John"
    assert result.last_name == "Doe"
    assert result.picture == "https://example.com/photo.jpg"
    assert result.email_verified is True

    get_mock.assert_called_once_with(
        google_auth_service.GOOGLE_USERINFO_URL,
        headers={"Authorization": "Bearer google-access-token"},
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Google identity lookup / user creation
# ---------------------------------------------------------------------------


def test_get_user_by_google_identity_returns_none_when_missing(db_session):
    result = google_auth_service._get_user_by_google_identity(
        "missing-google-id"
    )

    assert result is None


def test_get_user_by_google_identity_returns_existing_user(
    db_session,
    user,
):
    identity = UserAuthIdentity(
        user_id=user.id,
        provider=google_auth_service.GOOGLE_PROVIDER,
        provider_user_id="google-existing",
    )
    db_session.add(identity)
    db_session.flush()

    result = google_auth_service._get_user_by_google_identity(
        "google-existing"
    )

    assert result.id == user.id


def test_get_or_create_google_user_returns_existing_google_user(
    db_session,
    user,
):
    identity = UserAuthIdentity(
        user_id=user.id,
        provider=google_auth_service.GOOGLE_PROVIDER,
        provider_user_id="google-existing",
    )
    db_session.add(identity)
    db_session.flush()

    google_user = GoogleUserInfoSchema(
        provider_user_id="google-existing",
        email=user.email,
        email_verified=True,
    )

    result_user, created = (
        google_auth_service._get_or_create_google_user(google_user)
    )

    assert result_user.id == user.id
    assert created is False


def test_get_or_create_google_user_links_existing_email_user(
    db_session,
    user,
):
    google_user = GoogleUserInfoSchema(
        provider_user_id="google-new",
        email=user.email.upper(),
        email_verified=True,
    )

    result_user, created = (
        google_auth_service._get_or_create_google_user(google_user)
    )

    assert result_user.id == user.id
    assert created is False

    identity = UserAuthIdentity.query.filter_by(
        user_id=user.id,
        provider=google_auth_service.GOOGLE_PROVIDER,
    ).first()

    assert identity is not None
    assert identity.provider_user_id == "google-new"


def test_get_or_create_google_user_rejects_different_google_identity(
    db_session,
    user,
):
    identity = UserAuthIdentity(
        user_id=user.id,
        provider=google_auth_service.GOOGLE_PROVIDER,
        provider_user_id="google-old",
    )
    db_session.add(identity)
    db_session.flush()

    google_user = GoogleUserInfoSchema(
        provider_user_id="google-new",
        email=user.email,
        email_verified=True,
    )

    with pytest.raises(
        ConflictError,
        match="different Google identity",
    ):
        google_auth_service._get_or_create_google_user(google_user)


def test_get_or_create_google_user_creates_new_patient(
    db_session,
):
    google_user = GoogleUserInfoSchema(
        provider_user_id="google-new",
        email="newuser@example.com",
        first_name="New",
        last_name="User",
        email_verified=True,
    )

    with patch.object(
        google_auth_service,
        "create_audit_log",
    ) as audit_mock:
        result_user, created = (
            google_auth_service._get_or_create_google_user(google_user)
        )

    assert created is True
    assert result_user.id is not None
    assert result_user.email == "newuser@example.com"
    assert result_user.role == Role.PATIENT
    assert result_user.password_hash is None

    identity = UserAuthIdentity.query.filter_by(
        user_id=result_user.id,
        provider=google_auth_service.GOOGLE_PROVIDER,
        provider_user_id="google-new",
    ).first()

    assert identity is not None

    audit_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Google authentication
# ---------------------------------------------------------------------------


def test_authenticate_google_user_rejects_unverified_email():
    google_user = GoogleUserInfoSchema(
        provider_user_id="google-123",
        email="user@example.com",
        email_verified=False,
    )

    with pytest.raises(
        ValidationError,
        match="Google email address is not verified",
    ):
        google_auth_service.authenticate_google_user(google_user)


def test_authenticate_google_user_rejects_inactive_user(
    db_session,
    user,
):
    user.is_active = False
    db_session.flush()

    google_user = GoogleUserInfoSchema(
        provider_user_id="google-123",
        email=user.email,
        email_verified=True,
    )

    with patch.object(
        google_auth_service,
        "_get_or_create_google_user",
        return_value=(user, False),
    ):
        with pytest.raises(
            ValidationError,
            match="account has been deactivated",
        ):
            google_auth_service.authenticate_google_user(google_user)


def test_authenticate_google_user_success(
    db_session,
    user,
):
    google_user = GoogleUserInfoSchema(
        provider_user_id="google-123",
        email=user.email,
        email_verified=True,
    )

    with patch.object(
        google_auth_service,
        "_get_or_create_google_user",
        return_value=(user, False),
    ), patch.object(
        google_auth_service,
        "create_access_token",
        return_value="access-token",
    ) as access_mock, patch.object(
        google_auth_service,
        "create_refresh_token",
        return_value="refresh-token",
    ) as refresh_mock, patch.object(
        google_auth_service,
        "create_audit_log",
    ) as audit_mock:

        result = google_auth_service.authenticate_google_user(
            google_user
        )

    assert result == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "user_id": user.id,
        "role": user.role.value,
        "is_new_user": False,
    }

    access_mock.assert_called_once_with(
        identity=str(user.id),
        additional_claims={"role": user.role.value},
    )
    refresh_mock.assert_called_once_with(
        identity=str(user.id),
    )

    audit_mock.assert_called_once()


def test_authenticate_google_code_runs_full_flow():
    google_user = MagicMock()

    with patch.object(
        google_auth_service,
        "exchange_google_code",
        return_value={"access_token": "google-token"},
    ) as exchange_mock, patch.object(
        google_auth_service,
        "get_google_user_info",
        return_value=google_user,
    ) as info_mock, patch.object(
        google_auth_service,
        "authenticate_google_user",
        return_value={"user_id": 1},
    ) as auth_mock:

        result = google_auth_service.authenticate_google_code(
            "authorization-code"
        )

    assert result == {"user_id": 1}

    exchange_mock.assert_called_once_with("authorization-code")
    info_mock.assert_called_once_with("google-token")
    auth_mock.assert_called_once_with(google_user)