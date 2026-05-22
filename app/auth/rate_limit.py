"""In-memory token-bucket rate limiter (single EC2 instance)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.auth.base import AuthContext
from app.config import get_settings


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


_buckets: dict[str, _Bucket] = {}


def check_rate_limit(auth: AuthContext, request: Request | None = None) -> None:
    settings = get_settings()

    # ------------------------------------------------------------------
    # DEV / TESTING BYPASS
    # ------------------------------------------------------------------
    # Add this in your settings/env:
    #
    # RATE_LIMIT_BYPASS_TOKEN=super-secret-dev-token
    #
    # Then pass header:
    # X-RateLimit-Bypass: super-secret-dev-token
    # ------------------------------------------------------------------
    bypass_token = getattr(settings, "rate_limit_bypass_token", None)

    if request and bypass_token:
        provided_token = request.headers.get("X-RateLimit-Bypass")

        # secure comparison
        if provided_token and secrets.compare_digest(
            provided_token,
            bypass_token,
        ):
            return

    key = auth.token_id
    now = time.monotonic()

    max_tokens = float(settings.rate_limit_requests)
    window = float(settings.rate_limit_window_seconds)
    refill_rate = max_tokens / window

    bucket = _buckets.get(key)

    if bucket is None:
        bucket = _Bucket(tokens=max_tokens, last_refill=now)
        _buckets[key] = bucket

    elapsed = now - bucket.last_refill

    bucket.tokens = min(
        max_tokens,
        bucket.tokens + elapsed * refill_rate,
    )

    bucket.last_refill = now

    if bucket.tokens < 1.0:
        retry_after = max(
            1,
            int((1.0 - bucket.tokens) / refill_rate),
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.tokens -= 1.0


def reset_rate_limits() -> None:
    _buckets.clear()