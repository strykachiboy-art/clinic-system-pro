from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums.inventory_enums import (
    InventoryCategory,
    InventoryTransferStatus,
    StockMovementDirection,
    StockMovementType,
)


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


# ============================================================================
# HELPERS
# ============================================================================

def _normalize_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    value = value.strip()

    return value or None


# ============================================================================
# PAGINATION
# ============================================================================

class InventoryPaginationSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
    )


class InventoryPaginationResponseSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

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


# ============================================================================
# INVENTORY ITEMS
# ============================================================================

class InventoryItemCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    category: InventoryCategory = Field(
        default=InventoryCategory.MEDICAL_SUPPLY
    )

    sku: str | None = Field(
        default=None,
        max_length=80,
    )

    barcode: str | None = Field(
        default=None,
        max_length=80,
    )

    unit: str | None = Field(
        default=None,
        max_length=30,
    )

    initial_quantity: int = Field(
        default=0,
        ge=0,
    )

    reorder_level: int = Field(
        default=10,
        ge=0,
    )

    @field_validator(
        "name",
        "sku",
        "barcode",
        "unit",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value,
    ):
        if not value:
            raise ValueError(
                "Item name cannot be empty"
            )

        return value


class InventoryItemUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str | None = Field(
        default=None,
        max_length=150,
    )

    category: InventoryCategory | None = None

    sku: str | None = Field(
        default=None,
        max_length=80,
    )

    barcode: str | None = Field(
        default=None,
        max_length=80,
    )

    unit: str | None = Field(
        default=None,
        max_length=30,
    )

    reorder_level: int | None = Field(
        default=None,
        ge=0,
    )

    @field_validator(
        "name",
        "sku",
        "barcode",
        "unit",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value,
    ):
        if value is not None and not value:
            raise ValueError(
                "Item name cannot be empty"
            )

        return value


class InventoryItemResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    clinic_id: int
    name: str
    category: InventoryCategory
    sku: str | None
    barcode: str | None
    unit: str | None
    quantity_on_hand: int
    reorder_level: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InventoryItemFilterSchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    category: InventoryCategory | None = None

    low_stock_only: bool = False

    include_inactive: bool = False


class InventoryItemListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[InventoryItemResponseSchema]


# ============================================================================
# SUPPLIERS
# ============================================================================

class InventorySupplierCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    contact_person: str | None = Field(
        default=None,
        max_length=120,
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    email: EmailStr | None = None

    address: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator(
        "name",
        "contact_person",
        "phone",
        "address",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value,
    ):
        if not value:
            raise ValueError(
                "Supplier name cannot be empty"
            )

        return value


class InventorySupplierUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str | None = Field(
        default=None,
        max_length=150,
    )

    contact_person: str | None = Field(
        default=None,
        max_length=120,
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    email: EmailStr | None = None

    address: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator(
        "name",
        "contact_person",
        "phone",
        "address",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value,
    ):
        if value is not None and not value:
            raise ValueError(
                "Supplier name cannot be empty"
            )

        return value


class InventorySupplierResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    clinic_id: int | None
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InventorySupplierFilterSchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    include_inactive: bool = False


class InventorySupplierListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[InventorySupplierResponseSchema]


# ============================================================================
# INVENTORY BATCHES
# ============================================================================

class InventoryBatchCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    item_id: int = Field(
        ...,
        gt=0,
    )

    batch_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    supplier_id: int | None = Field(
        default=None,
        gt=0,
    )

    unit_cost: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
    )

    expiry_date: date | None = None

    @field_validator(
        "batch_number",
        mode="before",
    )
    @classmethod
    def normalize_batch_number(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(
        cls,
        value,
    ):
        if not value:
            raise ValueError(
                "Batch number cannot be empty"
            )

        return value

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(
        cls,
        value,
    ):
        if (
            value is not None
            and value < date.today()
        ):
            raise ValueError(
                "Expiry date cannot be in the past"
            )

        return value


class InventoryBatchUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    batch_number: str | None = Field(
        default=None,
        max_length=100,
    )

    supplier_id: int | None = Field(
        default=None,
        gt=0,
    )

    unit_cost: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
    )

    expiry_date: date | None = None

    @field_validator(
        "batch_number",
        mode="before",
    )
    @classmethod
    def normalize_batch_number(
        cls,
        value,
    ):
        return _normalize_text(value)

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(
        cls,
        value,
    ):
        if value is not None and not value:
            raise ValueError(
                "Batch number cannot be empty"
            )

        return value

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(
        cls,
        value,
    ):
        if (
            value is not None
            and value < date.today()
        ):
            raise ValueError(
                "Expiry date cannot be in the past"
            )

        return value


class InventoryBatchResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    item_id: int
    supplier_id: int | None
    batch_number: str
    quantity_on_hand: int
    unit_cost: Decimal | None
    expiry_date: date | None
    received_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InventoryBatchFilterSchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    include_inactive: bool = False


class InventoryBatchListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[InventoryBatchResponseSchema]


# ============================================================================
# EXPIRING BATCHES
# ============================================================================

class ExpiringInventoryBatchQuerySchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    days: int = Field(
        default=30,
        ge=0,
    )


class ExpiringInventoryBatchListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[InventoryBatchResponseSchema]


# ============================================================================
# STOCK MOVEMENTS
# ============================================================================

class StockMovementCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    item_id: int = Field(
        ...,
        gt=0,
    )

    batch_id: int | None = Field(
        default=None,
        gt=0,
    )

    movement_type: StockMovementType

    # Positive for normal movements.
    # ADJUSTMENT may be positive or negative.
    quantity: int

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    reference_type: str | None = Field(
        default=None,
        max_length=50,
    )

    reference_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator(
        "reason",
        "reference_type",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value,
    ):
        return _normalize_text(value)

    @model_validator(mode="after")
    def validate_quantity(self):
        if (
            self.movement_type
            == StockMovementType.ADJUSTMENT
        ):
            if self.quantity == 0:
                raise ValueError(
                    "Adjustment quantity cannot be zero"
                )

        elif self.quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero"
            )

        return self


class StockMovementResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    item_id: int
    batch_id: int | None
    movement_type: StockMovementType
    direction: StockMovementDirection
    quantity: int
    reason: str | None
    performed_by_id: int
    reference_type: str | None
    reference_id: int | None
    created_at: datetime


class StockMovementFilterSchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )


class StockMovementListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[StockMovementResponseSchema]


# ============================================================================
# INVENTORY TRANSFERS
# ============================================================================

class InventoryTransferCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    item_id: int = Field(
        ...,
        gt=0,
    )

    batch_id: int | None = Field(
        default=None,
        gt=0,
    )

    destination_clinic_id: int = Field(
        ...,
        gt=0,
    )

    quantity: int = Field(
        ...,
        gt=0,
    )

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator(
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_reason(
        cls,
        value,
    ):
        return _normalize_text(value)


class InventoryTransferApproveSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )


class InventoryTransferCompleteSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )


class InventoryTransferCancelSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator(
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_reason(
        cls,
        value,
    ):
        return _normalize_text(value)


class InventoryTransferResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    item_id: int
    batch_id: int | None
    source_clinic_id: int
    destination_clinic_id: int
    quantity: int
    status: InventoryTransferStatus
    reason: str | None
    requested_by_id: int
    approved_by_id: int | None
    requested_at: datetime
    approved_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InventoryTransferFilterSchema(
    InventoryPaginationSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: InventoryTransferStatus | None = None


class InventoryTransferListResponseSchema(
    InventoryPaginationResponseSchema
):
    model_config = ConfigDict(
        extra="forbid"
    )

    items: list[InventoryTransferResponseSchema]