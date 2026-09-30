from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ClinicContextSelectSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    clinic_id: StrictInt = Field(
        ...,
        gt=0,
    )
