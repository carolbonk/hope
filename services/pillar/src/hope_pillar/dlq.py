"""Retry with backoff, dead-letter to gop.dlq.<topic>, and replay (blueprint 7.2)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from hope_core.envelope import PillarEnvelope

from hope_pillar.contracts import DeadLetter
from hope_pillar.kafka import KafkaConfig

Handler = Callable[[PillarEnvelope], None]


class DeadLetterSink(Protocol):
    def send(self, letter: DeadLetter) -> None: ...


class InMemoryDeadLetterSink:
    def __init__(self) -> None:
        self.letters: list[DeadLetter] = []

    def send(self, letter: DeadLetter) -> None:
        self.letters.append(letter)


class KafkaDeadLetterSink:
    def __init__(self, kafka: KafkaConfig) -> None:
        self.kafka = kafka

    def send(self, letter: DeadLetter) -> None:
        self.kafka.ensure_topics([letter.dlq_topic])
        self.kafka.produce([(letter.dlq_topic, letter.key, letter.model_dump_json().encode())])


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 0.5
    factor: float = 2.0
    max_delay: float = 30.0
    sleep: Callable[[float], None] = field(default=time.sleep, compare=False)

    def delay(self, attempt: int) -> float:
        return min(self.max_delay, self.base_delay * self.factor ** (attempt - 1))


DEFAULT_RETRY = RetryPolicy()


def run_with_retry(
    handler: Handler,
    envelope: PillarEnvelope,
    *,
    consumer: str,
    sink: DeadLetterSink,
    policy: RetryPolicy = DEFAULT_RETRY,
) -> bool:
    """Run `handler`; dead-letter the event after `policy.max_attempts` failures."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            handler(envelope)
            return True
        except Exception as exc:
            if attempt == policy.max_attempts:
                sink.send(
                    DeadLetter(
                        source_topic=envelope.topic,
                        key=envelope.subject_id,
                        consumer=consumer,
                        attempts=attempt,
                        error_type=type(exc).__name__,
                        error=str(exc)[:2000],
                        envelope=envelope,
                    )
                )
                return False
            policy.sleep(policy.delay(attempt))
    return False
