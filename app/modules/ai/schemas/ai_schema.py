from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DrugInteractionCheckSchema(BaseModel):
    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    drug_names: list[str] = Field(
        ...,
        min_length=2,
    )

    @field_validator("drug_names")
    @classmethod
    def validate_drug_names(
        cls,
        value: list[str],
    ) -> list[str]:
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

    model_config = ConfigDict(
        from_attributes=True,
    )


class TriageAssistantSchema(BaseModel):
    patient_id: int = Field(
        ...,
        gt=0,
    )

    symptoms: str = Field(
        ...,
        min_length=1,
    )

    vitals: Optional[dict[str, Any]] = Field(
        default=None,
    )

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Symptoms are required"
            )

        return value

    model_config = ConfigDict(
        from_attributes=True,
    )


class LabResultInterpreterSchema(BaseModel):
    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    lab_order_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    result_data: dict[str, Any] = Field(
        ...,
    )

    @field_validator("result_data")
    @classmethod
    def validate_result_data(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError(
                "Result data is required"
            )

        return value

    model_config = ConfigDict(
        from_attributes=True,
    )