from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from redis.exceptions import ConnectionError, TimeoutError

from app.core.exceptions import ValidationError
from app.core.auth.user.services import token_service


class TestRevokedTokenKey:
    def test_builds_correct_redis_key(self):
        result = token_service._revoked_token_key("abc-123")

        assert result == "auth:revoked:abc-123"


class TestTokenRemainingSeconds:
    def test_uses_supplied_payload(self):
        future_exp = (
            datetime.now(timezone.utc) + timedelta(seconds=120)
        ).timestamp()

        result = token_service._token_remaining_seconds(
            {"exp": future_exp}
        )

        assert 118 <= result <= 120

    def test_uses_current_jwt_when_payload_is_none(self):
        future_exp = (
            datetime.now(timezone.utc) + timedelta(seconds=120)
        ).timestamp()

        with patch(
            "app.core.auth.user.services.token_service.get_jwt",
            return_value={"exp": future_exp},
        ) as mock_get_jwt:
            result = token_service._token_remaining_seconds()

        mock_get_jwt.assert_called_once()
        assert 118 <= result <= 120

    def test_rejects_missing_exp(self):
        with pytest.raises(
            ValidationError,
            match="JWT expiration is missing",
        ):
            token_service._token_remaining_seconds({})

    def test_returns_at_least_one_second_for_expired_token(self):
        expired_exp = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        ).timestamp()

        result = token_service._token_remaining_seconds(
            {"exp": expired_exp}
        )

        assert result == 1

    def test_returns_at_least_one_second_when_exp_is_now(self):
        current_exp = datetime.now(timezone.utc).timestamp()

        result = token_service._token_remaining_seconds(
            {"exp": current_exp}
        )

        assert result == 1


class TestRevokeToken:
    def test_rejects_when_redis_is_unavailable(self):
        with patch.object(
            token_service.extensions,
            "redis_client",
            None,
        ):
            with pytest.raises(
                ValidationError,
                match="Redis is not available for token revocation",
            ):
                token_service.revoke_token(
                    {"jti": "abc-123", "exp": 9999999999}
                )

    def test_rejects_missing_jti(self):
        redis_client = Mock()

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(
                ValidationError,
                match="JWT ID is missing",
            ):
                token_service.revoke_token(
                    {"exp": 9999999999}
                )

        redis_client.setex.assert_not_called()

    def test_rejects_empty_jti(self):
        redis_client = Mock()

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(
                ValidationError,
                match="JWT ID is missing",
            ):
                token_service.revoke_token(
                    {"jti": "", "exp": 9999999999}
                )

        redis_client.setex.assert_not_called()

    def test_stores_revoked_token_in_redis(self):
        redis_client = Mock()

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ), patch(
            "app.core.auth.user.services.token_service._token_remaining_seconds",
            return_value=300,
        ) as mock_remaining:
            token_service.revoke_token(
                {"jti": "abc-123", "exp": 9999999999}
            )

        mock_remaining.assert_called_once_with(
            {"jti": "abc-123", "exp": 9999999999}
        )
        redis_client.setex.assert_called_once_with(
            "auth:revoked:abc-123",
            300,
            "1",
        )

    def test_handles_redis_connection_error(self):
        redis_client = Mock()
        redis_client.setex.side_effect = ConnectionError(
            "Redis connection failed"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(
                ValidationError,
                match="Unable to access token revocation storage",
            ):
                token_service.revoke_token(
                    {"jti": "abc-123", "exp": 9999999999}
                )

    def test_handles_redis_timeout_error(self):
        redis_client = Mock()
        redis_client.setex.side_effect = TimeoutError(
            "Redis operation timed out"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(
                ValidationError,
                match="Unable to access token revocation storage",
            ):
                token_service.revoke_token(
                    {"jti": "abc-123", "exp": 9999999999}
                )

    def test_does_not_swallow_unexpected_errors(self):
        redis_client = Mock()
        redis_client.setex.side_effect = RuntimeError(
            "Unexpected programming error"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(RuntimeError, match="Unexpected"):
                token_service.revoke_token(
                    {"jti": "abc-123", "exp": 9999999999}
                )


class TestRevokeCurrentToken:
    def test_revokes_current_jwt(self):
        jwt_payload = {
            "jti": "current-token",
            "exp": 9999999999,
        }

        with patch(
            "app.core.auth.user.services.token_service.get_jwt",
            return_value=jwt_payload,
        ) as mock_get_jwt, patch(
            "app.core.auth.user.services.token_service.revoke_token"
        ) as mock_revoke:
            token_service.revoke_current_token()

        mock_get_jwt.assert_called_once()
        mock_revoke.assert_called_once_with(jwt_payload)


class TestIsTokenRevoked:
    def test_fails_closed_when_redis_is_unavailable(self):
        with patch.object(
            token_service.extensions,
            "redis_client",
            None,
        ):
            result = token_service.is_token_revoked(
                {"jti": "abc-123"}
            )

        assert result is True

    def test_fails_closed_when_jti_is_missing(self):
        redis_client = Mock()

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked({})

        assert result is True
        redis_client.exists.assert_not_called()

    def test_fails_closed_when_jti_is_empty(self):
        redis_client = Mock()

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked(
                {"jti": ""}
            )

        assert result is True
        redis_client.exists.assert_not_called()

    def test_returns_true_when_token_is_revoked(self):
        redis_client = Mock()
        redis_client.exists.return_value = 1

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked(
                {"jti": "abc-123"}
            )

        assert result is True
        redis_client.exists.assert_called_once_with(
            "auth:revoked:abc-123"
        )

    def test_returns_false_when_token_is_not_revoked(self):
        redis_client = Mock()
        redis_client.exists.return_value = 0

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked(
                {"jti": "abc-123"}
            )

        assert result is False
        redis_client.exists.assert_called_once_with(
            "auth:revoked:abc-123"
        )

    def test_fails_closed_on_redis_connection_error(self):
        redis_client = Mock()
        redis_client.exists.side_effect = ConnectionError(
            "Redis connection failed"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked(
                {"jti": "abc-123"}
            )

        assert result is True

    def test_fails_closed_on_redis_timeout_error(self):
        redis_client = Mock()
        redis_client.exists.side_effect = TimeoutError(
            "Redis operation timed out"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            result = token_service.is_token_revoked(
                {"jti": "abc-123"}
            )

        assert result is True

    def test_does_not_swallow_unexpected_errors(self):
        redis_client = Mock()
        redis_client.exists.side_effect = RuntimeError(
            "Unexpected programming error"
        )

        with patch.object(
            token_service.extensions,
            "redis_client",
            redis_client,
        ):
            with pytest.raises(
                RuntimeError,
                match="Unexpected",
            ):
                token_service.is_token_revoked(
                    {"jti": "abc-123"}
                )