"""Dashboard profile — services the user provides and consumes."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.lawyer import LawyerContractResponse, LawyerResponse
from app.schemas.service import GroupServiceType, IndividualServiceType, ServiceKind
from app.schemas.user import UserResponse


class ServiceProvidingItem(BaseModel):
    """A service this user offers to others (e.g. lawyer)."""

    kind: ServiceKind = ServiceKind.INDIVIDUAL
    service_type: IndividualServiceType | GroupServiceType
    lawyer: LawyerResponse | None = None
    # Future: ambulance_unit, police_unit, etc.


class LawyerUsageSummary(BaseModel):
    lawyer_id: UUID
    lawyer_user_id: UUID
    firm_name: str | None = None
    bar_number: str | None = None
    active_contracts: int = 0
    total_contracts: int = 0


class ServiceUsingItem(BaseModel):
    """A service this user consumes (subscriptions / contracts)."""

    kind: ServiceKind = ServiceKind.INDIVIDUAL
    service_type: IndividualServiceType | GroupServiceType
    lawyer: LawyerUsageSummary | None = None
    contracts: list[LawyerContractResponse] = Field(default_factory=list)
    # Future: group incident subscriptions


class UserProfileDashboard(BaseModel):
    """Logged-in user dashboard: identity + providing + using."""

    user: UserResponse
    services_providing: list[ServiceProvidingItem] = Field(default_factory=list)
    services_using: list[ServiceUsingItem] = Field(default_factory=list)
