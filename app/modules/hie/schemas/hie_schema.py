from datetime import datetime
from typing import Any, Optional

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)


class HIEIntegrationCreateSchema(BaseModel):
    provider: str = Field(
        default="malaffi",
        min_length=1,
        max_length=50,
    )

    endpoint_url: Optional[AnyHttpUrl] = Field(
        default=None,
    )

    organization_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    facility_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("Provider is required")

        return value

    @field_validator("organization_id", "facility_id")
    @classmethod
    def validate_identifiers(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Identifier cannot be empty"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIEIntegrationUpdateSchema(BaseModel):
    provider: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    status: Optional[HIEIntegrationStatus] = Field(
        default=None,
    )

    endpoint_url: Optional[AnyHttpUrl] = Field(
        default=None,
    )

    organization_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    facility_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip().lower()

        if not value:
            raise ValueError(
                "Provider cannot be empty"
            )

        return value

    @field_validator("organization_id", "facility_id")
    @classmethod
    def validate_identifiers(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Identifier cannot be empty"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIEIntegrationResponseSchema(BaseModel):
    id: int
    clinic_id: int
    provider: str
    status: HIEIntegrationStatus
    endpoint_url: Optional[AnyHttpUrl]
    organization_id: Optional[str]
    facility_id: Optional[str]
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIESubmissionCreateSchema(BaseModel):
    integration_id: int = Field(
        ...,
        gt=0,
    )

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    operation: HIEOperation = Field(
        ...,
    )

    request_data: Optional[dict[str, Any]] = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIESubmissionResponseSchema(BaseModel):
    id: int
    integration_id: int
    clinic_id: int
    patient_id: Optional[int]
    operation: HIEOperation
    status: HIESubmissionStatus
    external_reference: Optional[str]
    request_data: Optional[dict[str, Any]]
    response_data: Optional[dict[str, Any]]
    status_code: Optional[int]
    error_message: Optional[str]
    retry_count: int
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIESubmissionQuerySchema(BaseModel):
    integration_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    operation: Optional[HIEOperation] = Field(
        default=None,
    )

    status: Optional[HIESubmissionStatus] = Field(
        default=None,
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

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class HIESubmissionListResponseSchema(BaseModel):
    items: list[HIESubmissionResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )
    page: int = Field(
        ...,
        ge=1,
    )
    per_page: int = Field(
        ...,
        ge=1,
        le=100,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )