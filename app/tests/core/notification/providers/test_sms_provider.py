from unittest.mock import patch

import pytest

from app.core.exceptions import ValidationError
from app.core.notifications.providers.SMS_provider import (
    SMSNotificationProvider,
)


class TestSMSNotificationProvider:

    def test_send_success(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            message="Your appointment is tomorrow.",
        )

        provider = SMSNotificationProvider()

        with patch.object(
            provider,
            "_deliver_sms",
            return_value=True,
        ) as deliver:
            result = provider.send(
                notification=notification,
                phone="+2348012345678",
            )

        assert result is True

        deliver.assert_called_once_with(
            phone="+2348012345678",
            message="Your appointment is tomorrow.",
        )

    def test_send_rejects_missing_notification(self):
        provider = SMSNotificationProvider()

        with pytest.raises(
            ValidationError,
            match="Notification is required",
        ):
            provider.send(
                notification=None,
                phone="+2348012345678",
            )

    def test_send_rejects_invalid_phone(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
        )

        provider = SMSNotificationProvider()

        with pytest.raises(
            ValidationError,
            match="phone number is invalid",
        ):
            provider.send(
                notification=notification,
                phone="",
            )

    def test_send_rejects_non_string_phone(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
        )

        provider = SMSNotificationProvider()

        with pytest.raises(
            ValidationError,
            match="phone number is invalid",
        ):
            provider.send(
                notification=notification,
                phone=None,
            )

    def test_send_rejects_oversized_phone(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
        )

        provider = SMSNotificationProvider()

        with pytest.raises(
            ValidationError,
            match="phone number is invalid",
        ):
            provider.send(
                notification=notification,
                phone="1" * 31,
            )

    def test_send_rejects_empty_message(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            message="   ",
        )

        provider = SMSNotificationProvider()

        with pytest.raises(
            ValidationError,
            match="Notification message is required",
        ):
            provider.send(
                notification=notification,
                phone="+2348012345678",
            )

    def test_send_normalizes_phone_and_message(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            message="  Test SMS  ",
        )

        provider = SMSNotificationProvider()

        with patch.object(
            provider,
            "_deliver_sms",
            return_value=True,
        ) as deliver:
            result = provider.send(
                notification=notification,
                phone="  +2348012345678  ",
            )

        assert result is True

        deliver.assert_called_once_with(
            phone="+2348012345678",
            message="Test SMS",
        )

    def test_sms_transport_boundary_is_not_configured(
        self,
        make_notification,
        clinic,
        user,
    ):
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            message="Test SMS",
        )

        provider = SMSNotificationProvider()

        with pytest.raises(
            NotImplementedError,
            match="SMS transport is not configured",
        ):
            provider.send(
                notification=notification,
                phone="+2348012345678",
            )