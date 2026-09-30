from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.enums.ai_enums import AIRiskLevel


MAX_SUMMARY_LENGTH = 5000
MAX_INTERACTIONS = 100
MAX_RECOMMENDATIONS = 50
MAX_RECOMMENDATION_LENGTH = 2000
MAX_ABNORMAL_FINDINGS = 100
MAX_FINDING_LENGTH = 2000
MAX_INTERPRETATION_LENGTH = 10000


class AIResponseBaseSchema(BaseModel):
    """
    Common response fields returned by AI features.

    These represent AI-generated suggestions and must not be
    interpreted as clinician-authored clinical truth.
    """

    summary: Optional[str] = Field(
        default=None,
        max_length=MAX_SUMMARY_LENGTH,
    )

    @field_validator("summary")
    @classmethod
    def validate_summary(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                "Summary must be a string"
            )

        value = value.strip()

        if not value:
            return None

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class DrugInteractionResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for drug interaction checks.
    """

    interactions: Optional[
        list[dict[str, Any]]
    ] = Field(
        default=None,
        max_length=MAX_INTERACTIONS,
    )

    recommendations: Optional[list[str]] = Field(
        default=None,
        max_length=MAX_RECOMMENDATIONS,
    )

    @field_validator("interactions")
    @classmethod
    def validate_interactions(
        cls,
        value: Optional[list[dict[str, Any]]],
    ) -> Optional[list[dict[str, Any]]]:
        if value is None:
            return None

        for interaction in value:
            if not isinstance(interaction, dict):
                raise ValueError(
                    "Each interaction must be an object"
                )

        return value

    @field_validator("recommendations")
    @classmethod
    def validate_recommendations(
        cls,
        value: Optional[list[str]],
    ) -> Optional[list[str]]:
        if value is None:
            return None

        cleaned = []

        for recommendation in value:
            if not isinstance(recommendation, str):
                raise ValueError(
                    "Each recommendation must be a string"
                )

            recommendation = recommendation.strip()

            if not recommendation:
                raise ValueError(
                    "Recommendations cannot be empty"
                )

            if len(recommendation) > MAX_RECOMMENDATION_LENGTH:
                raise ValueError(
                    "Recommendation is too long"
                )

            cleaned.append(recommendation)

        return cleaned


class TriageAssistantResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for triage assistance.
    """

    risk_score: AIRiskLevel

    recommendation: Optional[str] = Field(
        default=None,
        max_length=MAX_RECOMMENDATION_LENGTH,
    )

    @field_validator("recommendation")
    @classmethod
    def validate_recommendation(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value


class LabResultInterpreterResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for laboratory result interpretation.
    """

    interpretation: Optional[str] = Field(
        default=None,
        max_length=MAX_INTERPRETATION_LENGTH,
    )

    abnormal_findings: Optional[list[str]] = Field(
        default=None,
        max_length=MAX_ABNORMAL_FINDINGS,
    )

    recommendations: Optional[list[str]] = Field(
        default=None,
        max_length=MAX_RECOMMENDATIONS,
    )

    @field_validator("interpretation")
    @classmethod
    def validate_interpretation(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value

    @field_validator("abnormal_findings")
    @classmethod
    def validate_abnormal_findings(
        cls,
        value: Optional[list[str]],
    ) -> Optional[list[str]]:
        if value is None:
            return None

        cleaned = []

        for finding in value:
            if not isinstance(finding, str):
                raise ValueError(
                    "Each abnormal finding must be a string"
                )

            finding = finding.strip()

            if not finding:
                raise ValueError(
                    "Abnormal findings cannot be empty"
                )

            if len(finding) > MAX_FINDING_LENGTH:
                raise ValueError(
                    "Abnormal finding is too long"
                )

            cleaned.append(finding)

        return cleaned

    @field_validator("recommendations")
    @classmethod
    def validate_recommendations(
        cls,
        value: Optional[list[str]],
    ) -> Optional[list[str]]:
        if value is None:
            return None

        cleaned = []

        for recommendation in value:
            if not isinstance(recommendation, str):
                raise ValueError(
                    "Each recommendation must be a string"
                )

            recommendation = recommendation.strip()

            if not recommendation:
                raise ValueError(
                    "Recommendations cannot be empty"
                )

            if len(recommendation) > MAX_RECOMMENDATION_LENGTH:
                raise ValueError(
                    "Recommendation is too long"
                )

            cleaned.append(recommendation)

        return cleaned