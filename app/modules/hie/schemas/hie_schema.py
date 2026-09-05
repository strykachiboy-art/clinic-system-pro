from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)


class HIEIntegrationCreateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic that owns the HIE integration",
    )
    provider: str = Field(
        default="malaffi",
        min_length=1,
        max_length=50,
        description="HIE provider name",
    )
    endpoint_url: Optional[str] = Field(
        default=None,
        max_length=255,
        description="External HIE endpoint URL",
    )
    organization_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="External healthcare organization identifier",
    )
    facility_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="External healthcare facility identifier",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("Provider is required")

        return value

    model_config = ConfigDict(from_attributes=True)


class HIEIntegrationUpdateSchema(BaseModel):
    provider: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="HIE provider name",
    )
    status: Optional[HIEIntegrationStatus] = Field(
        default=None,
        description="Current HIE integration status",
    )
    endpoint_url: Optional[str] = Field(
        default=None,
        max_length=255,
        description="External HIE endpoint URL",
    )
    organization_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="External healthcare organization identifier",
    )
    facility_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="External healthcare facility identifier",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Provider cannot be empty")

        return value

    model_config = ConfigDict(from_attributes=True)


class HIEIntegrationResponseSchema(BaseModel):
    id: int
    clinic_id: int
    provider: str
    status: HIEIntegrationStatus
    endpoint_url: Optional[str]
    organization_id: Optional[str]
    facility_id: Optional[str]
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HIESubmissionCreateSchema(BaseModel):
    integration_id: int = Field(
        ...,
        gt=0,
        description="ID of the HIE integration to use",
    )
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic associated with the submission",
    )
    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the patient associated with the operation",
    )
    operation: HIEOperation = Field(
        ...,
        description="HIE operation being performed",
    )
    request_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Payload sent to the external HIE provider",
    )

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class HIESubmissionQuerySchema(BaseModel):
    clinic_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Filter by clinic",
    )
    integration_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Filter by HIE integration",
    )
    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Filter by patient",
    )
    operation: Optional[HIEOperation] = Field(
        default=None,
        description="Filter by HIE operation",
    )
    status: Optional[HIESubmissionStatus] = Field(
        default=None,
        description="Filter by submission status",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number",
    )
    per_page: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of records per page",
    )

    model_config = ConfigDict(from_attributes=True)


class HIESubmissionListResponseSchema(BaseModel):
    items: list[HIESubmissionResponseSchema]
    total: int
    page: int
    per_page: int

    model_config = ConfigDict(from_attributes=True)