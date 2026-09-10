from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.core.enums.lab_enums import (
    LabResultFlag,
    SampleType,
)


# ============================================================================
# PAGINATION
# ============================================================================

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


class LabPaginationSchema(BaseModel):
    """
    Shared pagination contract for laboratory collection endpoints.
    """

    page: int = Field(
        DEFAULT_PAGE,
        ge=1,
    )

    per_page: int = Field(
        DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class LabPaginationResponseSchema(BaseModel):
    """
    Standard pagination metadata returned by laboratory
    collection endpoints.
    """

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
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


# ============================================================================
# LAB TEST CATALOG
# ============================================================================


class LabTestCreateSchema(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    loinc_code: Optional[str] = Field(
        None,
        max_length=20,
    )

    code: Optional[str] = Field(
        None,
        max_length=50,
    )

    sample_type: SampleType = Field(
        default=SampleType.BLOOD,
    )

    reference_range: Optional[str] = Field(
        None,
        max_length=150,
    )

    unit: Optional[str] = Field(
        None,
        max_length=30,
    )

    price: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
    )

    critical_low: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    critical_high: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    is_active: bool = Field(
        default=True,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    @model_validator(mode="after")
    def validate_critical_range(self):
        if (
            self.critical_low is not None
            and self.critical_high is not None
            and self.critical_low >= self.critical_high
        ):
            raise ValueError(
                "critical_low must be less than critical_high"
            )

        return self


class LabTestUpdateSchema(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=150,
    )

    loinc_code: Optional[str] = Field(
        None,
        max_length=20,
    )

    code: Optional[str] = Field(
        None,
        max_length=50,
    )

    sample_type: Optional[SampleType] = None

    reference_range: Optional[str] = Field(
        None,
        max_length=150,
    )

    unit: Optional[str] = Field(
        None,
        max_length=30,
    )

    price: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
    )

    critical_low: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    critical_high: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    is_active: Optional[bool] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    @model_validator(mode="after")
    def validate_critical_range(self):
        """
        Validate the range when both thresholds are supplied.

        During partial updates, the service merges a single supplied
        threshold with the existing persisted threshold and validates
        the final range.
        """
        if (
            self.critical_low is not None
            and self.critical_high is not None
            and self.critical_low >= self.critical_high
        ):
            raise ValueError(
                "critical_low must be less than critical_high"
            )

        return self


class LabTestListQuerySchema(LabPaginationSchema):
    """
    Query schema for laboratory test catalog listing.

    clinic_id is intentionally excluded because the route/service
    derives clinic context from authenticated identity.
    """

    active_only: bool = Field(
        default=True,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class LabTestListResponseSchema(
    LabPaginationResponseSchema
):
    """
    Paginated laboratory test response.
    """

    items: list[LabTestCreateSchema] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# LAB ORDERS
# ============================================================================


class LabOrderCreateSchema(BaseModel):

    patient_id: int = Field(
        ...,
        gt=0,
    )

    test_ids: list[int] = Field(
        ...,
        min_length=1,
    )

    consultation_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    @model_validator(mode="after")
    def validate_test_ids(self):
        if any(
            not isinstance(test_id, int)
            or isinstance(test_id, bool)
            or test_id <= 0
            for test_id in self.test_ids
        ):
            raise ValueError(
                "All test_ids must be positive integers"
            )

        if len(self.test_ids) != len(set(self.test_ids)):
            raise ValueError(
                "Duplicate test_ids are not allowed"
            )

        return self


# ============================================================================
# LAB ORDER LIST QUERY
# ============================================================================


class LabOrderListQuerySchema(LabPaginationSchema):
    """
    Query schema for tenant-scoped patient laboratory orders.
    """

    patient_id: int = Field(
        ...,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class LabOrderListResponseSchema(
    LabPaginationResponseSchema
):
    """
    Paginated laboratory order response.
    """

    items: list[dict] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# SAMPLE COLLECTION
# ============================================================================


class LabSampleCollectionSchema(BaseModel):
    """
    Collects a laboratory sample.
    """

    scanned_qr_code: Optional[str] = Field(
        None,
        min_length=1,
        max_length=150,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# LABORATORY PROCESSING
# ============================================================================


class LabProcessingSchema(BaseModel):
    """
    Marks a laboratory order as processed.

    processed_by_id and processed_at are controlled by the service.
    """

    equipment_reference_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=150,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# LABORATORY VERIFICATION
# ============================================================================


class LabVerificationSchema(BaseModel):
    """
    Verifies a laboratory order/result.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# EQUIPMENT
# ============================================================================


class LabEquipmentLinkSchema(BaseModel):
    equipment_reference_id: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# CANCELLATION
# ============================================================================


class LabOrderCancelSchema(BaseModel):
    reason: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# RESULTS
# ============================================================================


class LabResultCreateSchema(BaseModel):
    """
    Creates or records a result for a laboratory order item.
    """

    result_value: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    flag: Optional[LabResultFlag] = None

    result_notes: Optional[str] = Field(
        None,
        max_length=1000,
    )

    result_file_url: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )