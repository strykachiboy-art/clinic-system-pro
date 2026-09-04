from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.clinic_enums import (
    ClinicStatus,
    ClinicType,
)


# ============================================================
# CLINIC CREATE
# ============================================================

class ClinicCreateSchema(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Name of the clinic",
    )

    clinic_type: ClinicType = Field(
        default=ClinicType.GENERAL,
        description="Type of clinic",
    )

    parent_clinic_id: Optional[int] = Field(
        None,
        description="ID of the parent clinic when creating a branch",
    )

    is_headquarters: bool = Field(
        default=False,
        description="Whether this clinic is a headquarters",
    )

    address: Optional[str] = Field(
        None,
        max_length=255,
        description="Clinic address",
    )

    city: Optional[str] = Field(
        None,
        max_length=100,
        description="Clinic city",
    )

    country: Optional[str] = Field(
        None,
        max_length=100,
        description="Clinic country",
    )

    phone: Optional[str] = Field(
        None,
        max_length=30,
        description="Clinic phone number",
    )

    email: Optional[str] = Field(
        None,
        max_length=120,
        description="Clinic email address",
    )

    timezone: str = Field(
        default="UTC",
        min_length=1,
        max_length=50,
        description="Clinic timezone",
    )

    opening_time: Optional[time] = Field(
        None,
        description="Clinic opening time",
    )

    closing_time: Optional[time] = Field(
        None,
        description="Clinic closing time",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# CLINIC BRANCH CREATE
# ============================================================

class ClinicBranchCreateSchema(BaseModel):
    """
    Schema used when creating a branch through:

        POST /api/clinics/<clinic_id>/branches

    The parent clinic is determined by the URL and therefore
    should not be supplied in the request body.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Name of the branch",
    )

    clinic_type: ClinicType = Field(
        default=ClinicType.GENERAL,
        description="Type of clinic branch",
    )

    address: Optional[str] = Field(
        None,
        max_length=255,
        description="Branch address",
    )

    city: Optional[str] = Field(
        None,
        max_length=100,
        description="Branch city",
    )

    country: Optional[str] = Field(
        None,
        max_length=100,
        description="Branch country",
    )

    phone: Optional[str] = Field(
        None,
        max_length=30,
        description="Branch phone number",
    )

    email: Optional[str] = Field(
        None,
        max_length=120,
        description="Branch email address",
    )

    timezone: str = Field(
        default="UTC",
        min_length=1,
        max_length=50,
        description="Branch timezone",
    )

    opening_time: Optional[time] = Field(
        None,
        description="Branch opening time",
    )

    closing_time: Optional[time] = Field(
        None,
        description="Branch closing time",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# CLINIC UPDATE
# ============================================================

class ClinicUpdateSchema(BaseModel):
    """
    Updates general clinic profile information.

    Branch relationships and headquarters configuration are
    intentionally managed through ClinicBranchConfigurationSchema.
    Clinic status, AI credits, and API tokens are also managed
    through dedicated endpoints.
    """

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=150,
        description="Updated clinic name",
    )

    clinic_type: Optional[ClinicType] = Field(
        None,
        description="Updated clinic type",
    )

    address: Optional[str] = Field(
        None,
        max_length=255,
        description="Updated clinic address",
    )

    city: Optional[str] = Field(
        None,
        max_length=100,
        description="Updated clinic city",
    )

    country: Optional[str] = Field(
        None,
        max_length=100,
        description="Updated clinic country",
    )

    phone: Optional[str] = Field(
        None,
        max_length=30,
        description="Updated clinic phone number",
    )

    email: Optional[str] = Field(
        None,
        max_length=120,
        description="Updated clinic email address",
    )

    timezone: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Updated clinic timezone",
    )

    opening_time: Optional[time] = Field(
        None,
        description="Updated clinic opening time",
    )

    closing_time: Optional[time] = Field(
        None,
        description="Updated clinic closing time",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# CLINIC BRANCH CONFIGURATION
# ============================================================

class ClinicBranchConfigurationSchema(BaseModel):
    """
    Updates a clinic's branch/headquarters configuration.

    parent_clinic_id:
        - integer -> attach clinic to another parent
        - null -> detach clinic from its current parent
        - omitted -> leave parent unchanged

    is_headquarters:
        - true -> make clinic a headquarters
        - false -> make clinic a non-headquarters
        - omitted -> leave value unchanged

    `exclude_unset=True` should be used by the route so the
    service can distinguish omitted values from explicit nulls.
    """

    parent_clinic_id: Optional[int] = Field(
        None,
        description=(
            "Parent clinic ID. Set to null to detach the clinic "
            "from its current parent."
        ),
    )

    is_headquarters: Optional[bool] = Field(
        None,
        description="Whether this clinic is a headquarters",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# CLINIC STATUS
# ============================================================

class ClinicStatusUpdateSchema(BaseModel):
    status: ClinicStatus = Field(
        ...,
        description="New clinic status",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# CLINIC AI CREDITS
# ============================================================

class ClinicAICreditsUpdateSchema(BaseModel):

    amount: int = Field(
        ...,
        gt=0,
        description="Number of AI credits to add",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )