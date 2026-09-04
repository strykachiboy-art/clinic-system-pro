from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DrugInteractionCheckSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic",
    )

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the patient, if tied to one",
    )

    drug_names: list[str] = Field(
        ...,
        min_length=2,
        description="Drug names to check against each other",
    )

    @field_validator("drug_names")
    @classmethod
    def validate_drug_names(cls, value: list[str]) -> list[str]:
        cleaned = [
            drug.strip()
            for drug in value
            if isinstance(drug, str) and drug.strip()
        ]

        if len(cleaned) < 2:
            raise ValueError(
                "At least two valid drug names are required"
            )

        return cleaned

    model_config = ConfigDict(from_attributes=True)


class TriageAssistantSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic",
    )

    patient_id: int = Field(
        ...,
        gt=0,
        description="ID of the patient being triaged",
    )

    symptoms: str = Field(
        ...,
        min_length=1,
        description="Free-text description of presenting symptoms",
    )

    vitals: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional recent vitals snapshot, "
            "e.g. {'temp_c': 38.5}"
        ),
    )

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Symptoms are required")

        return value

    model_config = ConfigDict(from_attributes=True)


class LabResultInterpreterSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic",
    )

    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the patient, if tied to one",
    )

    lab_order_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the source LabOrder, if any",
    )

    result_data: dict[str, Any] = Field(
        ...,
        description=(
            "Raw lab result values to interpret, "
            "e.g. {'WBC': 11.2, 'unit': '10^9/L'}"
        ),
    )

    @field_validator("result_data")
    @classmethod
    def validate_result_data(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError("Result data is required")

        return value

    model_config = ConfigDict(from_attributes=True)