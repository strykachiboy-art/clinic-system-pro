from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


ALLOWED_INTEGRATION_PROVIDERS = {
    "paystack",
    "flutterwave",
    "stripe",
    "email",
    "sms",
}


class IntegrationConfigBaseSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    provider: str = Field(
        min_length=2,
        max_length=50,
    )

    configuration: dict[str, Any] = Field(
        default_factory=dict,
    )

    is_enabled: bool = False

    @field_validator("provider")
    @classmethod
    def validate_provider(
        cls,
        value: str,
    ) -> str:
        value = value.lower()

        if value not in ALLOWED_INTEGRATION_PROVIDERS:
            raise ValueError(
                "Unsupported integration provider"
            )

        return value

    @field_validator("configuration")
    @classmethod
    def validate_configuration(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(
                "Configuration must be an object"
            )

        return value


class IntegrationConfigCreateSchema(
    IntegrationConfigBaseSchema
):
    credentials: dict[str, Any] = Field(
        min_length=1,
    )

    @field_validator("credentials")
    @classmethod
    def validate_credentials(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(
                "Credentials must be an object"
            )

        if not value:
            raise ValueError(
                "Credentials cannot be empty"
            )

        return value


class IntegrationConfigUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    configuration: dict[str, Any] | None = None

    is_enabled: bool | None = None

    credentials: dict[str, Any] | None = None

    @field_validator("configuration")
    @classmethod
    def validate_configuration(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if value is None:
            return value

        if not isinstance(value, dict):
            raise ValueError(
                "Configuration must be an object"
            )

        return value

    @field_validator("credentials")
    @classmethod
    def validate_credentials(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if value is None:
            return value

        if not isinstance(value, dict):
            raise ValueError(
                "Credentials must be an object"
            )

        if not value:
            raise ValueError(
                "Credentials cannot be empty"
            )

        return value


class IntegrationConfigStatusSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    is_enabled: bool


class IntegrationConfigResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int
    provider: str
    is_enabled: bool

    configuration: dict[str, Any]

    credentials_version: int
    last_rotated_at: Any | None

    created_at: Any
    updated_at: Any


class IntegrationConfigListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    include_disabled: bool = False

    provider: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
    )

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.lower()

        if value not in ALLOWED_INTEGRATION_PROVIDERS:
            raise ValueError(
                "Unsupported integration provider"
            )

        return value