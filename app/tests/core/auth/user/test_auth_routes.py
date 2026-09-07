from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask_jwt_extended import create_refresh_token

from app.core.auth.user.routes import auth_routes
from app.core.enums.role_enums import Role
from app.core.exceptions import DomainError


# ============================================================================
# HELPERS
# ============================================================================


def domain_error(
    message="Test domain error",
    status_code=400,
):

    error = DomainError(message)
    error.status_code = status_code
    return error


def valid_register_payload():
    return {
        "email": "newuser@test.com",
        "password": "StrongPassword123!",
    }


def valid_login_payload():
    return {
        "email": "admin@test.com",
        "password": "supersecret",
    }


def token_from_headers(headers):
    """
    Extract the JWT value from an Authorization header dictionary.
    """
    return headers["Authorization"].split(" ", 1)[1]


# ============================================================================
# REGISTER
# ============================================================================


class TestRegisterRoute:
    def test_register_success(
        self,
        client,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=101,
            email="newuser@test.com",
            role=Role.PATIENT,
            clinic_id=None,
            is_active=True,
            created_at=None,
        )

        service = Mock(return_value=user)

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json=valid_register_payload(),
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == 101
        assert body["data"]["email"] == "newuser@test.com"
        assert body["data"]["role"] == Role.PATIENT.value
        assert body["data"]["clinic_id"] is None
        assert body["data"]["is_active"] is True
        assert body["data"]["created_at"] is None
        assert body["data"]["last_login_at"] is None

        service.assert_called_once_with(
            email="newuser@test.com",
            password="StrongPassword123!",
            role=Role.PATIENT,
            clinic_id=None,
        )

    def test_register_client_cannot_set_role(
        self,
        client,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=102,
            email="attacker@test.com",
            role=Role.PATIENT,
            clinic_id=None,
            is_active=True,
            created_at=None,
        )

        service = Mock(return_value=user)

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        payload = {
            "email": "attacker@test.com",
            "password": "StrongPassword123!",
            "role": Role.ADMIN.value,
        }

        response = client.post(
            "/api/auth/register",
            json=payload,
        )

        assert response.status_code == 201

        service.assert_called_once()

        kwargs = service.call_args.kwargs

        assert kwargs["role"] == Role.PATIENT
        assert kwargs["role"] != Role.ADMIN

    def test_register_validation_failure(
        self,
        client,
        monkeypatch,
    ):
        service = Mock()

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json={},
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"
        assert "details" in body

        service.assert_not_called()

    def test_register_invalid_email(
        self,
        client,
        monkeypatch,
    ):
        service = Mock()

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        service.assert_not_called()

    def test_register_domain_error(
        self,
        client,
        monkeypatch,
    ):
        service = Mock(
            side_effect=domain_error(
                "Email already exists",
                409,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json=valid_register_payload(),
        )

        assert response.status_code == 409

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Email already exists"


# ============================================================================
# LOGIN
# ============================================================================


class TestLoginRoute:
    def test_login_success(
        self,
        client,
        monkeypatch,
    ):
        result = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user": {
                "id": 1,
                "email": "admin@test.com",
                "role": Role.ADMIN.value,
            },
        }

        service = Mock(return_value=result)

        monkeypatch.setattr(
            auth_routes,
            "authenticate_user",
            service,
        )

        response = client.post(
            "/api/auth/login",
            json=valid_login_payload(),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == result

        service.assert_called_once_with(
            email="admin@test.com",
            password="supersecret",
        )

    def test_login_validation_failure(
        self,
        client,
        monkeypatch,
    ):
        service = Mock()

        monkeypatch.setattr(
            auth_routes,
            "authenticate_user",
            service,
        )

        response = client.post(
            "/api/auth/login",
            json={},
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        service.assert_not_called()

    def test_login_invalid_email(
        self,
        client,
        monkeypatch,
    ):
        service = Mock()

        monkeypatch.setattr(
            auth_routes,
            "authenticate_user",
            service,
        )

        response = client.post(
            "/api/auth/login",
            json={
                "email": "invalid-email",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400

        service.assert_not_called()

    def test_login_domain_error(
        self,
        client,
        monkeypatch,
    ):
        service = Mock(
            side_effect=domain_error(
                "Invalid email or password",
                401,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_user",
            service,
        )

        response = client.post(
            "/api/auth/login",
            json=valid_login_payload(),
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid email or password"


# ============================================================================
# GOOGLE LOGIN
# ============================================================================


class TestGoogleLoginRoute:
    def test_google_login_success(
        self,
        client,
        monkeypatch,
    ):
        service = Mock(
            return_value=(
                "https://accounts.google.com/o/oauth2/auth",
                "test-state",
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "get_google_authorization_url",
            service,
        )

        response = client.get(
            "/api/auth/google",
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert (
            body["data"]["authorization_url"]
            == "https://accounts.google.com/o/oauth2/auth"
        )
        assert body["data"]["state"] == "test-state"

        service.assert_called_once_with()

    def test_google_login_domain_error(
        self,
        client,
        monkeypatch,
    ):
        service = Mock(
            side_effect=domain_error(
                "Google OAuth is not configured",
                503,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "get_google_authorization_url",
            service,
        )

        response = client.get(
            "/api/auth/google",
        )

        assert response.status_code == 503

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Google OAuth is not configured"


# ============================================================================
# GOOGLE CALLBACK
# ============================================================================


class TestGoogleCallbackRoute:
    def test_google_callback_success(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock()

        authenticate = Mock(
            return_value={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "user": {
                    "id": 1,
                    "email": "google@test.com",
                    "role": Role.PATIENT.value,
                },
            }
        )

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?code=test-code"
            "&state=test-state"
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert (
            body["data"]["access_token"]
            == "access-token"
        )

        validate_state.assert_called_once_with(
            "test-state",
        )

        authenticate.assert_called_once_with(
            code="test-code",
        )

    def test_google_callback_provider_error(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock()
        authenticate = Mock()

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?error=access_denied"
            "&error_description=User%20denied%20access"
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "access_denied"
        assert (
            body["error_description"]
            == "User denied access"
        )

        validate_state.assert_not_called()
        authenticate.assert_not_called()

    def test_google_callback_missing_code(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock()
        authenticate = Mock()

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?state=test-state"
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        validate_state.assert_not_called()
        authenticate.assert_not_called()

    def test_google_callback_missing_state(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock()
        authenticate = Mock()

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?code=test-code"
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        validate_state.assert_not_called()
        authenticate.assert_not_called()

    def test_google_callback_invalid_state(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock(
            side_effect=domain_error(
                "Invalid OAuth state",
                401,
            )
        )

        authenticate = Mock()

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?code=test-code"
            "&state=bad-state"
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid OAuth state"

        validate_state.assert_called_once_with(
            "bad-state",
        )

        authenticate.assert_not_called()

    def test_google_callback_authentication_error(
        self,
        client,
        monkeypatch,
    ):
        validate_state = Mock()

        authenticate = Mock(
            side_effect=domain_error(
                "Google authentication failed",
                401,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "validate_google_oauth_state",
            validate_state,
        )

        monkeypatch.setattr(
            auth_routes,
            "authenticate_google_code",
            authenticate,
        )

        response = client.get(
            "/api/auth/google/callback"
            "?code=test-code"
            "&state=test-state"
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Google authentication failed"
        )

        validate_state.assert_called_once_with(
            "test-state",
        )

        authenticate.assert_called_once_with(
            code="test-code",
        )


# ============================================================================
# REFRESH
# ============================================================================


class TestRefreshRoute:
    def test_refresh_requires_refresh_token(
        self,
        client,
    ):
        response = client.post(
            "/api/auth/refresh",
        )

        assert response.status_code == 401

    def test_refresh_rejects_access_token(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = auth_headers_for(user)

        response = client.post(
            "/api/auth/refresh",
            headers=headers,
        )

        assert response.status_code == 422

    def test_refresh_success(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        revoke = Mock()

        create_access = Mock(
            return_value="new-access-token",
        )

        create_refresh = Mock(
            return_value="new-refresh-token",
        )

        monkeypatch.setattr(
            auth_routes,
            "revoke_current_token",
            revoke,
        )

        monkeypatch.setattr(
            auth_routes,
            "create_access_token",
            create_access,
        )

        monkeypatch.setattr(
            auth_routes,
            "create_refresh_token",
            create_refresh,
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                )
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert (
            body["data"]["access_token"]
            == "new-access-token"
        )
        assert (
            body["data"]["refresh_token"]
            == "new-refresh-token"
        )
        assert body["data"]["user_id"] == user.id
        assert body["data"]["role"] == user.role.value

        revoke.assert_called_once_with()

        create_access.assert_called_once_with(
            identity=str(user.id),
            additional_claims={
                "role": user.role.value,
            },
        )

        create_refresh.assert_called_once_with(
            identity=str(user.id),
        )

    def test_refresh_user_not_found(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        original_get = auth_routes.db.session.get

        def fake_get(model, object_id):
            return None

        monkeypatch.setattr(
            auth_routes.db.session,
            "get",
            fake_get,
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                )
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "User not found"

        monkeypatch.setattr(
            auth_routes.db.session,
            "get",
            original_get,
        )

    def test_refresh_inactive_user(
        self,
        app,
        client,
        make_user,
        clinic,
    ):
        inactive_user = make_user(
            clinic,
            role=Role.ADMIN,
            is_active=False,
            email="inactive-refresh@test.com",
        )

        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(inactive_user.id),
            )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                )
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "This account has been deactivated"
        )

    def test_refresh_invalid_identity(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        monkeypatch.setattr(
            auth_routes,
            "get_jwt_identity",
            Mock(return_value="not-an-integer"),
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                )
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Invalid authentication identity"
        )

    def test_refresh_domain_error(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        revoke = Mock(
            side_effect=domain_error(
                "Token revocation failed",
                500,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "revoke_current_token",
            revoke,
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                )
            },
        )

        assert response.status_code == 500

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Token revocation failed"
        )


# ============================================================================
# LOGOUT
# ============================================================================


class TestLogoutRoute:
    def test_logout_requires_access_token(
        self,
        client,
    ):
        response = client.post(
            "/api/auth/logout",
            json={
                "refresh_token": "something",
            },
        )

        assert response.status_code == 401

    def test_logout_requires_refresh_token(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={},
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Refresh token is required"
        )

    def test_logout_invalid_refresh_token(
        self,
        client,
        user,
        auth_headers_for,
    ):
        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={
                "refresh_token": "not-a-real-jwt",
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Invalid refresh token"
        )

    def test_logout_rejects_access_token_as_refresh(
        self,
        app,
        client,
        user,
        auth_headers_for,
    ):
        access_token = token_from_headers(
            auth_headers_for(user),
        )

        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={
                "refresh_token": access_token,
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Invalid refresh token"
        )

    def test_logout_rejects_other_users_refresh_token(
        self,
        app,
        client,
        make_user,
        clinic,
        user,
        auth_headers_for,
    ):
        other_user = make_user(
            clinic,
            role=Role.PATIENT,
            email="other-logout@test.com",
        )

        with app.app_context():
            other_refresh_token = (
                create_refresh_token(
                    identity=str(other_user.id),
                )
            )

        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={
                "refresh_token": other_refresh_token,
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Refresh token does not belong to the current user"
        )

    def test_logout_success(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        revoke_token = Mock()
        revoke_current = Mock()

        monkeypatch.setattr(
            auth_routes,
            "revoke_token",
            revoke_token,
        )

        monkeypatch.setattr(
            auth_routes,
            "revoke_current_token",
            revoke_current,
        )

        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={
                "refresh_token": refresh_token,
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert (
            body["message"]
            == "Successfully logged out"
        )

        revoke_token.assert_called_once()

        refresh_payload = (
            revoke_token.call_args.args[0]
        )

        assert (
            refresh_payload["type"]
            == "refresh"
        )

        assert (
            str(refresh_payload["sub"])
            == str(user.id)
        )

        revoke_current.assert_called_once_with()

    def test_logout_domain_error(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        with app.app_context():
            refresh_token = create_refresh_token(
                identity=str(user.id),
            )

        revoke = Mock(
            side_effect=domain_error(
                "Failed to revoke refresh token",
                500,
            )
        )

        monkeypatch.setattr(
            auth_routes,
            "revoke_token",
            revoke,
        )

        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_for(user),
            json={
                "refresh_token": refresh_token,
            },
        )

        assert response.status_code == 500

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Failed to revoke refresh token"
        )


# ============================================================================
# BLUEPRINT / ROUTE REGISTRATION
# ============================================================================


class TestAuthRouteRegistration:
    def test_auth_routes_are_registered(
        self,
        app,
    ):
        routes = {
            rule.rule
            for rule in app.url_map.iter_rules()
        }

        assert "/api/auth/register" in routes
        assert "/api/auth/login" in routes
        assert "/api/auth/google" in routes
        assert "/api/auth/google/callback" in routes
        assert "/api/auth/refresh" in routes
        assert "/api/auth/logout" in routes

    def test_register_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/register"
        )

        assert "POST" in rule.methods

    def test_login_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/login"
        )

        assert "POST" in rule.methods

    def test_google_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/google"
        )

        assert "GET" in rule.methods

    def test_google_callback_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule
            == "/api/auth/google/callback"
        )

        assert "GET" in rule.methods

    def test_refresh_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/refresh"
        )

        assert "POST" in rule.methods

    def test_logout_methods(
        self,
        app,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/logout"
        )

        assert "POST" in rule.methods