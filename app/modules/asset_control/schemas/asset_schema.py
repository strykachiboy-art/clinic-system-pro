from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
    AssetOwnership,
    AssetStatus,
    MaintenanceStatus,
)


# ============================================================================
# SHARED CONFIG
# ============================================================================


class AssetSchemaBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=False,
    )


# ============================================================================
# CREATE
# ============================================================================


class AssetCreateSchema(AssetSchemaBase):
    """
    Client-supplied fields for creating an asset.

    clinic_id, status, is_active, lifecycle dates, and audit fields
    are intentionally excluded because they are server-controlled.
    """

    asset_tag: str = Field(
        ...,
        min_length=1,
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

    category: AssetCategory

    condition: AssetCondition = AssetCondition.GOOD

    ownership: AssetOwnership = AssetOwnership.CLINIC

    location: str | None = Field(
        default=None,
        max_length=255,
    )

    assigned_to_id: int | None = Field(
        default=None,
        gt=0,
    )

    serial_number: str | None = Field(
        default=None,
        max_length=150,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
    )

    model_number: str | None = Field(
        default=None,
        max_length=150,
    )

    purchase_date: date | None = None

    purchase_cost: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=14,
        decimal_places=2,
    )

    supplier: str | None = Field(
        default=None,
        max_length=255,
    )

    warranty_expiry: date | None = None

    maintenance_status: MaintenanceStatus = (
        MaintenanceStatus.NOT_REQUIRED
    )

    last_maintenance_date: date | None = None

    next_maintenance_date: date | None = None

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    @field_validator(
        "asset_tag",
        "name",
        "description",
        "location",
        "serial_number",
        "manufacturer",
        "model_number",
        "supplier",
        "notes",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator(
        "asset_tag",
        "name",
    )
    @classmethod
    def reject_blank_required_text(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError(
                "must not be blank"
            )

        value = value.strip()

        if not value:
            raise ValueError(
                "must not be blank"
            )

        return value

    @field_validator("assigned_to_id")
    @classmethod
    def validate_assigned_to_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                "assigned_to_id must be a positive integer"
            )

        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "AssetCreateSchema":
        if (
            self.warranty_expiry is not None
            and self.purchase_date is not None
            and self.warranty_expiry < self.purchase_date
        ):
            raise ValueError(
                "warranty_expiry cannot be before purchase_date"
            )

        if (
            self.last_maintenance_date is not None
            and self.next_maintenance_date is not None
            and self.next_maintenance_date
            < self.last_maintenance_date
        ):
            raise ValueError(
                "next_maintenance_date cannot be before "
                "last_maintenance_date"
            )

        return self


# ============================================================================
# UPDATE
# ============================================================================


class AssetUpdateSchema(AssetSchemaBase):
    """
    Client-supplied fields for normal asset updates.

    Lifecycle fields such as status, retirement, disposal, and
    is_active are intentionally excluded and must use dedicated
    lifecycle operations.
    """

    asset_tag: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    category: AssetCategory | None = None

    condition: AssetCondition | None = None

    ownership: AssetOwnership | None = None

    location: str | None = Field(
        default=None,
        max_length=255,
    )

    assigned_to_id: int | None = Field(
        default=None,
        gt=0,
    )

    serial_number: str | None = Field(
        default=None,
        max_length=150,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
    )

    model_number: str | None = Field(
        default=None,
        max_length=150,
    )

    purchase_date: date | None = None

    purchase_cost: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=14,
        decimal_places=2,
    )

    supplier: str | None = Field(
        default=None,
        max_length=255,
    )

    warranty_expiry: date | None = None

    maintenance_status: MaintenanceStatus | None = None

    last_maintenance_date: date | None = None

    next_maintenance_date: date | None = None

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    @field_validator(
        "asset_tag",
        "name",
        "description",
        "location",
        "serial_number",
        "manufacturer",
        "model_number",
        "supplier",
        "notes",
    )
    @classmethod
    def normalize_text_fields(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator(
        "asset_tag",
        "name",
    )
    @classmethod
    def reject_blank_required_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "must not be blank"
            )

        return value

    @field_validator("assigned_to_id")
    @classmethod
    def validate_assigned_to_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                "assigned_to_id must be a positive integer"
            )

        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "AssetUpdateSchema":
        if (
            self.warranty_expiry is not None
            and self.purchase_date is not None
            and self.warranty_expiry < self.purchase_date
        ):
            raise ValueError(
                "warranty_expiry cannot be before purchase_date"
            )

        if (
            self.last_maintenance_date is not None
            and self.next_maintenance_date is not None
            and self.next_maintenance_date
            < self.last_maintenance_date
        ):
            raise ValueError(
                "next_maintenance_date cannot be before "
                "last_maintenance_date"
            )

        return self


# ============================================================================
# RETIRE ASSET
# ============================================================================


class AssetRetireSchema(AssetSchemaBase):
    """
    Payload for retiring an asset.
    """

    retirement_date: date | None = None


# ============================================================================
# DISPOSE ASSET
# ============================================================================


class AssetDisposeSchema(AssetSchemaBase):
    """
    Payload for disposing an asset.
    """

    disposal_reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    disposal_date: date | None = None

    @field_validator("disposal_reason")
    @classmethod
    def normalize_disposal_reason(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "disposal_reason is required"
            )

        return value


# ============================================================================
# LIST / FILTER QUERY
# ============================================================================


class AssetListQuerySchema(AssetSchemaBase):
    """
    Query parameters for tenant-scoped asset listing.
    """

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    search: str | None = Field(
        default=None,
        max_length=255,
    )

    category: AssetCategory | None = None

    status: AssetStatus | None = None

    condition: AssetCondition | None = None

    ownership: AssetOwnership | None = None

    maintenance_status: MaintenanceStatus | None = None

    assigned_to_id: int | None = Field(
        default=None,
        gt=0,
    )

    is_active: bool | None = None

    @field_validator("search")
    @classmethod
    def normalize_search(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("assigned_to_id")
    @classmethod
    def validate_assigned_to_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                "assigned_to_id must be a positive integer"
            )

        return value


# ============================================================================
# RESPONSE
# ============================================================================


class AssetResponseSchema(AssetSchemaBase):
    """
    Read-only API representation of an asset.
    """

    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    asset_tag: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    description: str | None = None

    category: AssetCategory

    status: AssetStatus

    condition: AssetCondition

    ownership: AssetOwnership

    location: str | None = None

    assigned_to_id: int | None = Field(
        default=None,
        gt=0,
    )

    serial_number: str | None = None

    manufacturer: str | None = None

    model_number: str | None = None

    purchase_date: date | None = None

    purchase_cost: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=14,
        decimal_places=2,
    )

    supplier: str | None = None

    warranty_expiry: date | None = None

    maintenance_status: MaintenanceStatus

    last_maintenance_date: date | None = None

    next_maintenance_date: date | None = None

    retirement_date: date | None = None

    disposal_date: date | None = None

    disposal_reason: str | None = None

    is_active: bool

    notes: str | None = None

    created_at: datetime

    updated_at: datetime