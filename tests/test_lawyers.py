from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.models import Lawyer, LawyerContract, User
from tests.conftest import AUTH_HEADER

USER_ID = uuid4()
LAWYER_ID = uuid4()
CLIENT_ID = uuid4()
CONTRACT_ID = uuid4()
NOW = datetime.now(timezone.utc)


def _lawyer(**kwargs) -> Lawyer:
    defaults = dict(
        id=LAWYER_ID,
        user_id=USER_ID,
        service_type="lawyer",
        status="active",
        bar_number="BAR-123",
        license_jurisdiction="CA",
        firm_name="Firm",
        specializations="civil",
        bio="bio",
        years_experience=5,
        promoted_at=NOW,
        promoted_by="service:dev",
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )
    defaults.update(kwargs)
    return Lawyer(**defaults)


@pytest.mark.asyncio
async def test_promote_lawyer_success(client):
    with patch("app.api.routes.lawyers.query", new_callable=AsyncMock) as mock_query:
        from app.schemas.lawyer import LawyerResponse
        from app.schemas.service import IndividualServiceType

        mock_query.return_value = LawyerResponse(
            id=LAWYER_ID,
            user_id=USER_ID,
            service_type=IndividualServiceType.LAWYER,
            status="active",
            bar_number="BAR-123",
            license_jurisdiction="CA",
            promoted_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        response = await client.post(
            "/lawyers/promote",
            headers=AUTH_HEADER,
            json={
                "user_id": str(USER_ID),
                "bar_number": "BAR-123",
                "license_jurisdiction": "CA",
            },
        )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_get_lawyer_by_user_not_found(client):
    with patch("app.api.routes.lawyers.query", new_callable=AsyncMock) as mock_query:
        from fastapi import HTTPException

        mock_query.side_effect = HTTPException(status_code=404, detail="Lawyer not found for user")
        response = await client.get(f"/lawyers/by-user/{USER_ID}", headers=AUTH_HEADER)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_contract_success(client):
    contract = LawyerContract(
        id=CONTRACT_ID,
        lawyer_id=LAWYER_ID,
        client_user_id=CLIENT_ID,
        status="pending",
        title="Retainer",
        description=None,
        rating=None,
        review_text=None,
        started_at=None,
        ended_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    with patch("app.api.routes.lawyers.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = contract
        response = await client.post(
            f"/lawyers/{LAWYER_ID}/contracts",
            headers=AUTH_HEADER,
            json={
                "client_user_id": str(CLIENT_ID),
                "title": "Retainer",
            },
        )
    assert response.status_code == 201
    assert response.json()["title"] == "Retainer"


@pytest.mark.asyncio
async def test_get_user_with_lawyer_artifact(client):
    user_id = uuid4()
    from app.schemas.user import UserResponse
    from app.services.lawyer import build_lawyer_artifact

    mock_user = User(
        id=user_id,
        email="lawyer@example.com",
        auth_method="email_password",
        display_name="L",
        idempotency_key=None,
        created_at=NOW,
        deleted_at=None,
    )
    mock_lawyer = _lawyer(user_id=user_id)
    base = UserResponse.model_validate(mock_user)
    user_response = base.model_copy(update={"lawyer": build_lawyer_artifact(mock_lawyer)})

    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = user_response
        response = await client.get(f"/users/{user_id}", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["lawyer"] is not None
    assert body["lawyer"]["bar_number"] == "BAR-123"
