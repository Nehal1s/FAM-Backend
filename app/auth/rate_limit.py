"""In-memory token-bucket rate limiter (single EC2 instance)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.auth.base import AuthContext
from app.config import get_settings


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


_buckets: dict[str, _Bucket] = {}


def check_rate_limit(auth: AuthContext) -> None:
    settings = get_settings()
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
    bucket.tokens = min(max_tokens, bucket.tokens + elapsed * refill_rate)
    bucket.last_refill = now

    if bucket.tokens < 1.0:
        retry_after = max(1, int((1.0 - bucket.tokens) / refill_rate))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.tokens -= 1.0


def reset_rate_limits() -> None:
    _buckets.clear()
