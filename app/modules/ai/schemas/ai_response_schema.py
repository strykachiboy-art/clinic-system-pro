from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.ai_enums import AIRiskLevel


class AIResponseBaseSchema(BaseModel):
    """
    Common response fields returned by AI features.
    """

    summary: Optional[str] = Field(
        default=None,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class DrugInteractionResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for drug interaction checks.
    """

    interactions: Optional[list[dict[str, Any]]] = Field(
        default=None,
    )

    recommendations: Optional[list[str]] = Field(
        default=None,
    )


class TriageAssistantResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for triage assistance.
    """

    risk_score: AIRiskLevel

    recommendation: Optional[str] = Field(
        default=None,
    )


class LabResultInterpreterResponseSchema(AIResponseBaseSchema):
    """
    Expected AI response for laboratory result interpretation.
    """

    interpretation: Optional[str] = Field(
        default=None,
    )

    abnormal_findings: Optional[list[str]] = Field(
        default=None,
    )

    recommendations: Optional[list[str]] = Field(
        default=None,
    )