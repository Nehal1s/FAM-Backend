from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.service import IndividualServiceType


class LawyerLegalInfo(BaseModel):
    bar_number: str = Field(..., max_length=64)
    license_jurisdiction: str = Field(..., max_length=128)
    firm_name: str | None = Field(default=None, max_length=255)
    specializations: str | None = Field(
        default=None,
        max_length=500,
        description="Comma-separated areas of practice",
    )
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int | None = Field(default=None, ge=0, le=80)


class LawyerPromoteRequest(LawyerLegalInfo):
    user_id: UUID


class LawyerUpdateRequest(BaseModel):
    bar_number: str | None = Field(default=None, max_length=64)
    license_jurisdiction: str | None = Field(default=None, max_length=128)
    firm_name: str | None = Field(default=None, max_length=255)
    specializations: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    status: str | None = Field(default=None, pattern="^(active|suspended|inactive)$")


class LawyerArtifact(BaseModel):
    """Attached to UserResponse when the user is a promoted lawyer."""

    model_config = ConfigDict(from_attributes=True)

    lawyer_id: UUID
    service_type: IndividualServiceType = IndividualServiceType.LAWYER
    status: str
    bar_number: str
    license_jurisdiction: str
    firm_name: str | None = None
    specializations: str | None = None


class LawyerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    service_type: IndividualServiceType = IndividualServiceType.LAWYER
    status: str
    bar_number: str
    license_jurisdiction: str
    firm_name: str | None = None
    specializations: str | None = None
    bio: str | None = None
    years_experience: int | None = None
    average_rating: float | None = None
    contract_count: int = 0
    promoted_at: datetime
    created_at: datetime
    updated_at: datetime


class LawyerContractCreateRequest(BaseModel):
    client_user_id: UUID
    title: str = Field(..., max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class LawyerContractUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|active|completed|cancelled)$")
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    review_text: str | None = Field(default=None, max_length=2000)


class LawyerContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lawyer_id: UUID
    client_user_id: UUID
    status: str
    title: str
    description: str | None = None
    rating: int | None = None
    review_text: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
