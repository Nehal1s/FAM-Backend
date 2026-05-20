"""Build aggregated user dashboard from DB."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lawyer, LawyerContract, User
from app.schemas.lawyer import LawyerContractResponse
from app.schemas.profile import (
    LawyerUsageSummary,
    ServiceProvidingItem,
    ServiceUsingItem,
    UserProfileDashboard,
)
from app.schemas.service import IndividualServiceType, ServiceKind
from app.schemas.user import UserResponse
from app.services.lawyer import build_lawyer_artifact, build_lawyer_response, get_active_lawyer_by_user


async def build_user_profile(session: AsyncSession, user_id: uuid.UUID) -> UserProfileDashboard | None:
    user = (
        await session.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if user is None:
        return None

    lawyer = await get_active_lawyer_by_user(session, user_id)
    artifact = build_lawyer_artifact(lawyer) if lawyer else None
    user_response = UserResponse.model_validate(user).model_copy(update={"lawyer": artifact})

    providing: list[ServiceProvidingItem] = []
    if lawyer is not None:
        providing.append(
            ServiceProvidingItem(
                kind=ServiceKind.INDIVIDUAL,
                service_type=IndividualServiceType.LAWYER,
                lawyer=await build_lawyer_response(session, lawyer),
            )
        )

    client_contracts = list(
        (
            await session.execute(
                select(LawyerContract)
                .where(LawyerContract.client_user_id == user_id)
                .order_by(LawyerContract.created_at.desc())
            )
        ).scalars().all()
    )

    using: list[ServiceUsingItem] = []
    if client_contracts:
        by_lawyer: dict[uuid.UUID, list[LawyerContract]] = defaultdict(list)
        for c in client_contracts:
            by_lawyer[c.lawyer_id].append(c)

        lawyer_rows = {
            lw.id: lw
            for lw in (
                await session.execute(
                    select(Lawyer).where(Lawyer.id.in_(by_lawyer.keys()))
                )
            ).scalars().all()
        }

        for lawyer_id, contracts in by_lawyer.items():
            lw = lawyer_rows.get(lawyer_id)
            active = sum(1 for c in contracts if c.status in ("pending", "active"))
            using.append(
                ServiceUsingItem(
                    kind=ServiceKind.INDIVIDUAL,
                    service_type=IndividualServiceType.LAWYER,
                    lawyer=LawyerUsageSummary(
                        lawyer_id=lawyer_id,
                        lawyer_user_id=lw.user_id if lw else lawyer_id,
                        firm_name=lw.firm_name if lw else None,
                        bar_number=lw.bar_number if lw else None,
                        active_contracts=active,
                        total_contracts=len(contracts),
                    ),
                    contracts=[LawyerContractResponse.model_validate(c) for c in contracts],
                )
            )

    return UserProfileDashboard(
        user=user_response,
        services_providing=providing,
        services_using=using,
    )
