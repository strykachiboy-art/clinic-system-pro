from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests

from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)


@pytest.fixture
def paystack_credentials():
    return {
        "secret_key": "sk_test_secret",
    }


@pytest.fixture
def gateway(paystack_credentials):
    return PaystackGateway(
        credentials=paystack_credentials,
    )