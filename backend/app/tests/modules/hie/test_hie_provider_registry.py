from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.exceptions import ValidationError
from app.modules.hie.providers import registry


def test_register_provider_normalizes_name_and_resolves_provider():
    provider = object()
    factory = Mock(return_value=provider)

    registry.register_provider(
        "  TEST-HIE-PROVIDER  ",
        factory,
    )

    try:
        assert registry.is_provider_registered(
            "test-hie-provider"
        )

        result = registry.get_provider(
            "TEST-HIE-PROVIDER",
            endpoint="https://hie.test.example",
        )

        assert result is provider
        factory.assert_called_once_with(
            "https://hie.test.example"
        )
    finally:
        registry.unregister_provider(
            "test-hie-provider"
        )


def test_register_provider_replaces_existing_factory():
    first_provider = object()
    second_provider = object()

    first_factory = Mock(return_value=first_provider)
    second_factory = Mock(return_value=second_provider)

    registry.register_provider(
        "TEST-HIE-PROVIDER",
        first_factory,
    )

    try:
        registry.register_provider(
            "test-hie-provider",
            second_factory,
        )

        result = registry.get_provider(
            "test-hie-provider"
        )

        assert result is second_provider
        first_factory.assert_not_called()
        second_factory.assert_called_once_with(None)
    finally:
        registry.unregister_provider(
            "test-hie-provider"
        )


def test_register_provider_requires_name():
    with pytest.raises(
        ValidationError,
        match="HIE provider name is required",
    ):
        registry.register_provider(
            "",
            Mock(),
        )


def test_register_provider_rejects_whitespace_only_name():
    with pytest.raises(
        ValidationError,
        match="HIE provider name is required",
    ):
        registry.register_provider(
            "   ",
            Mock(),
        )


def test_register_provider_requires_callable_factory():
    with pytest.raises(
        ValidationError,
        match="HIE provider factory must be callable",
    ):
        registry.register_provider(
            "test-provider",
            object(),
        )


def test_get_provider_requires_name():
    with pytest.raises(
        ValidationError,
        match="HIE provider is required",
    ):
        registry.get_provider("")


def test_get_provider_rejects_whitespace_only_name():
    with pytest.raises(
        ValidationError,
        match="HIE provider is required",
    ):
        registry.get_provider("   ")


def test_get_provider_rejects_unregistered_provider():
    registry.unregister_provider(
        "missing-provider"
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider: missing-provider",
    ):
        registry.get_provider(
            "missing-provider"
        )


def test_get_provider_normalizes_name_before_lookup():
    provider = object()
    factory = Mock(return_value=provider)

    registry.register_provider(
        "test-hie-provider",
        factory,
    )

    try:
        result = registry.get_provider(
            "  TEST-HIE-PROVIDER  ",
        )

        assert result is provider
        factory.assert_called_once_with(None)
    finally:
        registry.unregister_provider(
            "test-hie-provider"
        )


def test_get_provider_passes_endpoint_to_factory():
    provider = object()
    factory = Mock(return_value=provider)

    registry.register_provider(
        "test-hie-provider",
        factory,
    )

    try:
        endpoint = "https://hie.example.test"

        result = registry.get_provider(
            "test-hie-provider",
            endpoint=endpoint,
        )

        assert result is provider
        factory.assert_called_once_with(
            endpoint
        )
    finally:
        registry.unregister_provider(
            "test-hie-provider"
        )


def test_unregister_provider_removes_provider():
    registry.register_provider(
        "test-hie-provider",
        Mock(return_value=object()),
    )

    assert registry.is_provider_registered(
        "test-hie-provider"
    )

    registry.unregister_provider(
        "test-hie-provider"
    )

    assert not registry.is_provider_registered(
        "test-hie-provider"
    )


def test_unregister_provider_is_idempotent():
    registry.unregister_provider(
        "missing-provider"
    )

    registry.unregister_provider(
        "missing-provider"
    )

    assert not registry.is_provider_registered(
        "missing-provider"
    )


def test_is_provider_registered_normalizes_name():
    registry.register_provider(
        "test-hie-provider",
        Mock(return_value=object()),
    )

    try:
        assert registry.is_provider_registered(
            "  TEST-HIE-PROVIDER  "
        )
    finally:
        registry.unregister_provider(
            "test-hie-provider"
        )


def test_is_provider_registered_returns_false_for_unknown_provider():
    registry.unregister_provider(
        "missing-provider"
    )

    assert not registry.is_provider_registered(
        "missing-provider"
    )


def test_is_provider_registered_returns_false_for_empty_name():
    assert not registry.is_provider_registered("")


def test_is_provider_registered_returns_false_for_whitespace_name():
    assert not registry.is_provider_registered("   ")