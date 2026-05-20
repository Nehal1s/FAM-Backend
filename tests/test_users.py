from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.models import User
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_get_user_missing_auth(client):
    user_id = uuid4()
    response = await client.get(f"/users/{user_id}")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert "Authorization header required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_user_missing_auth(client):
    response = await client.post(
        "/users",
        json={"email": "new@example.com"},
    )
    assert response.status_code == 401
    assert "Authorization header required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_user_invalid_token(client):
    user_id = uuid4()
    response = await client.get(
        f"/users/{user_id}",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_invalid_uuid(client):
    response = await client.get("/users/not-a-uuid", headers=AUTH_HEADER)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_user_not_found(client):
    user_id = uuid4()
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = None
        response = await client.get(f"/users/{user_id}", headers=AUTH_HEADER)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_get_user_success(client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_user = User(
        id=user_id,
        email="user@example.com",
        auth_method="static_token",
        display_name=None,
        idempotency_key=None,
        created_at=now,
        deleted_at=None,
    )

    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = mock_user
        response = await client.get(f"/users/{user_id}", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["email"] == "user@example.com"
    assert body["auth_method"] == "static_token"
    assert "created_at" in body


@pytest.mark.asyncio
async def test_get_user_db_timeout(client):
    user_id = uuid4()
    from app.exceptions import DbTimeoutError

    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.side_effect = DbTimeoutError("timed out")
        response = await client.get(f"/users/{user_id}", headers=AUTH_HEADER)

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_list_users_success(client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_user = User(
        id=user_id,
        email="a@example.com",
        auth_method="pending",
        display_name="A",
        idempotency_key=None,
        created_at=now,
        deleted_at=None,
    )
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = (1, [mock_user])
        response = await client.get("/users", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["email"] == "a@example.com"


@pytest.mark.asyncio
async def test_create_user_created(client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_user = User(
        id=user_id,
        email="new@example.com",
        auth_method="static_token",
        display_name=None,
        idempotency_key=None,
        created_at=now,
        deleted_at=None,
    )
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = (mock_user, False)
        response = await client.post(
            "/users",
            headers=AUTH_HEADER,
            json={"email": "new@example.com", "auth_method": "static_token"},
        )

    assert response.status_code == 201
    assert response.json()["email"] == "new@example.com"


@pytest.mark.asyncio
async def test_create_user_idempotent_replay(client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_user = User(
        id=user_id,
        email="new@example.com",
        auth_method="static_token",
        display_name=None,
        idempotency_key="key-1",
        created_at=now,
        deleted_at=None,
    )
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = (mock_user, True)
        response = await client.post(
            "/users",
            headers={**AUTH_HEADER, "Idempotency-Key": "key-1"},
            json={"email": "new@example.com"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_lookup_user_by_email(client):
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = True
        response = await client.get(
            "/users/lookup",
            headers=AUTH_HEADER,
            params={"email": "someone@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {"exists": True}


@pytest.mark.asyncio
async def test_patch_user_success(client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_user = User(
        id=user_id,
        email="u@example.com",
        auth_method="google",
        display_name="U",
        idempotency_key=None,
        created_at=now,
        deleted_at=None,
    )
    with patch("app.api.routes.users.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = mock_user
        response = await client.patch(
            f"/users/{user_id}",
            headers=AUTH_HEADER,
            json={"display_name": "U", "auth_method": "google"},
        )

    assert response.status_code == 200
    assert response.json()["auth_method"] == "google"
