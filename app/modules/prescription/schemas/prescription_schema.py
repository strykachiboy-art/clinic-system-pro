from __future__ import annotations

from datetime import datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.prescription_enums import DrugInteractionSeverity


# =====================================================================
# Pagination
# =====================================================================

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


class PaginationSchema(BaseModel):
    """
    Shared pagination request schema.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="1-based page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description=f"Number of records per page (maximum {MAX_PER_PAGE})",
    )


class PaginationResponseSchema(BaseModel):
    """
    Shared pagination response schema.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    items: list
    total: int = Field(
        ge=0,
    )
    page: int = Field(
        ge=1,
    )
    per_page: int = Field(
        ge=1,
        le=MAX_PER_PAGE,
    )


# =====================================================================
# Prescription Item
# =====================================================================

class PrescriptionItemSchema(BaseModel):
    """
    Request schema for an individual prescription item.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    drug_id: int = Field(
        ...,
        gt=0,
        description="ID of the prescribed drug",
    )

    dosage: str | None = Field(
        default=None,
        max_length=255,
        description="Medication dosage",
    )

    frequency: str | None = Field(
        default=None,
        max_length=255,
        description="How frequently the medication should be taken",
    )

    duration: str | None = Field(
        default=None,
        max_length=255,
        description="Duration of the medication",
    )

    quantity: int | None = Field(
        default=None,
        gt=0,
        description="Quantity of medication to dispense",
    )

    instructions: str | None = Field(
        default=None,
        max_length=1000,
        description="Additional instructions for the patient",
    )

    @field_validator(
        "dosage",
        "frequency",
        "duration",
        "instructions",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None


# =====================================================================
# Prescription Creation
# =====================================================================

class PrescriptionCreateSchema(BaseModel):
    """
    Request schema for creating a prescription.

    Clinic and prescriber identity are intentionally excluded from
    client-controlled payloads. The route must derive those values
    from the authenticated user/session context.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    patient_id: int = Field(
        ...,
        gt=0,
        description="Patient receiving the prescription",
    )

    consultation_id: int | None = Field(
        default=None,
        gt=0,
        description="Optional consultation associated with the prescription",
    )

    items: list[PrescriptionItemSchema] = Field(
        ...,
        min_length=1,
        description="Prescription medication items",
    )

    expires_at: datetime | None = Field(
        default=None,
        description="Optional prescription expiration timestamp",
    )

    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Additional prescription notes",
    )

    @field_validator("items")
    @classmethod
    def validate_unique_drugs(cls, value):
        drug_ids = [
            item.drug_id
            for item in value
        ]

        if len(drug_ids) != len(
            set(drug_ids)
        ):
            raise ValueError(
                "A drug cannot appear more than once in a prescription"
            )

        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value):
        if value is None:
            return None

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "expires_at must include timezone information"
            )

        if value <= datetime.now(
            timezone.utc
        ):
            raise ValueError(
                "expires_at must be in the future"
            )

        return value.astimezone(
            timezone.utc
        )

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None


# =====================================================================
# Prescription Cancellation
# =====================================================================

class PrescriptionCancelSchema(BaseModel):
    """
    Request schema for cancelling a prescription.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Reason for cancelling the prescription",
    )

    @field_validator(
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_reason(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None


# =====================================================================
# Prescription List Query
# =====================================================================

class PrescriptionListQuerySchema(PaginationSchema):
    """
    Query parameters for clinic-scoped patient prescription listings.
    """

    active_only: bool = Field(
        default=False,
        description="Return only active prescriptions",
    )


# =====================================================================
# Drug Interaction Creation
# =====================================================================

class DrugInteractionCreateSchema(BaseModel):
    """
    Request schema for creating a global drug interaction.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    drug_a_id: int = Field(
        ...,
        gt=0,
        description="First drug ID",
    )

    drug_b_id: int = Field(
        ...,
        gt=0,
        description="Second drug ID",
    )

    severity: DrugInteractionSeverity = Field(
        ...,
        description="Interaction severity",
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Description of the drug interaction",
    )

    @field_validator("drug_b_id")
    @classmethod
    def validate_different_drug(
        cls,
        value,
        info,
    ):
        drug_a_id = info.data.get(
            "drug_a_id"
        )

        if (
            drug_a_id is not None
            and value == drug_a_id
        ):
            raise ValueError(
                "A drug cannot interact with itself"
            )

        return value

    @field_validator(
        "description",
        mode="before",
    )
    @classmethod
    def normalize_description(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None


# =====================================================================
# Drug Interaction Check
# =====================================================================

class DrugInteractionCheckSchema(BaseModel):
    """
    Request schema for checking a list of drugs for known interactions.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    drug_ids: list[int] = Field(
        ...,
        min_length=2,
        description="Drug IDs to check for interactions",
    )

    @field_validator("drug_ids")
    @classmethod
    def validate_drug_ids(cls, value):
        if any(
            (
                not isinstance(drug_id, int)
                or isinstance(drug_id, bool)
                or drug_id <= 0
            )
            for drug_id in value
        ):
            raise ValueError(
                "All drug IDs must be greater than zero"
            )

        if len(value) != len(
            set(value)
        ):
            raise ValueError(
                "Duplicate drug IDs are not allowed"
            )

        return value