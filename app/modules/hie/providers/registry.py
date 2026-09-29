from __future__ import annotations

from typing import Callable, Optional

from app.core.exceptions import ValidationError
from app.modules.hie.providers.base import HIEProvider


HIEProviderFactory = Callable[
    [Optional[str]],
    HIEProvider,
]


_PROVIDER_REGISTRY: dict[
    str,
    HIEProviderFactory,
] = {}


def register_provider(
    name: str,
    factory: HIEProviderFactory,
) -> None:
    if name is None:
        raise ValidationError(
            "HIE provider name is required"
        )

    name = name.strip().lower()

    if not name:
        raise ValidationError(
            "HIE provider name is required"
        )

    if not callable(factory):
        raise ValidationError(
            "HIE provider factory must be callable"
        )

    _PROVIDER_REGISTRY[name] = factory


def unregister_provider(
    name: str,
) -> None:
    if name is None:
        return

    name = name.strip().lower()

    if not name:
        return

    _PROVIDER_REGISTRY.pop(
        name,
        None,
    )


def is_provider_registered(
    name: str,
) -> bool:
    if name is None:
        return False

    name = name.strip().lower()

    if not name:
        return False

    return name in _PROVIDER_REGISTRY


def get_provider(
    name: str,
    *,
    endpoint: Optional[str] = None,
) -> HIEProvider:
    if name is None:
        raise ValidationError(
            "HIE provider is required"
        )

    name = name.strip().lower()

    if not name:
        raise ValidationError(
            "HIE provider is required"
        )

    factory = _PROVIDER_REGISTRY.get(name)

    if factory is None:
        raise ValidationError(
            f"Unsupported HIE provider: {name}"
        )

    return factory(endpoint)