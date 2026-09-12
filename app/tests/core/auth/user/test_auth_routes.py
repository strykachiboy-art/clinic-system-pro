from __future__ import annotations

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
    return headers["Authorization"].split(
        " ",
        1,
    )[1]


def make_refresh_token(
    app,
    user,
):
    """
    Create a refresh token compatible with the current
    fail-closed token validation flow.
    """
    with app.app_context():
        return create_refresh_token(
            identity=str(user.id),
            additional_claims={
                "token_version": user.token_version,
            },
        )


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

        service = Mock(
            return_value=user,
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

        assert response.status_code == 201

        body = response.get_json()

        assert body["success"] is True

        assert body["data"] == {
            "id": 101,
            "email": "newuser@test.com",
            "role": Role.PATIENT.value,
            "clinic_id": None,
            "is_active": True,
            "created_at": None,
            "last_login_at": None,
        }

        service.assert_called_once_with(
            email="newuser@test.com",
            password="StrongPassword123!",
            role=Role.PATIENT,
            clinic_id=None,
        )

    def test_register_success_with_clinic(
        self,
        client,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=102,
            email="clinicuser@test.com",
            role=Role.PATIENT,
            clinic_id=55,
            is_active=True,
            created_at=None,
        )

        service = Mock(
            return_value=user,
        )

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json={
                "email": "clinicuser@test.com",
                "password": "StrongPassword123!",
                "clinic_id": 55,
            },
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["data"]["clinic_id"] == 55

        service.assert_called_once_with(
            email="clinicuser@test.com",
            password="StrongPassword123!",
            role=Role.PATIENT,
            clinic_id=55,
        )

    def test_register_client_cannot_set_role(
        self,
        client,
        monkeypatch,
    ):
        user = SimpleNamespace(
            id=103,
            email="attacker@test.com",
            role=Role.PATIENT,
            clinic_id=None,
            is_active=True,
            created_at=None,
        )

        service = Mock(
            return_value=user,
        )

        monkeypatch.setattr(
            auth_routes,
            "register_user",
            service,
        )

        response = client.post(
            "/api/auth/register",
            json={
                "email": "attacker@test.com",
                "password": "StrongPassword123!",
                "role": Role.ADMIN.value,
            },
        )

        assert response.status_code == 201

        service.assert_called_once()

        kwargs = service.call_args.kwargs

        assert kwargs["role"] is Role.PATIENT
        assert kwargs["role"] is not Role.ADMIN

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

    def test_register_invalid_password(
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
                "email": "valid@test.com",
                "password": "short",
            },
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        service.assert_not_called()

    def test_register_invalid_clinic_id(
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
                "email": "valid@test.com",
                "password": "StrongPassword123!",
                "clinic_id": 0,
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
            ),
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
            "user_id": 1,
            "role": Role.ADMIN.value,
        }

        service = Mock(
            return_value=result,
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

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        service.assert_not_called()

    def test_login_invalid_password(
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
                "email": "admin@test.com",
                "password": "",
            },
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

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
            ),
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
        assert body["error"] == (
            "Invalid email or password"
        )

        service.assert_called_once_with(
            email="admin@test.com",
            password="supersecret",
        )


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
                "https://accounts.google.com/o/oauth2/v2/auth"
                "?client_id=test",
                "test-state",
            ),
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
            == (
                "https://accounts.google.com/"
                "o/oauth2/v2/auth?client_id=test"
            )
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
            ),
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
        assert body["error"] == (
            "Google OAuth is not configured"
        )


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
                "user_id": 1,
                "role": Role.PATIENT.value,
            },
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
            "&state=test-state",
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user_id": 1,
            "role": Role.PATIENT.value,
        }

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
            "&error_description=User%20denied%20access",
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

    def test_google_callback_provider_error_without_description(
        self,
        client,
    ):
        response = client.get(
            "/api/auth/google/callback"
            "?error=access_denied",
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "access_denied"
        assert body["error_description"] is None

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
            "?state=test-state",
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
            "?code=test-code",
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation failed"

        validate_state.assert_not_called()
        authenticate.assert_not_called()

    def test_google_callback_rejects_empty_code(
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
            "?code="
            "&state=test-state",
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
                "Invalid Google OAuth state",
                401,
            ),
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
            "&state=bad-state",
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Invalid Google OAuth state"
        )

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
            ),
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
            "&state=test-state",
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Google authentication failed"
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
        response = client.post(
            "/api/auth/refresh",
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

    def test_refresh_success(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        user.token_version = 4

        refresh_token = make_refresh_token(
            app,
            user,
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
                ),
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True

        assert body["data"] == {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "user_id": user.id,
            "role": user.role.value,
        }

        revoke.assert_called_once_with()

        create_access.assert_called_once_with(
            identity=str(user.id),
            additional_claims={
                "role": user.role.value,
                "token_version": user.token_version,
            },
        )

        create_refresh.assert_called_once_with(
            identity=str(user.id),
            additional_claims={
                "token_version": user.token_version,
            },
        )

    def test_refresh_user_not_found(
        self,
        app,
        user,
        monkeypatch,
    ):
        """
        Test the route's explicit User-not-found branch.

        This intentionally bypasses the outer JWT decorator because
        token validation itself performs a database user lookup before
        the route body executes.
        """
        with app.test_request_context(
            "/api/auth/refresh",
            method="POST",
        ):
            monkeypatch.setattr(
                auth_routes,
                "get_jwt_identity",
                Mock(
                    return_value=str(user.id),
                ),
            )

            def fake_get(
                model,
                object_id,
            ):
                return None

            monkeypatch.setattr(
                auth_routes.db.session,
                "get",
                fake_get,
            )

            response = auth_routes.refresh.__wrapped__()

            assert response[1] == 401

            body = response[0].get_json()

            assert body["success"] is False
            assert body["error"] == "User not found"

    def test_refresh_inactive_user_rejected_by_token_validation(
        self,
        app,
        client,
        make_user,
        clinic,
    ):
        """
        Integration-level test proving inactive users are rejected
        by the fail-closed JWT validation layer before the route body.
        """
        inactive_user = make_user(
            clinic,
            role=Role.ADMIN,
            is_active=False,
            email="inactive-refresh@test.com",
        )

        refresh_token = make_refresh_token(
            app,
            inactive_user,
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                ),
            },
        )

        assert response.status_code == 401

    def test_refresh_inactive_user_route_branch(
        self,
        app,
        make_user,
        clinic,
        monkeypatch,
    ):
        """
        Test the explicit inactive-user branch inside refresh().
        """
        inactive_user = make_user(
            clinic,
            role=Role.ADMIN,
            is_active=False,
            email="inactive-route@test.com",
        )

        with app.test_request_context(
            "/api/auth/refresh",
            method="POST",
        ):
            monkeypatch.setattr(
                auth_routes,
                "get_jwt_identity",
                Mock(
                    return_value=str(inactive_user.id),
                ),
            )

            response = auth_routes.refresh.__wrapped__()

            assert response[1] == 401

            body = response[0].get_json()

            assert body["success"] is False
            assert body["error"] == (
                "This account has been deactivated"
            )

    def test_refresh_invalid_identity(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
        )

        monkeypatch.setattr(
            auth_routes,
            "get_jwt_identity",
            Mock(
                return_value="not-an-integer",
            ),
        )

        response = client.post(
            "/api/auth/refresh",
            headers={
                "Authorization": (
                    f"Bearer {refresh_token}"
                ),
            },
        )

        assert response.status_code == 401

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Invalid authentication identity"
        )

    def test_refresh_domain_error(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
        )

        revoke = Mock(
            side_effect=domain_error(
                "Token revocation failed",
                500,
            ),
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
                ),
            },
        )

        assert response.status_code == 500

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Token revocation failed"
        )

    def test_refresh_does_not_generate_tokens_when_revocation_fails(
        self,
        app,
        client,
        user,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
        )

        revoke = Mock(
            side_effect=domain_error(
                "Token revocation failed",
                500,
            ),
        )

        create_access = Mock()
        create_refresh = Mock()

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
                ),
            },
        )

        assert response.status_code == 500

        create_access.assert_not_called()
        create_refresh.assert_not_called()


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
        assert body["error"] == (
            "Refresh token is required"
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
        assert body["error"] == (
            "Invalid refresh token"
        )

    def test_logout_rejects_access_token_as_refresh(
        self,
        client,
        user,
        auth_headers_for,
    ):
        access_token = token_from_headers(
            auth_headers_for(user)
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
        assert body["error"] == (
            "Invalid refresh token"
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

        other_refresh_token = make_refresh_token(
            app,
            other_user,
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
        assert body["error"] == (
            "Refresh token does not belong "
            "to the current user"
        )

    def test_logout_success(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
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
        assert body["message"] == (
            "Successfully logged out"
        )

        revoke_token.assert_called_once()

        refresh_payload = (
            revoke_token.call_args.args[0]
        )

        assert refresh_payload["type"] == "refresh"

        assert (
            str(refresh_payload["sub"])
            == str(user.id)
        )

        assert (
            refresh_payload["token_version"]
            == user.token_version
        )

        revoke_current.assert_called_once_with()

    def test_logout_domain_error_from_refresh_revocation(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
        )

        revoke = Mock(
            side_effect=domain_error(
                "Failed to revoke refresh token",
                500,
            ),
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
        assert body["error"] == (
            "Failed to revoke refresh token"
        )

    def test_logout_does_not_revoke_access_token_when_refresh_revocation_fails(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        refresh_token = make_refresh_token(
            app,
            user,
        )

        revoke_token = Mock(
            side_effect=domain_error(
                "Failed to revoke refresh token",
                500,
            ),
        )

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

        assert response.status_code == 500

        revoke_current.assert_not_called()


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

    @pytest.mark.parametrize(
        "route,method",
        [
            (
                "/api/auth/register",
                "POST",
            ),
            (
                "/api/auth/login",
                "POST",
            ),
            (
                "/api/auth/google",
                "GET",
            ),
            (
                "/api/auth/google/callback",
                "GET",
            ),
            (
                "/api/auth/refresh",
                "POST",
            ),
            (
                "/api/auth/logout",
                "POST",
            ),
        ],
    )
    def test_auth_route_methods(
        self,
        app,
        route,
        method,
    ):
        rule = next(
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == route
        )

        assert method in rule.methods