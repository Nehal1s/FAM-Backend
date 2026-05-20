"""Universal service subscription handlers."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lawyer, LawyerContract, User

logger = structlog.get_logger(__name__)


class ServiceSubscriptionHandler(ABC):
    """Base class for service-specific subscription logic."""

    @abstractmethod
    async def validate_service_exists(
        self, session: AsyncSession, service_id: uuid.UUID
    ) -> bool:
        """Check if the service provider exists and is active."""
        pass

    @abstractmethod
    async def create_subscription(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a subscription and return subscription details."""
        pass

    @abstractmethod
    def get_service_type(self) -> str:
        """Return the service type identifier."""
        pass


class LawyerSubscriptionHandler(ServiceSubscriptionHandler):
    """Handler for lawyer service subscriptions."""

    def get_service_type(self) -> str:
        return "lawyer"

    async def validate_service_exists(
        self, session: AsyncSession, service_id: uuid.UUID
    ) -> bool:
        lawyer = await session.get(Lawyer, service_id)
        if lawyer is None or lawyer.deleted_at is not None:
            return False
        return lawyer.status == "active"

    async def create_subscription(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        title = kwargs.get("title", "Lawyer Engagement")
        description = kwargs.get("description")

        contract = LawyerContract(
            id=uuid.uuid4(),
            lawyer_id=service_id,
            client_user_id=user_id,
            status="active",
            title=title,
            description=description,
        )
        session.add(contract)
        await session.flush()

        return {
            "subscription_id": contract.id,
            "service_type": "lawyer",
            "service_id": service_id,
            "status": contract.status,
            "created_at": contract.created_at,
        }


_HANDLERS: dict[str, ServiceSubscriptionHandler] = {
    "lawyer": LawyerSubscriptionHandler(),
}


def get_subscription_handler(service_type: str) -> ServiceSubscriptionHandler | None:
    """Get the handler for a service type."""
    return _HANDLERS.get(service_type)


async def subscribe_user_to_service(
    session: AsyncSession,
    user: User,
    service_type: str,
    service_id: uuid.UUID,
    **kwargs: Any,
) -> dict[str, Any]:
    """Universal subscription handler."""
    handler = get_subscription_handler(service_type)
    if handler is None:
        raise ValueError(f"Unknown service type: {service_type}")

    if not await handler.validate_service_exists(session, service_id):
        raise ValueError(f"Service provider not found or inactive")

    result = await handler.create_subscription(session, user.id, service_id, **kwargs)
    logger.info(
        "user_subscribed_to_service",
        user_id=str(user.id),
        service_type=service_type,
        service_id=str(service_id),
    )
    return result
