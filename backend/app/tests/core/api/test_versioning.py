from __future__ import annotations

import pytest

from app.core.api.versioning import (
    APIVersionNotSupportedError,
    SUPPORTED_API_VERSIONS,
    validate_api_version,
)


def test_v1_is_supported():
    assert "v1" in SUPPORTED_API_VERSIONS
    assert validate_api_version("v1") == "v1"


@pytest.mark.parametrize(
    "value",
    [
        "V1",
        " v1",
        "v1 ",
        " V1 ",
    ],
)
def test_supported_version_is_normalized(value):
    assert validate_api_version(value) == "v1"


@pytest.mark.parametrize(
    "value",
    [
        "v0",
        "v2",
        "v3",
        "v99",
        "",
        "patients",
        "api",
        "version1",
    ],
)
def test_unsupported_version_raises(value):
    with pytest.raises(APIVersionNotSupportedError) as exc_info:
        validate_api_version(value)

    error = exc_info.value

    assert error.status_code == 404
    assert error.code == "api_version_not_supported"
    assert error.version == value.strip().lower()


def test_unsupported_version_error_message():
    with pytest.raises(APIVersionNotSupportedError) as exc_info:
        validate_api_version("v2")

    assert str(exc_info.value) == (
        "API version 'v2' is not supported."
    )