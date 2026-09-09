from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


MAX_DRUG_NAME_LENGTH = 255
MAX_SYMPTOMS_LENGTH = 5000
MAX_RESULT_DATA_FIELDS = 100


class DrugInteractionCheckSchema(BaseModel):
    patient_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    drug_names: list[str] = Field(
        ...,
        min_length=2,
        max_length=50,
    )

    @field_validator("drug_names")
    @classmethod
    def validate_drug_names(
        cls,
        value: list[str],
    ) -> list[str]:
        cleaned: list[str] = []

        for drug in value:
            if not isinstance(drug, str):
                raise ValueError(
                    "Each drug name must be a string"
                )

            drug = drug.strip()

            if not drug:
                continue

            if len(drug) > MAX_DRUG_NAME_LENGTH:
                raise ValueError(
                    f"Drug name cannot exceed "
                    f"{MAX_DRUG_NAME_LENGTH} characters"
                )

            cleaned.append(drug)

        if len(cleaned) < 2:
            raise ValueError(
                "At least two valid drug names are required"
            )

        normalized = {
            drug.casefold()
            for drug in cleaned
        }

        if len(normalized) != len(cleaned):
            raise ValueError(
                "Duplicate drug names are not allowed"
            )

        return cleaned

    model_config = ConfigDict(
        extra="forbid",
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
        max_length=MAX_SYMPTOMS_LENGTH,
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

        if len(value) > MAX_SYMPTOMS_LENGTH:
            raise ValueError(
                f"Symptoms cannot exceed "
                f"{MAX_SYMPTOMS_LENGTH} characters"
            )

        return value

    @field_validator("vitals")
    @classmethod
    def validate_vitals(
        cls,
        value: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if value is None:
            return None

        if not isinstance(value, dict):
            raise ValueError(
                "Vitals must be provided as an object"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
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
        if not isinstance(value, dict) or not value:
            raise ValueError(
                "Result data is required"
            )

        if len(value) > MAX_RESULT_DATA_FIELDS:
            raise ValueError(
                f"Result data cannot contain more than "
                f"{MAX_RESULT_DATA_FIELDS} fields"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )