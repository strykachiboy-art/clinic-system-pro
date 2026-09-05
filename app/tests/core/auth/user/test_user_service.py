from datetime import timedelta
from unittest.mock import patch

import pytest
from flask_jwt_extended import decode_token

from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.exceptions import ConflictError, ValidationError
from app.core.auth.user.services.user_service import (
    authenticate_user,
    get_user,
    get_user_by_email,
    register_user,
)


# ============================================================================
# get_user()
# ============================================================================

class TestGetUser:
    def test_returns_user_when_user_exists(self, user):
        result = get_user(user.id)

        assert result.id == user.id
        assert result.email == user.email

    def test_raises_validation_error_when_user_does_not_exist(self):
        with pytest.raises(ValidationError, match="User 999999 not found"):
            get_user(999999)


# ============================================================================
# get_user_by_email()
# ============================================================================

class TestGetUserByEmail:
    def test_returns_user_by_email(self, user):
        result = get_user_by_email(user.email)

        assert result is not None
        assert result.id == user.id

    def test_email_lookup_is_case_insensitive(self, user):
        result = get_user_by_email(user.email.upper())

        assert result is not None
        assert result.id == user.id

    def test_email_lookup_strips_whitespace(self, user):
        result = get_user_by_email(f"  {user.email}  ")

        assert result is not None
        assert result.id == user.id

    def test_returns_none_when_email_does_not_exist(self):
        result = get_user_by_email("missing@test.com")

        assert result is None


# ============================================================================
# register_user()
# ============================================================================

class TestRegisterUser:
    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_registers_user_successfully(
        self,
        mock_create_audit_log,
        db,
        clinic,
    ):
        result = register_user(
            email="newuser@test.com",
            password="supersecret",
            role=Role.ADMIN,
            clinic_id=clinic.id,
        )

        assert result.id is not None
        assert result.email == "newuser@test.com"
        assert result.role == Role.ADMIN
        assert result.clinic_id == clinic.id
        assert result.check_password("supersecret") is True

        persisted = get_user(result.id)

        assert persisted.email == "newuser@test.com"
        assert persisted.role == Role.ADMIN
        assert persisted.clinic_id == clinic.id
        assert persisted.check_password("supersecret") is True

        mock_create_audit_log.assert_called_once_with(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=result.id,
            description="User registered: newuser@test.com (admin)",
        )

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_normalizes_email_before_persisting(
        self,
        mock_create_audit_log,
        clinic,
    ):
        result = register_user(
            email="  NEWUSER@TEST.COM  ",
            password="supersecret",
            role=Role.ADMIN,
            clinic_id=clinic.id,
        )

        assert result.email == "newuser@test.com"

        mock_create_audit_log.assert_called_once_with(
            action=AuditAction.CREATE,
            entity_type="User",
            entity_id=result.id,
            description="User registered: newuser@test.com (admin)",
        )

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_registers_user_without_clinic(
        self,
        mock_create_audit_log,
    ):
        result = register_user(
            email="noclinic@test.com",
            password="supersecret",
            role=Role.ADMIN,
            clinic_id=None,
        )

        assert result.id is not None
        assert result.email == "noclinic@test.com"
        assert result.clinic_id is None

        mock_create_audit_log.assert_called_once()

    def test_rejects_missing_email(self):
        with pytest.raises(
            ValidationError,
            match="A valid email is required",
        ):
            register_user(
                email="",
                password="supersecret",
                role=Role.ADMIN,
            )

    def test_rejects_email_without_at_symbol(self):
        with pytest.raises(
            ValidationError,
            match="A valid email is required",
        ):
            register_user(
                email="invalid-email",
                password="supersecret",
                role=Role.ADMIN,
            )

    def test_rejects_none_email(self):
        with pytest.raises(
            ValidationError,
            match="A valid email is required",
        ):
            register_user(
                email=None,
                password="supersecret",
                role=Role.ADMIN,
            )

    @pytest.mark.parametrize(
        "password",
        [
            "",
            "1234567",
            None,
        ],
    )
    def test_rejects_invalid_password(self, password):
        with pytest.raises(
            ValidationError,
            match="Password must be at least 8 characters",
        ):
            register_user(
                email="newuser@test.com",
                password=password,
                role=Role.ADMIN,
            )

    def test_accepts_password_of_exactly_eight_characters(self, clinic):
        result = register_user(
            email="eightchars@test.com",
            password="12345678",
            role=Role.ADMIN,
            clinic_id=clinic.id,
        )

        assert result.check_password("12345678") is True

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_rejects_duplicate_email(
        self,
        mock_create_audit_log,
        user,
    ):
        with pytest.raises(
            ConflictError,
            match=f"Email '{user.email}' is already registered",
        ):
            register_user(
                email=user.email,
                password="anotherpassword",
                role=Role.ADMIN,
                clinic_id=user.clinic_id,
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_duplicate_email_check_is_case_insensitive(
        self,
        mock_create_audit_log,
        user,
    ):
        with pytest.raises(
            ConflictError,
            match=f"Email '{user.email}' is already registered",
        ):
            register_user(
                email=user.email.upper(),
                password="anotherpassword",
                role=Role.ADMIN,
                clinic_id=user.clinic_id,
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_registration_does_not_create_audit_log_with_user_id(
        self,
        mock_create_audit_log,
        clinic,
    ):
        result = register_user(
            email="audit@test.com",
            password="supersecret",
            role=Role.ADMIN,
            clinic_id=clinic.id,
        )

        call_kwargs = mock_create_audit_log.call_args.kwargs

        assert call_kwargs["action"] == AuditAction.CREATE
        assert call_kwargs["entity_type"] == "User"
        assert call_kwargs["entity_id"] == result.id
        assert "user_id" not in call_kwargs

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_registration_uses_role_value_in_audit_description(
        self,
        mock_create_audit_log,
        clinic,
    ):
        result = register_user(
            email="doctor@test.com",
            password="supersecret",
            role=Role.DOCTOR,
            clinic_id=clinic.id,
        )

        call_kwargs = mock_create_audit_log.call_args.kwargs

        assert call_kwargs["description"] == (
            f"User registered: doctor@test.com ({result.role.value})"
        )


# ============================================================================
# authenticate_user()
# ============================================================================

class TestAuthenticateUser:
    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_authenticates_active_user_successfully(
        self,
        mock_create_audit_log,
        user,
        db,
    ):
        result = authenticate_user(
            email=user.email,
            password="supersecret",
        )

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user_id"] == user.id
        assert result["role"] == user.role.value

        assert isinstance(result["access_token"], str)
        assert isinstance(result["refresh_token"], str)
        assert result["access_token"]
        assert result["refresh_token"]

        mock_create_audit_log.assert_called_once_with(
            action=AuditAction.LOGIN,
            entity_type="User",
            entity_id=user.id,
            description=f"User '{user.email}' logged in",
        )

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_access_token_contains_user_id_and_role_claims(
        self,
        mock_create_audit_log,
        user,
    ):
        result = authenticate_user(
            email=user.email,
            password="supersecret",
        )

        decoded = decode_token(result["access_token"])

        assert decoded["sub"] == str(user.id)
        assert decoded["role"] == user.role.value

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_refresh_token_contains_user_id(
        self,
        mock_create_audit_log,
        user,
    ):
        result = authenticate_user(
            email=user.email,
            password="supersecret",
        )

        decoded = decode_token(result["refresh_token"])

        assert decoded["sub"] == str(user.id)

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_access_token_expires_in_eight_hours(
        self,
        mock_create_audit_log,
        user,
    ):
        result = authenticate_user(
            email=user.email,
            password="supersecret",
        )

        decoded = decode_token(result["access_token"])

        lifetime = decoded["exp"] - decoded["iat"]

        assert lifetime == int(timedelta(hours=8).total_seconds())

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_refresh_token_expires_in_thirty_days(
        self,
        mock_create_audit_log,
        user,
    ):
        result = authenticate_user(
            email=user.email,
            password="supersecret",
        )

        decoded = decode_token(result["refresh_token"])

        lifetime = decoded["exp"] - decoded["iat"]

        assert lifetime == int(timedelta(days=30).total_seconds())

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_updates_last_login_at(
        self,
        mock_create_audit_log,
        user,
        db,
    ):
        assert user.last_login_at is None

        authenticate_user(
            email=user.email,
            password="supersecret",
        )

        db.session.refresh(user)

        assert user.last_login_at is not None

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_authentication_commits_login_audit_log(
        self,
        mock_create_audit_log,
        user,
        db,
    ):
        authenticate_user(
            email=user.email,
            password="supersecret",
        )

        mock_create_audit_log.assert_called_once()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_email_lookup_is_normalized_during_authentication(
        self,
        mock_create_audit_log,
        user,
    ):
        result = authenticate_user(
            email=f"  {user.email.upper()}  ",
            password="supersecret",
        )

        assert result["user_id"] == user.id
        assert result["role"] == user.role.value

        mock_create_audit_log.assert_called_once()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_rejects_wrong_password(
        self,
        mock_create_audit_log,
        user,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid email or password",
        ):
            authenticate_user(
                email=user.email,
                password="wrongpassword",
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_rejects_nonexistent_email(
        self,
        mock_create_audit_log,
    ):
        with pytest.raises(
            ValidationError,
            match="Invalid email or password",
        ):
            authenticate_user(
                email="doesnotexist@test.com",
                password="supersecret",
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_rejects_deactivated_user(
        self,
        mock_create_audit_log,
        user,
        db,
    ):
        user.is_active = False
        db.session.commit()

        with pytest.raises(
            ValidationError,
            match="This account has been deactivated",
        ):
            authenticate_user(
                email=user.email,
                password="supersecret",
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_does_not_authenticate_user_with_wrong_password_even_if_active(
        self,
        mock_create_audit_log,
        user,
    ):
        assert user.is_active is True

        with pytest.raises(
            ValidationError,
            match="Invalid email or password",
        ):
            authenticate_user(
                email=user.email,
                password="incorrect-password",
            )

        mock_create_audit_log.assert_not_called()

    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_login_audit_contains_correct_user(
        self,
        mock_create_audit_log,
        user,
    ):
        authenticate_user(
            email=user.email,
            password="supersecret",
        )

        call_kwargs = mock_create_audit_log.call_args.kwargs

        assert call_kwargs["action"] == AuditAction.LOGIN
        assert call_kwargs["entity_type"] == "User"
        assert call_kwargs["entity_id"] == user.id
        assert call_kwargs["description"] == (
            f"User '{user.email}' logged in"
        )


# ============================================================================
# ROLE-SPECIFIC REGISTRATION
# ============================================================================

class TestRegisterUserRoles:
    @pytest.mark.parametrize(
        "role",
        list(Role),
    )
    @patch(
        "app.core.auth.user.services.user_service.create_audit_log"
    )
    def test_registers_all_supported_roles(
        self,
        mock_create_audit_log,
        clinic,
        role,
    ):
        result = register_user(
            email=f"{role.value}@test.com",
            password="supersecret",
            role=role,
            clinic_id=clinic.id,
        )

        assert result.role == role
        assert result.email == f"{role.value}@test.com"

        mock_create_audit_log.assert_called_once()

        call_kwargs = mock_create_audit_log.call_args.kwargs

        assert call_kwargs["description"] == (
            f"User registered: {result.email} ({role.value})"
        )