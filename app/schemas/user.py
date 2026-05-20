from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.lawyer import LawyerArtifact
from app.schemas.user_auth import UserAuthMethod


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    auth_method: UserAuthMethod
    display_name: str | None = None
    created_at: datetime
    lawyer: LawyerArtifact | None = None


class ErrorResponse(BaseModel):
    detail: str


class UserCreateRequest(BaseModel):
    email: EmailStr
    auth_method: UserAuthMethod = UserAuthMethod.STATIC_TOKEN
    display_name: str | None = Field(default=None, max_length=255)


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class UserEmailLookupResponse(BaseModel):
    """Does not expose PII beyond existence."""

    exists: bool


class UserPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    auth_method: UserAuthMethod | None = None


class ServiceSubscribeRequest(BaseModel):
    service_type: str = Field(..., description="Service type to subscribe to (e.g., 'lawyer')")
    service_id: UUID | None = Field(default=None, description="ID of the specific service provider")
    title: str | None = Field(default=None, max_length=255, description="Subscription title/engagement name")
    description: str | None = Field(default=None, max_length=4000, description="Subscription description")


class SubscriptionResponse(BaseModel):
    subscription_id: UUID
    service_type: str
    service_id: UUID
    status: str
    created_at: datetime
