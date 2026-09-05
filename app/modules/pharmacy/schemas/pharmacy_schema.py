from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.pharmacy_enums import DispenseStatus, DrugCategory


# ============================================================================
# SHARED HELPERS
# ============================================================================


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    value = value.strip()

    return value or None


# ============================================================================
# DRUG SCHEMAS
# ============================================================================


class DrugCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    clinic_id: int | None = Field(
        default=None,
        gt=0,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    generic_name: str | None = Field(
        default=None,
        max_length=150,
    )

    category: DrugCategory | None = Field(
        default=None,
    )

    rxnorm_code: str | None = Field(
        default=None,
        max_length=20,
    )

    barcode: str | None = Field(
        default=None,
        max_length=80,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
    )

    dosage_form: str | None = Field(
        default=None,
        max_length=50,
    )

    strength: str | None = Field(
        default=None,
        max_length=50,
    )

    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    is_controlled: bool = Field(
        default=False,
    )

    @field_validator(
        "generic_name",
        "rxnorm_code",
        "barcode",
        "manufacturer",
        "dosage_form",
        "strength",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)


class DrugUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    generic_name: str | None = Field(
        default=None,
        max_length=150,
    )

    category: DrugCategory | None = Field(
        default=None,
    )

    rxnorm_code: str | None = Field(
        default=None,
        max_length=20,
    )

    barcode: str | None = Field(
        default=None,
        max_length=80,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
    )

    dosage_form: str | None = Field(
        default=None,
        max_length=50,
    )

    strength: str | None = Field(
        default=None,
        max_length=50,
    )

    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    is_controlled: bool | None = Field(
        default=None,
    )

    @field_validator(
        "generic_name",
        "rxnorm_code",
        "barcode",
        "manufacturer",
        "dosage_form",
        "strength",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)


class DrugResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    clinic_id: int | None
    name: str
    generic_name: str | None
    category: DrugCategory
    rxnorm_code: str | None
    barcode: str | None
    manufacturer: str | None
    dosage_form: str | None
    strength: str | None
    unit_price: Decimal | None
    is_controlled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DrugFilterSchema(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
    )

    include_inactive: bool = Field(
        default=False,
    )


# ============================================================================
# DRUG BATCH SCHEMAS
# ============================================================================


class DrugBatchCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    drug_id: int = Field(
        ...,
        gt=0,
    )

    batch_number: str = Field(
        ...,
        min_length=1,
        max_length=80,
    )

    quantity_on_hand: int = Field(
        ...,
        ge=0,
    )

    expiry_date: date

    reorder_level: int = Field(
        default=20,
        ge=0,
    )

    supplier_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator(
        "batch_number",
        mode="before",
    )
    @classmethod
    def normalize_batch_number(cls, value):
        return _normalize_text(value)


class DrugBatchResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    clinic_id: int
    drug_id: int
    supplier_id: int | None
    batch_number: str
    quantity_on_hand: int
    reorder_level: int
    expiry_date: date
    received_at: datetime
    created_at: datetime
    updated_at: datetime


class DrugBatchFilterSchema(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
    )

    include_expired: bool = Field(
        default=True,
    )


class ExpiringDrugBatchQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
    )

    days: int = Field(
        default=30,
        ge=0,
    )


class StockSummaryResponseSchema(BaseModel):
    clinic_id: int
    drug_id: int
    drug_name: str
    quantity_on_hand: int
    batch_count: int


# ============================================================================
# DISPENSING SCHEMAS
# ============================================================================


class DispenseItemInputSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    prescription_item_id: int = Field(
        ...,
        gt=0,
    )

    quantity: int = Field(
        ...,
        gt=0,
    )


class DispenseRecordCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    prescription_id: int = Field(
        ...,
        gt=0,
    )

    dispensed_by_id: int = Field(
        ...,
        gt=0,
    )

    items: list[DispenseItemInputSchema] = Field(
        ...,
        min_length=1,
    )

    notes: str | None = Field(
        default=None,
    )

    @field_validator(
        "notes",
        mode="before",
    )
    @classmethod
    def normalize_notes(cls, value):
        return _normalize_text(value)

    def to_service_items(self) -> list[dict]:
        return [
            item.model_dump()
            for item in self.items
        ]


class DispenseRecordCancelSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )


class DispenseItemResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    dispense_record_id: int
    batch_id: int
    prescription_item_id: int | None
    quantity_dispensed: int


class DispenseRecordResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    prescription_id: int
    dispensed_by_id: int
    status: DispenseStatus
    notes: str | None
    dispensed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[DispenseItemResponseSchema]