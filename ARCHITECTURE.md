# FAM Backend - Architecture Documentation

## Project Overview

**FAM Backend** is a REST API for a lawyer services marketplace platform built with **FastAPI + PostgreSQL**.

- **Framework**: FastAPI (async, Python 3.11+)
- **Database**: PostgreSQL (RDS in production) with SQLAlchemy ORM
- **Deployment**: Docker, AWS (RDS, Secrets Manager, CloudWatch)
- **Authentication**: Bearer tokens (static) → future JWT from login services
- **Infrastructure**: Async task workers, rate limiting, idempotency keys, structured logging

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Routes (routers: users, lawyers, profile)           │  │
│  │  • GET/POST /users                                       │  │
│  │  • GET /users/{id}, GET /users/lookup                    │  │
│  │  • PATCH /users/{id}                                     │  │
│  │  • POST/GET /lawyers, PATCH /lawyers/{id}                │  │
│  │  • POST/PATCH /lawyers/{id}/contracts                    │  │
│  │  • GET /me/profile (user dashboard)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Authentication & Middleware                             │  │
│  │  • HTTPBearer scheme (Bearer token validation)           │  │
│  │  • AuthContext (subject_id, token_id, auth_method)       │  │
│  │  • Rate limiting (per token)                             │  │
│  │  • Correlation ID tracking                               │  │
│  │  • Structured logging (structlog)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Domain Services (Business Logic)                        │  │
│  │  • UserService (get_user_or_404, create/update)         │  │
│  │  • LawyerService (promote, get_active_lawyer)           │  │
│  │  • SubscriptionService (subscribe_user_to_service)      │  │
│  │  • ProfileService (aggregate user + services)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Database Layer (SQLAlchemy ORM)                        │  │
│  │  • Models: User, Lawyer, LawyerContract                 │  │
│  │  • Query utilities (async context manager)              │  │
│  │  • Connection pooling (asyncpg)                         │  │
│  │  • Query timeout protection                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↓                                     │
│              PostgreSQL Database                                │
│  (Migrations: alembic/versions/)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### 1. **User**

Represents any user in the system (potential lawyer, client, admin).

```
users (table)
├── id: UUID (PK)
├── email: String (unique)
├── auth_method: String (pending, email_password, google, apple, static_token)
├── display_name: String (nullable)
├── idempotency_key: String (nullable, unique) — for replay protection
├── created_at: DateTime (server default: now())
├── deleted_at: DateTime (nullable) — soft delete
└── Relationships:
    └── lawyer_profile: 1:0-1 (User → Lawyer)
```

### 2. **Lawyer**

A User who has been promoted to offer legal services. 1:1 with User.

```
lawyers (table)
├── id: UUID (PK)
├── user_id: UUID (FK → users.id, unique, cascade delete)
├── service_type: String (default: "lawyer")
├── status: String (active, inactive, suspended)
├── bar_number: String (required)
├── license_jurisdiction: String (required)
├── firm_name: String (nullable)
├── specializations: String (nullable, comma-separated)
├── bio: Text (nullable)
├── years_experience: Integer (nullable)
├── promoted_at: DateTime (server default: now())
├── promoted_by: String (nullable) — admin/service token ID
├── created_at: DateTime (server default: now())
├── updated_at: DateTime (server default: now(), auto-update)
├── deleted_at: DateTime (nullable) — soft delete (demote)
└── Relationships:
    ├── user: 1:1 (Lawyer → User)
    └── contracts: 1:many (Lawyer → LawyerContract)
```

### 3. **LawyerContract**

A subscription/engagement between a client (User) and a Lawyer.

```
lawyer_contracts (table)
├── id: UUID (PK)
├── lawyer_id: UUID (FK → lawyers.id, cascade delete)
├── client_user_id: UUID (FK → users.id, cascade delete)
├── status: String (pending, active, completed, cancelled)
├── title: String (e.g., "Corporate Compliance Review")
├── description: Text (nullable)
├── rating: Integer (nullable) — client rating (1-5)
├── created_at: DateTime (server default: now())
├── updated_at: DateTime (server default: now(), auto-update)
└── Relationships:
    ├── lawyer: 1:many (Contract → Lawyer)
    └── client_user: 1:many (Contract → User)
```

---

## Project Structure

```
FAM-Backend/
├── alembic/                          # Database migrations
│   ├── env.py                        # Alembic configuration
│   ├── script.py.mako                # Migration template
│   └── versions/
│       ├── 001_create_users_table.py
│       ├── 002_user_auth_method_and_meta.py
│       └── 003_lawyer_service.py
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app factory, lifespan
│   ├── config.py                     # Settings (pydantic-settings)
│   ├── exceptions.py                 # Custom exceptions (DbTimeoutError)
│   ├── api/
│   │   ├── deps.py                   # Dependency injections (auth, correlation ID)
│   │   └── routes/
│   │       ├── users.py              # GET/POST/PATCH /users
│   │       ├── lawyers.py            # GET/POST/PATCH /lawyers
│   │       └── profile.py            # GET /me/profile (dashboard)
│   ├── auth/
│   │   ├── base.py                   # AuthContext, require_auth()
│   │   ├── bearer.py                 # Bearer token validation & caching
│   │   ├── session.py                # User session (future JWT logic)
│   │   └── rate_limit.py             # Per-token rate limiting
│   ├── db/
│   │   ├── engine.py                 # SQLAlchemy engine, pool config
│   │   ├── models.py                 # User, Lawyer, LawyerContract
│   │   └── query.py                  # Async query helper (timeout)
│   ├── logging/
│   │   └── setup.py                  # structlog configuration
│   ├── metrics/
│   │   └── cloudwatch.py             # CloudWatch metrics (latency, errors)
│   ├── schemas/                      # Pydantic models (request/response)
│   │   ├── user.py                   # UserResponse, UserCreateRequest
│   │   ├── lawyer.py                 # LawyerResponse, LawyerArtifact
│   │   ├── service.py                # ServiceType enums
│   │   ├── profile.py                # ProfileResponse
│   │   └── user_auth.py              # Auth method schemas
│   ├── services/                     # Business logic
│   │   ├── users.py                  # get_user_or_404(), user operations
│   │   ├── lawyer.py                 # get_active_lawyer(), build_lawyer_artifact()
│   │   ├── subscription.py           # subscribe_user_to_service()
│   │   └── profile.py                # profile aggregation
│   └── secrets/
│       └── loader.py                 # Load bearer tokens from Secrets Manager or .env
├── tests/
│   ├── conftest.py                   # pytest fixtures
│   ├── test_users.py
│   ├── test_lawyers.py
│   └── test_profile.py
├── pyproject.toml                    # Project metadata, dependencies
├── requirements.txt                  # Pinned dependencies
├── alembic.ini                       # Alembic config file
├── Dockerfile                        # Container image
├── .env.example                      # Environment variables template
└── README.md                         # Quick start guide
```

---

## API Endpoints

### User Management

| Method | Path               | Auth   | Description                                                       |
| ------ | ------------------ | ------ | ----------------------------------------------------------------- |
| GET    | `/users/`          | Bearer | List users (paginated: `page`, `page_size`)                       |
| POST   | `/users/`          | Bearer | Create user; supports `Idempotency-Key` header (replay → **200**) |
| GET    | `/users/lookup`    | Bearer | Email lookup: `?email=` → `{ "exists": bool }`                    |
| GET    | `/users/{user_id}` | Bearer | Fetch single user (includes lawyer artifact if promoted)          |
| PATCH  | `/users/{user_id}` | Bearer | Update `display_name` and/or `auth_method`                        |

### Lawyer Service

| Method | Path                                            | Auth   | Description                                           |
| ------ | ----------------------------------------------- | ------ | ----------------------------------------------------- |
| POST   | `/lawyers/promote`                              | Bearer | Promote user → lawyer (requires admin/service token)  |
| GET    | `/lawyers`                                      | Bearer | List all active lawyers                               |
| GET    | `/lawyers/{lawyer_id}`                          | Bearer | Lawyer profile + stats (avg rating, contract count)   |
| GET    | `/lawyers/by-user/{user_id}`                    | Bearer | Get lawyer profile by user ID                         |
| PATCH  | `/lawyers/{lawyer_id}`                          | Bearer | Update legal info (bar_number, specializations, etc.) |
| DELETE | `/lawyers/{lawyer_id}`                          | Bearer | Demote lawyer (soft delete)                           |
| POST   | `/lawyers/{lawyer_id}/contracts`                | Bearer | Client subscribes to lawyer                           |
| GET    | `/lawyers/{lawyer_id}/contracts`                | Bearer | Contract history for lawyer                           |
| PATCH  | `/lawyers/contracts/{contract_id}`              | Bearer | Update contract status/rating                         |
| GET    | `/lawyers/contracts/by-client/{client_user_id}` | Bearer | Contracts for a client                                |

### User Dashboard

| Method | Path          | Auth                | Description                                       |
| ------ | ------------- | ------------------- | ------------------------------------------------- |
| GET    | `/me/profile` | Bearer (user token) | Logged-in user profile + services providing/using |

### Health Check

| Method | Path      | Auth | Description          |
| ------ | --------- | ---- | -------------------- |
| GET    | `/health` | None | Service health check |

---

## Authentication & Authorization

### Bearer Token Flow

1. **Token Source**:
   - Local dev: `BEARER_TOKENS_JSON` environment variable (JSON list)
   - Production: AWS Secrets Manager (`AUTH_SECRET_ARN`)

2. **Token Structure**:

   ```json
   {
     "id": "dev-token-1",
     "token": "secret-token-string",
     "type": "user" | "service"
   }
   ```

3. **Token Types**:
   - **User token**: Has `user_id`; can access `/me/profile`
   - **Service token**: No user context; admin operations (promote lawyer)
   - **API key**: Special bypass token for internal tools

4. **AuthContext** (attached to each request):

   ```python
   class AuthContext:
       subject_id: str              # "service:dev-token-1" or "user:uuid"
       token_id: str                # "dev-token-1"
       auth_method: Literal["bearer_static", "jwt"]  # Currently "bearer_static"
   ```

5. **Rate Limiting**:
   - Per-token limits: 100 requests / 60 seconds (configurable)
   - Bypass token can exceed limits
   - Returns **429** if exceeded

### Future: JWT Access Tokens

- Google / email/password login → JWT generation
- JWT validation instead of static tokens
- `auth_method="jwt"` in AuthContext

---

## Configuration

### Environment Variables (`.env` local dev or Secrets Manager production)

| Variable                    | Default         | Description                              |
| --------------------------- | --------------- | ---------------------------------------- |
| `APP_NAME`                  | `"fam-backend"` | Application name                         |
| `ENVIRONMENT`               | `"development"` | `development` \| `production`            |
| `LOG_LEVEL`                 | `"INFO"`        | Logging level                            |
| `DATABASE_URL`              | —               | PostgreSQL connection string (local dev) |
| `DATABASE_SECRET_ARN`       | —               | AWS Secrets Manager ARN (production)     |
| `DB_POOL_SIZE`              | `50`            | SQLAlchemy connection pool size          |
| `DB_MAX_OVERFLOW`           | `20`            | Max overflow connections                 |
| `DB_QUERY_TIMEOUT_MS`       | `300`           | Query timeout in milliseconds            |
| `AUTH_SECRET_ARN`           | —               | Secrets Manager ARN for bearer tokens    |
| `BEARER_TOKENS_JSON`        | —               | Local dev: JSON list of tokens           |
| `RATE_LIMIT_REQUESTS`       | `100`           | Requests per window                      |
| `RATE_LIMIT_WINDOW_SECONDS` | `60`            | Rate limit window                        |
| `ALLOW_DEV_USER_ID_HEADER`  | `true`          | Allow `X-User-Id` header in dev          |
| `JWT_SECRET`                | —               | (Future) JWT signing secret              |
| `JWT_ALGORITHM`             | `"HS256"`       | JWT algorithm                            |
| `CLOUDWATCH_ENABLED`        | `false`         | Enable CloudWatch metrics                |
| `CLOUDWATCH_NAMESPACE`      | `"FAM/Backend"` | CloudWatch namespace                     |
| `AWS_REGION`                | `"us-east-1"`   | AWS region                               |

---

## Key Features & Design Patterns

### 1. Idempotency

- **Header**: `Idempotency-Key` (up to 128 characters)
- **Behavior**: Duplicate requests with same key return **200** with cached response
- **Use Case**: Retry-safe user creation, payment processing

### 2. Soft Deletes

- **Deleted records**: `deleted_at` timestamp (not NULL = deleted)
- **Queries**: Always filter `WHERE deleted_at IS NULL`
- **Benefit**: Audit trail, data recovery, foreign key safety

### 3. Query Timeouts

- **Async helper**: `query()` function in `app/db/query.py`
- **Timeout**: Configurable per environment
- **Response**: **504** if query exceeds timeout

### 4. Structured Logging

- **Library**: `structlog` (async-friendly)
- **Correlation ID**: Tracked across requests (X-Correlation-ID header)
- **Format**: JSON logs with structured context

### 5. CloudWatch Metrics

- **Latency**: Per-endpoint timing
- **Errors**: Error rate, timeout counts
- **Integration**: Boto3 (optional)

### 6. Rate Limiting

- **Per-token**: Sliding window counter (in-memory)
- **Bypass**: Admin token can exceed limits
- **Response**: **429** Too Many Requests

---

## Database Migrations

Using **Alembic** for schema versioning.

### Existing Migrations

1. **001_create_users_table.py**: Core User table
2. **002_user_auth_method_and_meta.py**: Added `auth_method`, metadata fields
3. **003_lawyer_service.py**: Lawyer + LawyerContract tables

### Running Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Create new migration (auto-detect model changes)
alembic revision --autogenerate -m "description"
```

---

## Development Workflow

### Local Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy environment file
cp .env.example .env

# 3. Configure .env with local DATABASE_URL and BEARER_TOKENS_JSON

# 4. Run migrations
alembic upgrade head

# 5. Start dev server
uvicorn main:app --reload --port 8080
```

### Running Tests

```bash
pytest tests/ -v
# or async-specific
pytest tests/ -v --asyncio-mode=auto
```

### Docker Build

```bash
docker build -t fam-backend:latest .
```

---

## Error Handling

### HTTP Status Codes

| Code    | Scenario                                          |
| ------- | ------------------------------------------------- |
| **200** | Success (or idempotent replay)                    |
| **201** | Resource created                                  |
| **400** | Invalid request (validation error)                |
| **401** | Missing/invalid bearer token                      |
| **403** | Forbidden (service token accessing user resource) |
| **404** | Resource not found                                |
| **409** | Conflict (e.g., duplicate email)                  |
| **429** | Rate limit exceeded                               |
| **500** | Internal server error                             |
| **504** | Database query timeout                            |

### Custom Exceptions

- **DbTimeoutError**: Query exceeded timeout limit
- **Standard HTTPException**: FastAPI validation/auth errors

---

## Production Deployment

### AWS Infrastructure

1. **RDS**: PostgreSQL database
2. **Secrets Manager**: Bearer tokens + database credentials
3. **CloudWatch**: Metrics, logs, alarms
4. **ECS/Lambda**: Container or serverless compute

### Secrets Manager Structure

```json
{
  "database": "postgresql://user:pass@rds-endpoint/dbname",
  "bearer_tokens": [
    { "id": "prod-service-1", "token": "...", "type": "service" },
    { "id": "prod-user-1", "token": "...", "type": "user" }
  ]
}
```

---

## Future Enhancements

1. **JWT Login**: Replace static bearer tokens with OAuth2 (Google, email/password)
2. **WebSocket Support**: Real-time notifications for lawyer/client interactions
3. **Payment Integration**: Stripe for subscription billing
4. **Advanced Search**: Elasticsearch for lawyer discovery
5. **Background Jobs**: Celery for async tasks (email, notifications)

---

## Support & Debugging

### Useful Commands

```bash
# Check app health
curl -s http://localhost:8080/health | jq .

# List users (with auth)
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8080/users/?page=1&page_size=10

# Tail logs
tail -f .log

# Database CLI
psql $DATABASE_URL -c "SELECT * FROM users LIMIT 10;"
```

### Common Issues

1. **DB Connection Timeout**: Check `DATABASE_URL`, pool size, query timeout
2. **Auth Fails**: Verify bearer token in `BEARER_TOKENS_JSON` or Secrets Manager
3. **Migration Error**: Check migration files for schema conflicts
4. **Rate Limit Hits**: Adjust `RATE_LIMIT_REQUESTS` or use bypass token

---

## Contact & Documentation

- **Repository**: GitHub (Nehal1s/FAM-Backend)
- **Main Branch**: `main`
- **Issues**: GitHub Issues
