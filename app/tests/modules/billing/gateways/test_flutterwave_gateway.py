from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests

from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)


@pytest.fixture
def flutterwave_credentials():
    return {
        "secret_key": "flw_test_secret",
        "webhook_secret": "flw_webhook_secret",
        "public_key": "flw_test_public",
    }


@pytest.fixture
def gateway(flutterwave_credentials):
    return FlutterwaveGateway(
        credentials=flutterwave_credentials,
    )


class FakeResponse:
    def __init__(
        self,
        *,
        ok=True,
        status_code=200,
        json_data=None,
        json_error=None,
    ):
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error

        return self._json_data