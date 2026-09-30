from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


ALLOWED_DEVICE_PLATFORMS = {
    "android",
    "ios",
    "web",
}


class UserDeviceCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    device_token: str = Field(
        min_length=10,
        max_length=500,
    )

    device_name: str | None = Field(
        default=None,
        max_length=100,
    )

    platform: str = Field(
        min_length=2,
        max_length=20,
    )

    @field_validator("device_token")
    @classmethod
    def validate_device_token(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Device token is required"
            )

        return value

    @field_validator("device_name")
    @classmethod
    def normalize_device_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("platform")
    @classmethod
    def validate_platform(
        cls,
        value: str,
    ) -> str:
        value = value.lower()

        if value not in ALLOWED_DEVICE_PLATFORMS:
            raise ValueError(
                "Unsupported device platform"
            )

        return value


class UserDeviceUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    device_name: str | None = Field(
        default=None,
        max_length=100,
    )

    platform: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
    )

    is_active: bool | None = None

    @field_validator("device_name")
    @classmethod
    def normalize_device_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("platform")
    @classmethod
    def validate_platform(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.lower()

        if value not in ALLOWED_DEVICE_PLATFORMS:
            raise ValueError(
                "Unsupported device platform"
            )

        return value


class UserDeviceResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(
        gt=0,
    )

    user_id: int = Field(
        gt=0,
    )

    device_token: str = Field(
        min_length=1,
        max_length=500,
    )

    device_name: str | None = Field(
        default=None,
        max_length=100,
    )

    platform: str = Field(
        min_length=2,
        max_length=20,
    )

    is_active: bool

    last_seen_at: datetime | None

    created_at: datetime

    updated_at: datetime

    @field_validator("platform")
    @classmethod
    def normalize_platform(
        cls,
        value: str,
    ) -> str:
        value = value.lower()

        if value not in ALLOWED_DEVICE_PLATFORMS:
            raise ValueError(
                "Unsupported device platform"
            )

        return value