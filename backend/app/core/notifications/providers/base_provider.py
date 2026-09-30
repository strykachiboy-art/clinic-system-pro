from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.exceptions import ValidationError


class NotificationProviderBase(ABC):
    def __init__(
        self,
        *,
        credentials: dict[str, Any] | None = None,
    ):
        self.credentials = credentials or {}

    @abstractmethod
    def send(
        self,
        *,
        notification,
    ) -> bool:
        raise NotImplementedError

    def _require_credential(
        self,
        key: str,
    ) -> str:
        value = self.credentials.get(key)

        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"Missing required provider credential: {key}"
            )

        return value.strip()