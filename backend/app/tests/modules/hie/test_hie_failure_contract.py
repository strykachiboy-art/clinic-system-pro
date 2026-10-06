from __future__ import annotations

import pytest

from app.core.enums.hie_enums import HIEFailureClass
from app.modules.hie.providers.exceptions import (
    HIEFailClosedError,
    HIEProviderHTTPError,
)
from app.modules.hie.services import hie_service


@pytest.mark.parametrize(
    "response",
    [
        {
            "status_code": 200,
            "external_reference": "HIE-200",
        },
        {
            "status_code": 201,
            "external_reference": "HIE-201",
            "patient": {"id": "P-1"},
        },
        {
            "status_code": 200,
            "records": [],
        },
    ],
)
def test_validate_provider_response_accepts_success_contract(
    response,
):
    assert (
        hie_service._validate_provider_response(
            response
        )
        == response
    )


@pytest.mark.parametrize(
    "response",
    [
        [],
        "invalid",
        200,
        None,
    ],
)
def test_validate_provider_response_rejects_malformed_response(
    response,
):
    with pytest.raises(
        HIEFailClosedError,
        match="response must be an object",
    ):
        hie_service._validate_provider_response(
            response
        )


def test_validate_provider_response_rejects_empty_response():
    with pytest.raises(
        HIEFailClosedError,
        match="response was empty",
    ):
        hie_service._validate_provider_response({})


def test_validate_provider_response_rejects_missing_payload():
    with pytest.raises(
        HIEFailClosedError,
        match="provider response payload is missing",
    ):
        hie_service._validate_provider_response(
            {
                "status_code": 200,
            }
        )


@pytest.mark.parametrize(
    "response",
    [
        {
            "status_code": 201,
            "external_reference": "",
        },
        {
            "status_code": 201,
            "external_reference": "   ",
        },
    ],
)
def test_validate_provider_response_rejects_invalid_external_reference(
    response,
):
    with pytest.raises(
        HIEFailClosedError,
        match="external_reference is invalid",
    ):
        hie_service._validate_provider_response(
            response
        )


@pytest.mark.parametrize(
    "status_code",
    [
        400,
        401,
        403,
        404,
        409,
        422,
    ],
)
def test_validate_provider_response_maps_user_action_http_status(
    status_code,
):
    with pytest.raises(
        HIEProviderHTTPError,
    ) as exc_info:
        hie_service._validate_provider_response(
            {
                "status_code": status_code,
                "external_reference": "HIE-HTTP",
            }
        )

    assert exc_info.value.status_code == status_code
    assert (
        exc_info.value.failure_class
        is HIEFailureClass.USER_ACTION_REQUIRED
    )


@pytest.mark.parametrize(
    "status_code",
    [
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    ],
)
def test_validate_provider_response_maps_retryable_http_status(
    status_code,
):
    with pytest.raises(
        HIEProviderHTTPError,
    ) as exc_info:
        hie_service._validate_provider_response(
            {
                "status_code": status_code,
                "external_reference": "HIE-HTTP",
            }
        )

    assert exc_info.value.status_code == status_code
    assert (
        exc_info.value.failure_class
        is HIEFailureClass.RETRYABLE
    )


@pytest.mark.parametrize(
    "status_code",
    [
        99,
        600,
    ],
)
def test_validate_provider_response_rejects_invalid_status_code(
    status_code,
):
    with pytest.raises(
        HIEFailClosedError,
        match="status_code is invalid",
    ):
        hie_service._validate_provider_response(
            {
                "status_code": status_code,
                "external_reference": "HIE-INVALID",
            }
        )
