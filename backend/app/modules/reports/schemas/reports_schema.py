from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)

from app.core.enums.reports_enums import (
    ReportFormat,
    ReportType,
)


# ============================================================================
# Pagination
# ============================================================================

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


class PaginationSchema(BaseModel):
    """
    Shared pagination request contract for report listing.
    """

    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="1-based page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description=(
            f"Number of records per page "
            f"(maximum {MAX_PER_PAGE})"
        ),
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class PaginationResponseSchema(BaseModel):
    """
    Shared pagination response contract.
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
# Report filters
# ============================================================================


class ReportFiltersSchema(BaseModel):
    """
    Filters applied while generating a report.
    """

    date_from: Optional[date] = Field(
        default=None,
        description="Start date for the report data range",
    )

    date_to: Optional[date] = Field(
        default=None,
        description="End date for the report data range",
    )

    active_only: StrictBool = Field(
        default=True,
        description=(
            "Whether inactive records should be excluded "
            "where the report type supports this filter"
        ),
    )

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return self

    model_config = ConfigDict(
        extra="forbid",
    )


# ============================================================================
# Report generation
# ============================================================================


class ReportGenerateSchema(BaseModel):
    """
    Request schema for generating a report.

    Clinic and requester identity must come from the authenticated
    route/service context and are intentionally excluded here.
    """

    report_type: ReportType = Field(
        ...,
        description="Type of report to generate",
    )

    report_format: ReportFormat = Field(
        default=ReportFormat.CSV,
        description="Output format for the generated report",
    )

    filters: Optional[ReportFiltersSchema] = Field(
        default=None,
        description="Filters applied when generating the report",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


# ============================================================================
# Report query
# ============================================================================


class ReportQuerySchema(PaginationSchema):
    """
    Query parameters for generated-report listing.

    Clinic scope is resolved from authentication and therefore must
    not be supplied by non-admin clients through this schema.
    """

    report_type: Optional[ReportType] = Field(
        default=None,
        description="Filter by report type",
    )

    report_format: Optional[ReportFormat] = Field(
        default=None,
        description="Filter by report format",
    )

    date_from: Optional[date] = Field(
        default=None,
        description="Filter reports created on/after this date",
    )

    date_to: Optional[date] = Field(
        default=None,
        description="Filter reports created up to this date",
    )

    generated_by_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Filter by report generator staff ID",
    )

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return self


# ============================================================================
# Generated report response
# ============================================================================


class GeneratedReportResponseSchema(BaseModel):
    """
    Serialized generated-report response.
    """

    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    generated_by_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    report_type: ReportType

    report_format: ReportFormat

    filters: Optional[dict] = None

    file_url: Optional[str] = None

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Generated report list response
# ============================================================================


class GeneratedReportListResponseSchema(
    PaginationResponseSchema
):
    """
    Paginated generated-report response.
    """

    items: list[
        GeneratedReportResponseSchema
    ] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )