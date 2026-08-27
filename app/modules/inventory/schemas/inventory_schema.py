from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.inventory_enums import InventoryCategory, StockMovementType


class InventoryItemCreateSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")

    name: str = Field(..., max_length=150)
    category: InventoryCategory = Field(default=InventoryCategory.MEDICAL_SUPPLY)
    sku: Optional[str] = Field(None, max_length=80)
    barcode: Optional[str] = Field(None, max_length=80)

    unit: Optional[str] = Field(None, max_length=30, description="e.g. 'box', 'vial', 'pcs'")
    quantity_on_hand: int = Field(0, ge=0)
    reorder_level: int = Field(10, ge=0)

    unit_cost: Optional[Decimal] = Field(None, ge=0)
    expiry_date: Optional[date] = Field(None)

    supplier_id: Optional[int] = Field(None)

    class Config:
        from_attributes = True


class InventoryItemUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    category: Optional[InventoryCategory] = Field(None)
    sku: Optional[str] = Field(None, max_length=80)
    barcode: Optional[str] = Field(None, max_length=80)

    unit: Optional[str] = Field(None, max_length=30)
    reorder_level: Optional[int] = Field(None, ge=0)

    unit_cost: Optional[Decimal] = Field(None, ge=0)
    expiry_date: Optional[date] = Field(None)

    supplier_id: Optional[int] = Field(None)
    is_active: Optional[bool] = Field(None)

    class Config:
        from_attributes = True


class StockMovementCreateSchema(BaseModel):
    movement_type: StockMovementType = Field(...)
    quantity: int = Field(..., description="Positive for additions (restock), negative for removals (usage/damaged/expired) — sign convention enforced by the service layer")
    reason: Optional[str] = Field(None, max_length=255)
    performed_by_id: Optional[int] = Field(None, description="Staff member who performed this movement")


class InventorySupplierCreateSchema(BaseModel):
    clinic_id: Optional[int] = Field(None, description="Null for a supplier shared across all branches")
    name: str = Field(..., max_length=150)
    contact_person: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)

    class Config:
        from_attributes = True


class InventorySupplierUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    contact_person: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = Field(None)

    class Config:
        from_attributes = True