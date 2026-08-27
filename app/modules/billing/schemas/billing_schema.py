from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from app.core.enums.billing_enums import PaymentMethod


class InvoiceItemSchema(BaseModel):
    description: str = Field(..., max_length=255)
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0)


class InvoiceCreateSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: int = Field(..., description="ID of the patient")
    appointment_id: Optional[int] = Field(None, description="Linked appointment, if any")

    items: list[InvoiceItemSchema] = Field(..., min_length=1, description="Line items for this invoice")

    due_date: Optional[date] = Field(None)
    is_insurance_claim: bool = Field(False)
    insurance_provider: Optional[str] = Field(None, max_length=120)

    @model_validator(mode="after")
    def provider_required_if_insurance(self):
        if self.is_insurance_claim and not self.insurance_provider:
            raise ValueError("insurance_provider is required when is_insurance_claim is true")
        return self


class PaymentRecordSchema(BaseModel):
    amount: Decimal = Field(..., gt=0)
    method: PaymentMethod = Field(...)
    reference: Optional[str] = Field(None, max_length=120, description="Gateway/transaction reference")