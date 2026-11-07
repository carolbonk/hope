from __future__ import annotations

import random
from datetime import UTC, datetime

import httpx
import pytest
from hope_ingestion.http import (
    PoliteClient,
    RateLimitPolicy,
    RetryPolicy,
    SourceUnavailableError,
    TokenBucket,
    retry_after_seconds,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def polite(handler: httpx.MockTransport, clock: FakeClock, **retry: float) -> PoliteClient:
    return PoliteClient(
        httpx.Client(transport=handler),
        RateLimitPolicy(rate_per_sec=1000, burst=100),
        RetryPolicy(jitter=0, **retry),  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        rng=random.Random(0),
    )


def test_token_bucket_spaces_requests() -> None:
    clock = FakeClock()
    bucket = TokenBucket(RateLimitPolicy(rate_per_sec=2, burst=2), clock, clock.sleep)
    for _ in range(4):
        bucket.acquire()
    assert clock.sleeps == pytest.approx([0.5, 0.5])


def test_retry_after_seconds_and_http_date() -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    assert retry_after_seconds("7") == 7
    assert retry_after_seconds("Sat, 07 Nov 2026 12:00:30 GMT", now) == 30
    assert retry_after_seconds("soon") is None
    assert retry_after_seconds(None) is None


def test_honours_retry_after_on_429() -> None:
    calls = iter([httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200)])
    clock = FakeClock()
    client = polite(httpx.MockTransport(lambda request: next(calls)), clock)
    assert client.request("GET", "https://example.test").status_code == 200
    assert clock.sleeps == [3.0]


def test_exponential_backoff_on_5xx_then_gives_up() -> None:
    clock = FakeClock()
    client = polite(httpx.MockTransport(lambda request: httpx.Response(503)), clock, max_attempts=3)
    with pytest.raises(SourceUnavailableError):
        client.request("GET", "https://example.test")
    assert clock.sleeps == [0.5, 1.0]


def test_no_retry_on_client_errors() -> None:
    hits: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(1)
        return httpx.Response(400)

    with pytest.raises(httpx.HTTPStatusError):
        polite(httpx.MockTransport(handler), FakeClock()).request("GET", "https://example.test")
    assert len(hits) == 1


def test_transport_errors_are_retried() -> None:
    attempts = iter([httpx.ConnectError("down"), None])

    def handler(request: httpx.Request) -> httpx.Response:
        error = next(attempts)
        if error:
            raise error
        return httpx.Response(200)

    clock = FakeClock()
    assert polite(httpx.MockTransport(handler), clock).request("GET", "https://x.test").is_success
    assert clock.sleeps == [0.5]
