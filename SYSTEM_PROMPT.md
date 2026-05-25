# FAM Backend - System Prompt for LLM Code Generation

Use this prompt when working with other LLM tools (Claude, GPT-4, etc.) to generate code changes without repeating context.

---

## System Context

You are assisting with development of **FAM Backend**, a REST API for a lawyer services marketplace.

### Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL with SQLAlchemy ORM (2.0+)
- **Testing**: pytest with pytest-asyncio
- **Deployment**: Docker, AWS (RDS, Secrets Manager, CloudWatch)

### Project Purpose

FAM Backend is a marketplace connecting clients with lawyers. The system manages:

1. **Users**: Core user accounts (email, auth method, profile)
2. **Lawyers**: Promoted users offering legal services (bar number, specializations, status)
3. **Contracts**: Client-lawyer engagements (subscriptions, ratings)

---

## Data Models

### User Table

- **Primary Key**: `id` (UUID)
- **Unique Fields**: `email`, `idempotency_key`
- **Key Columns**:
  - `auth_method`: pending | email_password | google | apple | static_token
  - `display_name`: Nullable user display name
  - `deleted_at`: Soft delete timestamp (NULL = active)
- **Timestamps**: `created_at` (auto)
- **Relationships**: 1:0-1 with Lawyer (user → lawyer_profile)

### Lawyer Table

- **Primary Key**: `id` (UUID)
- **Foreign Key**: `user_id` (unique, cascade delete)
- **Key Columns**:
  - `bar_number`: Required legal identifier
  - `license_jurisdiction`: Required state/country
  - `firm_name`: Nullable
  - `specializations`: Nullable comma-separated string
  - `status`: active | inactive | suspended
  - `deleted_at`: Soft delete (demote when not NULL)
- **Timestamps**: `created_at`, `updated_at` (auto), `promoted_at`
- **Relationships**: 1:1 with User, 1:many with LawyerContract

### LawyerContract Table

- **Primary Key**: `id` (UUID)
- **Foreign Keys**: `lawyer_id`, `client_user_id` (cascade delete)
- **Key Columns**:
  - `status`: pending | active | completed | cancelled
  - `rating`: Nullable integer (client rating)
- **Timestamps**: `created_at`, `updated_at` (auto)
- **Relationships**: Many to Lawyer, many to User

---

## Authentication & Authorization

### Bearer Token Authentication

- **Header**: `Authorization: Bearer <token>`
- **Token Sources**:
  - Local Dev: `BEARER_TOKENS_JSON` environment variable (JSON array)
  - Production: AWS Secrets Manager (`AUTH_SECRET_ARN`)
- **Token Structure**: `{"id": "token-id", "token": "secret", "type": "user"|"service"}`

### AuthContext (Injected into all routes)

```python
class AuthContext:
    subject_id: str              # "service:token-id" or "user:uuid"
    token_id: str
    auth_method: Literal["bearer_static", "jwt"]
```

### Authorization Rules

- **User tokens**: Can access `/me/profile` (personal dashboard)
- **Service tokens**: Admin operations (promote lawyer), no user context
- **Bypass token**: Exceeds rate limits
- **Rate Limit**: 100 requests/60 seconds per token

---

## Project Structure

```
app/
├── api/
│   ├── deps.py                  # Dependency injection (require_auth_and_rate_limit)
│   └── routes/
│       ├── users.py             # GET/POST/PATCH /users endpoints
│       ├── lawyers.py           # GET/POST/PATCH /lawyers endpoints
│       └── profile.py           # GET /me/profile dashboard
├── auth/
│   ├── base.py                  # AuthContext, require_auth()
│   ├── bearer.py                # Token validation, caching
│   ├── rate_limit.py            # Per-token rate limiting
│   └── session.py               # User session (future JWT)
├── db/
│   ├── engine.py                # SQLAlchemy engine, pool config
│   ├── models.py                # User, Lawyer, LawyerContract ORM models
│   └── query.py                 # Async query helper with timeout
├── services/
│   ├── users.py                 # get_user_or_404(), user operations
│   ├── lawyer.py                # get_active_lawyer(), build_lawyer_artifact()
│   ├── subscription.py          # subscribe_user_to_service()
│   └── profile.py               # Profile aggregation logic
├── schemas/                     # Pydantic request/response models
│   ├── user.py
│   ├── lawyer.py
│   ├── service.py
│   ├── profile.py
│   └── user_auth.py
├── logging/
│   └── setup.py                 # structlog configuration
├── metrics/
│   └── cloudwatch.py            # CloudWatch metrics (latency, errors)
├── secrets/
│   └── loader.py                # Load bearer tokens from Secrets Manager/.env
├── config.py                    # Settings (pydantic-settings)
├── exceptions.py                # DbTimeoutError, custom exceptions
└── main.py                      # FastAPI app factory, lifespan
```

---

## API Endpoints (Quick Reference)

### User Endpoints

- `GET /users/` — List users (paginated)
- `POST /users/` — Create user (supports Idempotency-Key)
- `GET /users/{user_id}` — Fetch user (includes lawyer artifact if promoted)
- `PATCH /users/{user_id}` — Update display_name, auth_method
- `GET /users/lookup?email=` — Email existence check

### Lawyer Endpoints

- `POST /lawyers/promote` — Promote user to lawyer (admin)
- `GET /lawyers` — List all active lawyers
- `GET /lawyers/{lawyer_id}` — Lawyer profile + stats
- `GET /lawyers/by-user/{user_id}` — Lawyer by user ID
- `PATCH /lawyers/{lawyer_id}` — Update lawyer info
- `DELETE /lawyers/{lawyer_id}` — Demote lawyer

### Contract Endpoints

- `POST /lawyers/{lawyer_id}/contracts` — Subscribe client to lawyer
- `GET /lawyers/{lawyer_id}/contracts` — Contracts for lawyer
- `PATCH /lawyers/contracts/{contract_id}` — Update contract status/rating
- `GET /lawyers/contracts/by-client/{client_user_id}` — Client's contracts

### Profile Endpoint

- `GET /me/profile` — User dashboard (personal, requires user token)

### Health

- `GET /health` — Health check

---

## Common Code Patterns

### 1. Database Query with Timeout

```python
from app.db.query import query

async def _query_logic(session: AsyncSession) -> Any:
    result = await session.execute(select(...))
    return result.scalar_one_or_none()

try:
    result = await query(_query_logic, timeout_ms=300, operation="my_operation")
except DbTimeoutError:
    raise HTTPException(status_code=504, detail="Database query timed out")
```

### 2. Soft-Delete Filter

```python
from sqlalchemy import select
from app.db.models import User

# Always add deleted_at filter
query = select(User).where(User.deleted_at.is_(None))
```

### 3. Authentication Injection

```python
from fastapi import Depends
from app.api.deps import require_auth_and_rate_limit
from app.auth.base import AuthContext

@router.get("/protected")
async def protected_endpoint(auth: AuthContext = Depends(require_auth_and_rate_limit)):
    # auth.subject_id, auth.token_id, auth.auth_method available
    ...
```

### 4. Structured Logging

```python
import structlog

logger = structlog.get_logger(__name__)
logger.info("event_name", key="value", user_id=auth.subject_id)
logger.warning("something_unusual", hint="helpful_message")
```

### 5. CloudWatch Metrics

```python
from app.metrics.cloudwatch import LatencyTimer, record_error

with LatencyTimer("EndpointLatency", {"Endpoint": "my_endpoint"}):
    # Code to measure
    ...

if error_occurred:
    record_error("ErrorType", {"Endpoint": "my_endpoint"})
```

### 6. Pagination Response

```python
from app.schemas.user import UserListResponse

return UserListResponse(
    items=[UserResponse.model_validate(u) for u in users],
    total=total_count,
    page=page_number,
    page_size=page_size,
)
```

### 7. Idempotency Key Handling

```python
idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
key = (idempotency_key or "").strip()[:128] or None
# Use key to check for duplicate request, return 200 if found
```

---

## Environment Variables (Key Ones)

| Variable                   | Local Dev            | Production                 |
| -------------------------- | -------------------- | -------------------------- |
| `ENVIRONMENT`              | `"development"`      | `"production"`             |
| `DATABASE_URL`             | Local postgres URL   | From Secrets Manager       |
| `AUTH_SECRET_ARN`          | N/A                  | AWS Secrets Manager ARN    |
| `BEARER_TOKENS_JSON`       | JSON array of tokens | N/A (from Secrets Manager) |
| `ALLOW_DEV_USER_ID_HEADER` | `true`               | `false`                    |
| `RATE_LIMIT_REQUESTS`      | `100`                | Configurable               |
| `DB_QUERY_TIMEOUT_MS`      | `300`                | Configurable               |

---

## Testing Conventions

### File Location

- Tests in `tests/` directory
- Filename: `test_<module>.py`
- Fixture file: `conftest.py` (pytest auto-discovery)

### Async Test Syntax

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post("/users/", json={...})
    assert response.status_code == 201
```

### Database Test Fixture

- Use `conftest.py` for session fixtures
- Rollback after each test (clean state)

---

## HTTP Status Codes (Expected)

- **200**: Success
- **201**: Resource created
- **400**: Validation error
- **401**: Missing/invalid auth
- **403**: Forbidden (insufficient permissions)
- **404**: Resource not found
- **409**: Conflict (duplicate email, etc.)
- **429**: Rate limit exceeded
- **504**: Database query timeout

---

## Key Design Principles

1. **Soft Deletes**: Always use `deleted_at` field; never hard delete
2. **Query Timeouts**: Wrap DB queries in `query()` helper to prevent hangs
3. **Structured Logging**: Use structlog with correlation IDs for debugging
4. **Idempotency**: Support Idempotency-Key header for replay safety
5. **Async/Await**: All I/O is async; use `AsyncSession` for DB
6. **Bearer Tokens**: Static tokens in dev, JWT in future
7. **Rate Limiting**: Per-token sliding window; bypass for admin
8. **Relationships**: Use SQLAlchemy relationships (1:1, 1:many) with cascade delete

---

## Common Gotchas & Tips

1. **Always filter deleted records**: Add `WHERE deleted_at IS NULL` to queries
2. **Use AsyncSession** for database operations (not sync Session)
3. **Bearer token case-insensitive scheme check**: Compare with `.lower()`
4. **Idempotency key is unique** (database constraint): Handle IntegrityError on retry
5. **Rate limiting is in-memory**: Resets on app restart (OK for MVP)
6. **Correlation ID propagation**: Pass through logs and error responses
7. **CloudWatch optional**: Don't require it; gracefully handle disabled metrics
8. **Future JWT**: `auth_method` field already supports "jwt" type

---

## Migration & Deployment

### Running Migrations

```bash
alembic upgrade head       # Latest
alembic downgrade -1       # Rollback one
alembic revision --autogenerate -m "description"
```

### Production Deployment Checklist

- [ ] Environment set to `"production"`
- [ ] Database secrets configured in AWS Secrets Manager
- [ ] Bearer tokens loaded from Secrets Manager (not .env)
- [ ] CloudWatch enabled and IAM permissions granted
- [ ] Database pool size tuned for load
- [ ] Query timeout tested under realistic conditions
- [ ] Migrations applied to RDS
- [ ] Logging level set to INFO or DEBUG as needed

---

## When Making Changes

1. **Add/Modify Endpoint**:
   - Create route in `app/api/routes/` file
   - Inject `AuthContext` dependency
   - Use service layer for business logic
   - Return Pydantic response model

2. **Add Service Logic**:
   - Create function in `app/services/<domain>.py`
   - Wrap DB queries with timeout protection
   - Use structured logging

3. **Update Database Schema**:
   - Modify ORM model in `app/db/models.py`
   - Create migration: `alembic revision --autogenerate -m "description"`
   - Test migration locally

4. **Add Validation**:
   - Create Pydantic schema in `app/schemas/<domain>.py`
   - Use FastAPI request body annotation

5. **Fix Bug**:
   - Add test case first (TDD)
   - Reproduce bug
   - Fix in appropriate layer (route, service, db)
   - Verify test passes

---

## Questions for Context Clarification

When you encounter ambiguity, ask:

- "Should this be a soft delete or hard delete?"
- "Is this endpoint user-only or admin-only?"
- "Should this support idempotency?"
- "What's the timeout requirement for this query?"
- "Do we need CloudWatch metrics for this?"
- "Is this a breaking API change?"

---

## End of System Prompt

Copy and paste the above into your LLM tool's system/context section before asking for code changes.
