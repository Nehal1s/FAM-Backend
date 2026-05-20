"""CloudWatch custom metrics — no-op when disabled (local dev)."""

from __future__ import annotations

import time
from functools import lru_cache

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def _client():
    import boto3

    settings = get_settings()
    return boto3.client("cloudwatch", region_name=settings.aws_region)


def record_latency(metric_name: str, duration_ms: float, dimensions: dict[str, str] | None = None) -> None:
    settings = get_settings()
    if not settings.cloudwatch_enabled:
        return

    dims = [{"Name": k, "Value": v} for k, v in (dimensions or {}).items()]
    try:
        _client().put_metric_data(
            Namespace=settings.cloudwatch_namespace,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": duration_ms,
                    "Unit": "Milliseconds",
                    "Dimensions": dims,
                }
            ],
        )
    except Exception:
        logger.exception("cloudwatch_metric_failed", metric=metric_name)


def record_error(metric_name: str, dimensions: dict[str, str] | None = None) -> None:
    settings = get_settings()
    if not settings.cloudwatch_enabled:
        return

    dims = [{"Name": k, "Value": v} for k, v in (dimensions or {}).items()]
    try:
        _client().put_metric_data(
            Namespace=settings.cloudwatch_namespace,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": dims,
                }
            ],
        )
    except Exception:
        logger.exception("cloudwatch_metric_failed", metric=metric_name)


class LatencyTimer:
    def __init__(self, metric_name: str, dimensions: dict[str, str] | None = None) -> None:
        self._metric_name = metric_name
        self._dimensions = dimensions
        self._start = 0.0

    def __enter__(self) -> "LatencyTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000
        record_latency(self._metric_name, duration_ms, self._dimensions)
