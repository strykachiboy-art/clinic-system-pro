from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClinicSettingsBaseSchema(BaseModel):
    """
    Base schema for clinic application settings.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    language: str = Field(
        default="en",
        min_length=2,
        max_length=20,
    )

    date_format: str = Field(
        default="YYYY-MM-DD",
        min_length=2,
        max_length=30,
    )

    time_format: str = Field(
        default="24h",
        min_length=2,
        max_length=10,
    )

    notification_preferences: dict[str, Any] = Field(
        default_factory=dict,
    )

    feature_flags: dict[str, bool] = Field(
        default_factory=dict,
    )

    operational_preferences: dict[str, Any] = Field(
        default_factory=dict,
    )

    security_preferences: dict[str, Any] = Field(
        default_factory=dict,
    )

    system_preferences: dict[str, Any] = Field(
        default_factory=dict,
    )

    is_enabled: bool = True

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        value = value.lower()

        if not value.replace("-", "").isalpha():
            raise ValueError(
                "Language must contain only letters or a language-region format"
            )

        return value

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        allowed = {"12h", "24h"}

        if value not in allowed:
            raise ValueError(
                f"Time format must be one of: {', '.join(sorted(allowed))}"
            )

        return value

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        allowed = {
            "YYYY-MM-DD",
            "DD-MM-YYYY",
            "MM-DD-YYYY",
            "DD/MM/YYYY",
            "MM/DD/YYYY",
        }

        if value not in allowed:
            raise ValueError(
                f"Date format must be one of: {', '.join(sorted(allowed))}"
            )

        return value

    @field_validator(
        "notification_preferences",
        "feature_flags",
        "operational_preferences",
        "security_preferences",
        "system_preferences",
    )
    @classmethod
    def validate_preferences_are_dicts(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Preferences must be an object")

        return value


class ClinicSettingsCreateSchema(ClinicSettingsBaseSchema):
    """
    Schema for creating clinic settings.

    clinic_id is intentionally excluded because clinic ownership
    must come from the authenticated request context.
    """

    pass


class ClinicSettingsUpdateSchema(BaseModel):
    """
    Schema for partial clinic settings updates.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    language: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
    )

    date_format: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
    )

    time_format: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
    )

    notification_preferences: dict[str, Any] | None = None

    feature_flags: dict[str, bool] | None = None

    operational_preferences: dict[str, Any] | None = None

    security_preferences: dict[str, Any] | None = None

    system_preferences: dict[str, Any] | None = None

    is_enabled: bool | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.lower()

        if not value.replace("-", "").isalpha():
            raise ValueError(
                "Language must contain only letters or a language-region format"
            )

        return value

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, value: str | None) -> str | None:
        if value is None:
            return value

        if value not in {"12h", "24h"}:
            raise ValueError("Time format must be either '12h' or '24h'")

        return value

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        if value is None:
            return value

        allowed = {
            "YYYY-MM-DD",
            "DD-MM-YYYY",
            "MM-DD-YYYY",
            "DD/MM/YYYY",
            "MM/DD/YYYY",
        }

        if value not in allowed:
            raise ValueError(
                f"Date format must be one of: {', '.join(sorted(allowed))}"
            )

        return value


class ClinicSettingsResponseSchema(BaseModel):
    """
    Schema returned to clients.

    version and timestamps are server-controlled.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int

    language: str
    date_format: str
    time_format: str

    notification_preferences: dict[str, Any]
    feature_flags: dict[str, bool]
    operational_preferences: dict[str, Any]
    security_preferences: dict[str, Any]
    system_preferences: dict[str, Any]

    is_enabled: bool
    version: int

    created_at: Any
    updated_at: Any


class ClinicSettingsListQuerySchema(BaseModel):
    """
    Query parameters for settings retrieval.

    Settings are one-per-clinic, but keeping a query schema gives
    us a consistent pattern for future settings collection endpoints.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    include_disabled: bool = False