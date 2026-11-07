"""Polite HTTP for source connectors: token-bucket rate limiting and retry with backoff that
honours Retry-After (blueprint 6.1, 8.5)."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

Clock = Callable[[], float]
Sleep = Callable[[float], None]

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RateLimitPolicy:
    rate_per_sec: float
    burst: int = 1


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_s: float = 0.5
    max_delay_s: float = 60.0
    jitter: float = 0.25

    def backoff(self, attempt: int, rng: random.Random) -> float:
        delay = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
        return float(delay * (1 + rng.uniform(-self.jitter, self.jitter)))


class TokenBucket:
    """In-process token bucket. A Redis-backed bucket can replace it for multi-worker runs."""

    def __init__(
        self, policy: RateLimitPolicy, clock: Clock = time.monotonic, sleep: Sleep = time.sleep
    ) -> None:
        self.policy = policy
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(policy.burst)
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        self._tokens = min(self.policy.burst, self._tokens + elapsed * self.policy.rate_per_sec)
        self._updated = now

    def acquire(self) -> None:
        with self._lock:
            self._refill()
            if self._tokens < 1:
                self._sleep((1 - self._tokens) / self.policy.rate_per_sec)
                self._refill()
            self._tokens -= 1


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


class SourceUnavailableError(RuntimeError):
    """Retries are exhausted for a source; the circuit for it should open."""


@dataclass
class PoliteClient:
    client: httpx.Client
    rate_limit: RateLimitPolicy
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    clock: Clock = time.monotonic
    sleep: Sleep = time.sleep
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        self.bucket = TokenBucket(self.rate_limit, self.clock, self.sleep)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(1, self.retry.max_attempts + 1):
            self.bucket.acquire()
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == self.retry.max_attempts:
                    raise SourceUnavailableError(f"{method} {url}: {exc}") from exc
                self.sleep(self.retry.backoff(attempt, self.rng))
                continue
            if response.status_code not in RETRYABLE_STATUS:
                response.raise_for_status()
                return response
            if attempt == self.retry.max_attempts:
                raise SourceUnavailableError(f"{method} {url}: HTTP {response.status_code}")
            hinted = retry_after_seconds(response.headers.get("Retry-After"))
            delay = self.retry.backoff(attempt, self.rng) if hinted is None else hinted
            self.sleep(min(delay, self.retry.max_delay_s))
        raise AssertionError("unreachable")
