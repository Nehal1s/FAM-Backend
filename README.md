# FAM-Backend

REST API backend (FastAPI + PostgreSQL) for FAM.

## Requirements

- Python 3.11+
- PostgreSQL (RDS in production)
- AWS Secrets Manager (production) or `.env` for local dev

## Quick start (local)

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set DATABASE_URL and BEARER_TOKENS_JSON

# Run migrations
alembic upgrade head

# Start API
uvicorn main:app --reload --port 8080
```

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| GET | `/health` | None | |
| GET | `/users/` | Bearer | Paginated list (`page`, `page_size`) |
| POST | `/users/` | Bearer | Create user; optional `Idempotency-Key` (replay → **200**) |
| GET | `/users/lookup` | Bearer | `?email=` — returns `{ "exists": bool }` |
| PATCH | `/users/{user_id}` | Bearer | Update `display_name` and/or `auth_method` |
| GET | `/users/{user_id}` | Bearer | Fetch one user (includes `lawyer` artifact if promoted) |

### Lawyer service (individual)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/lawyers/promote` | Promote user → lawyer (admin/service token) |
| GET | `/lawyers` | List lawyers |
| GET | `/lawyers/{lawyer_id}` | Lawyer profile + stats |
| GET | `/lawyers/by-user/{user_id}` | Lawyer profile by user id |
| PATCH | `/lawyers/{lawyer_id}` | Update legal info / status |
| DELETE | `/lawyers/{lawyer_id}` | Demote (soft delete) |
| POST | `/lawyers/{lawyer_id}/contracts` | Client subscribes / contracts |
| GET | `/lawyers/{lawyer_id}/contracts` | Contract history for lawyer |
| PATCH | `/lawyers/contracts/{contract_id}` | Update status, rating |
| GET | `/lawyers/contracts/by-client/{client_user_id}` | Contracts for a client |

Run migration: `alembic upgrade head` (revision `003` adds `lawyers`, `lawyer_contracts`).

### User dashboard (`GET /me/profile`)

Logged-in user profile: account info, **services_providing** (e.g. lawyer), **services_using** (e.g. lawyer contracts as client).

**Real-world auth flow (target):**

1. User signs in (Google / email) → API returns **JWT access token** (`sub` = user id).
2. App stores token and sends `Authorization: Bearer <jwt>` on each request.
3. `GET /me/profile` resolves user from JWT — no user id in the URL.

**Local dev until login ships:**

- Option A: Bearer token with `"type":"user"` and `"user_id":"<uuid>"` in `BEARER_TOKENS_JSON`
- Option B: Service token + header `X-User-Id: <uuid>` (only when `ENVIRONMENT=development`)

Service-only tokens (`type":"service"`) get **403** on `/me/profile` (admin tokens must not impersonate users).

`User.auth_method` values: `pending`, `email_password`, `google`, `apple`, `static_token` (see `app/schemas/user_auth.py`). This is separate from API `AuthContext.auth_method` (`bearer_static` / future `jwt`).

### Examples

```bash
# List (note trailing slash or follow redirect)
curl -s -H "Authorization: Bearer your-dev-token-here" \
  "http://localhost:8080/users/?page=1&page_size=20"

# Create
curl -s -X POST -H "Authorization: Bearer your-dev-token-here" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: onboarding-123" \
  -d '{"email":"user@example.com","auth_method":"pending","display_name":"Ada"}' \
  http://localhost:8080/users/

# Email exists?
curl -s -H "Authorization: Bearer your-dev-token-here" \
  "http://localhost:8080/users/lookup?email=user@example.com"

# Get by id
curl -s -H "Authorization: Bearer your-dev-token-here" \
  http://localhost:8080/users/550e8400-e29b-41d4-a716-446655440000
```

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Local Postgres connection string |
| `AUTH_SECRET_ARN` | Secrets Manager ARN (combined JSON on EC2) |
| `BEARER_TOKENS_JSON` | Local bearer tokens `[{"id":"...","token":"..."}]` |
| `DB_POOL_SIZE` | Connection pool size (default 20) |
| `DB_QUERY_TIMEOUT_MS` | Per-query timeout (default 150) |
| `CLOUDWATCH_ENABLED` | Emit custom metrics (default false) |

### Secrets Manager JSON shape

```json
{
  "database": {
    "host": "your-rds.region.rds.amazonaws.com",
    "port": 5432,
    "username": "fam",
    "password": "...",
    "dbname": "postgres"
  },
  "bearer_tokens": [
    { "id": "partner-a", "token": "opaque-secret" }
  ]
}
```

## EC2 deployment

1. Attach IAM role with `secretsmanager:GetSecretValue` on your secret ARNs.
2. Set env on the instance: `AUTH_SECRET_ARN`, `ENVIRONMENT=production`, `CLOUDWATCH_ENABLED=true`.
3. Run via Docker (`docker build -t fam-backend .`) or Uvicorn directly.
4. **Pool sizing:** v1 uses one process with `DB_POOL_SIZE=20`. Before adding Uvicorn workers or a second instance, divide the 20-connection RDS budget.

## Tests

```bash
pytest tests/ -v
```

## Project layout

```
app/
  main.py           # FastAPI app + lifespan
  db/query.py       # db.query() wrapper (pool, timeout, retries)
  auth/             # Bearer auth + rate limiting
  api/routes/       # HTTP routes
  secrets/          # Secrets Manager loader
alembic/            # Migrations
```
