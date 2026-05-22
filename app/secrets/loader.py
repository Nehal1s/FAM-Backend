"""Load database credentials and bearer tokens from AWS Secrets Manager or local env."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import structlog

from app.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Expected Secrets Manager JSON:
# {
#   "database": {"host": "...", "port": 5432, "username": "...", "password": "...", "dbname": "..."},
#   "bearer_tokens": [{"id": "partner-a", "token": "opaque-secret"}]
# }


@dataclass(frozen=True)
class BearerTokenEntry:
    id: str
    token: str
    user_id: str | None = None  # set for user session tokens (dashboard /me)
    token_type: str = "service"  # service | user


@dataclass
class _CacheEntry:
    payload: dict[str, Any]
    fetched_at: float


class SecretsStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache: _CacheEntry | None = None
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "secretsmanager",
                region_name=self._settings.aws_region,
            )
        return self._client

    def _should_refresh(self) -> bool:
        if self._cache is None:
            return True
        age = time.monotonic() - self._cache.fetched_at
        return age >= self._settings.secrets_refresh_seconds

    def _fetch_from_aws(self, arn: str) -> dict[str, Any]:
        client = self._get_client()
        response = client.get_secret_value(SecretId=arn)
        raw = response.get("SecretString")
        if not raw:
            raise RuntimeError(f"Secret {arn} has no SecretString")
        return json.loads(raw)

    def _load_payload(self) -> dict[str, Any]:
        if not self._should_refresh() and self._cache is not None:
            return self._cache.payload

        settings = self._settings
        payload: dict[str, Any] = {}

        if settings.database_secret_arn:
            db_payload = self._fetch_from_aws(settings.database_secret_arn)
            if isinstance(db_payload, dict) and "host" in db_payload:
                payload.update(db_payload)
            elif isinstance(db_payload, dict) and "database" in db_payload:
                payload.update(db_payload["database"])

        if settings.auth_secret_arn:
            auth_payload = self._fetch_from_aws(settings.auth_secret_arn)
            if isinstance(auth_payload, dict):
                payload["bearer_tokens"] = auth_payload.get("bearer_tokens", [])
        elif settings.bearer_tokens_json:
            payload["bearer_tokens"] = json.loads(settings.bearer_tokens_json)

        self._cache = _CacheEntry(payload=payload, fetched_at=time.monotonic())
        logger.info("secrets_loaded", source="aws", db_arn=bool(settings.database_secret_arn), auth_arn=bool(settings.auth_secret_arn))
        return payload

    def invalidate(self) -> None:
        self._cache = None

    def get_database_url(self) -> str:
        settings = self._settings
        if settings.database_url:
            return settings.database_url

        payload = self._load_payload()
        if not payload.get("username"):
            raise RuntimeError(
                "No database config: set DATABASE_URL or provide 'database' in Secrets Manager JSON"
            )

        user = quote_plus(str(payload["username"]))
        password = quote_plus(str(payload["password"]))
        host = payload["host"]
        port = payload.get("port", 5432)
        name = payload["dbname"]
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

    def get_bearer_tokens(self) -> list[BearerTokenEntry]:
        settings = self._settings
        if settings.bearer_tokens_json and not settings.auth_secret_arn:
            raw = json.loads(settings.bearer_tokens_json)
            return [_parse_bearer_entry(t) for t in raw]

        payload = self._load_payload()
        tokens = payload.get("bearer_tokens", [])
        return [_parse_bearer_entry(t) for t in tokens]


def _parse_bearer_entry(raw: dict[str, Any]) -> BearerTokenEntry:
    return BearerTokenEntry(
        id=raw["id"],
        token=raw["token"],
        user_id=raw.get("user_id"),
        token_type=raw.get("type", "service"),
    )


_store: SecretsStore | None = None


def get_secrets_store() -> SecretsStore:
    global _store
    if _store is None:
        _store = SecretsStore()
    return _store


def reset_secrets_store() -> None:
    global _store
    _store = None
