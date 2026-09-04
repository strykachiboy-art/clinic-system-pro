from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.reports_enums import ReportFormat, ReportType


class ReportFiltersSchema(BaseModel):
    date_from: Optional[date] = Field(
        default=None,
        description="Start date for the report data range",
    )

    date_to: Optional[date] = Field(
        default=None,
        description="End date for the report data range",
    )

    active_only: bool = Field(
        default=True,
        description=(
            "Whether inactive records should be excluded "
            "where the report type supports this filter"
        ),
    )

    @field_validator("date_to")
    @classmethod
    def validate_date_range(
        cls,
        value: Optional[date],
        info,
    ):
        if value is None:
            return value

        date_from = info.data.get("date_from")

        if date_from is not None and value < date_from:
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return value

    model_config = ConfigDict(from_attributes=True)


class ReportGenerateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic the report belongs to",
    )

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

    model_config = ConfigDict(from_attributes=True)


class ReportQuerySchema(BaseModel):
    clinic_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    report_type: Optional[ReportType] = Field(
        default=None,
    )

    report_format: Optional[ReportFormat] = Field(
        default=None,
    )

    date_from: Optional[date] = Field(
        default=None,
    )

    date_to: Optional[date] = Field(
        default=None,
    )

    generated_by_id: Optional[int] = Field(
        default=None,
        gt=0,
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

    @field_validator("date_to")
    @classmethod
    def validate_date_range(
        cls,
        value: Optional[date],
        info,
    ):
        if value is None:
            return value

        date_from = info.data.get("date_from")

        if date_from is not None and value < date_from:
            raise ValueError(
                "date_to must be greater than or equal to date_from"
            )

        return value

    model_config = ConfigDict(from_attributes=True)


class GeneratedReportResponseSchema(BaseModel):
    id: int
    clinic_id: Optional[int]
    generated_by_id: Optional[int]
    report_type: ReportType
    report_format: ReportFormat
    filters: Optional[dict]
    file_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedReportListResponseSchema(BaseModel):
    items: list[GeneratedReportResponseSchema]
    total: int
    page: int
    per_page: int

    model_config = ConfigDict(from_attributes=True)