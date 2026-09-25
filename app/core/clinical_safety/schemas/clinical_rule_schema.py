from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)


_RULE_CODE_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9_]{2,99}$"
)


def _normalize_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    value = value.strip()

    return value or None


def _validate_timezone_aware(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "Datetime must include timezone information"
        )

    return value.astimezone(
        timezone.utc
    )


class ClinicalRuleCreateSchema(BaseModel):
    rule_code: str = Field(
        ...,
        min_length=3,
        max_length=100,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    scope: ClinicalRuleScope = Field(
        default=ClinicalRuleScope.CLINIC,
    )

    rule_type: ClinicalRuleType

    severity: ClinicalRuleSeverity

    action: ClinicalRuleAction

    conditions: dict[str, Any] = Field(
        default_factory=dict,
    )

    configuration: dict[str, Any] = Field(
        default_factory=dict,
    )

    department_code: str | None = Field(
        default=None,
        max_length=100,
    )

    priority: StrictInt = Field(
        default=100,
        ge=0,
    )

    enabled: StrictBool = Field(
        default=True,
    )

    effective_from: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ),
    )

    effective_until: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "rule_code",
        mode="before",
    )
    @classmethod
    def validate_rule_code(
        cls,
        value,
    ):
        if not isinstance(value, str):
            return value

        value = value.strip().upper()

        if not _RULE_CODE_PATTERN.fullmatch(
            value
        ):
            raise ValueError(
                "rule_code must contain only uppercase "
                "letters, numbers, and underscores and "
                "must start with a letter"
            )

        return value

    @field_validator(
        "name",
        "description",
        "department_code",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("effective_from")
    @classmethod
    def validate_effective_from(
        cls,
        value,
    ):
        return _validate_timezone_aware(value)

    @field_validator("effective_until")
    @classmethod
    def validate_effective_until(
        cls,
        value,
    ):
        return _validate_timezone_aware(value)

    @model_validator(mode="after")
    def validate_scope_and_dates(self):
        if (
            self.scope
            == ClinicalRuleScope.DEPARTMENT
            and not self.department_code
        ):
            raise ValueError(
                "department_code is required for department-scoped rules"
            )

        if (
            self.scope
            != ClinicalRuleScope.DEPARTMENT
            and self.department_code is not None
        ):
            raise ValueError(
                "department_code is only valid for department-scoped rules"
            )

        if (
            self.effective_until is not None
            and self.effective_until
            <= self.effective_from
        ):
            raise ValueError(
                "effective_until must be later than effective_from"
            )

        return self


class ClinicalRuleUpdateSchema(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    severity: ClinicalRuleSeverity | None = None

    action: ClinicalRuleAction | None = None

    conditions: dict[str, Any] | None = None

    configuration: dict[str, Any] | None = None

    department_code: str | None = Field(
        default=None,
        max_length=100,
    )

    priority: StrictInt | None = Field(
        default=None,
        ge=0,
    )

    enabled: StrictBool | None = None

    effective_from: datetime | None = None

    effective_until: datetime | None = None

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "name",
        "description",
        "department_code",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator(
        "effective_from",
        "effective_until",
    )
    @classmethod
    def validate_datetimes(
        cls,
        value,
    ):
        return _validate_timezone_aware(value)

    @model_validator(mode="after")
    def validate_effective_window(self):
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until
            <= self.effective_from
        ):
            raise ValueError(
                "effective_until must be later than effective_from"
            )

        return self


class ClinicalRuleResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    clinic_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    rule_code: str
    name: str
    description: str | None

    scope: ClinicalRuleScope
    rule_type: ClinicalRuleType
    severity: ClinicalRuleSeverity
    action: ClinicalRuleAction

    conditions: dict[str, Any]
    configuration: dict[str, Any]

    department_code: str | None

    priority: StrictInt = Field(
        ...,
        ge=0,
    )

    enabled: StrictBool
    is_hard_rule: StrictBool
    version: StrictInt = Field(
        ...,
        gt=0,
    )

    effective_from: datetime
    effective_until: datetime | None

    created_by_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    updated_by_user_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ClinicalRuleListQuerySchema(BaseModel):
    page: StrictInt = Field(
        default=1,
        ge=1,
    )

    per_page: StrictInt = Field(
        default=50,
        ge=1,
        le=500,
    )

    rule_type: ClinicalRuleType | None = None

    scope: ClinicalRuleScope | None = None

    severity: ClinicalRuleSeverity | None = None

    action: ClinicalRuleAction | None = None

    enabled: StrictBool | None = None

    department_code: str | None = Field(
        default=None,
        max_length=100,
    )

    include_global: StrictBool = True

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "department_code",
        mode="before",
    )
    @classmethod
    def normalize_department_code(
        cls,
        value,
    ):
        return _normalize_text(value)