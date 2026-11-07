"""Thin confluent-kafka helpers shared by the relay, consumers and the DLQ."""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic  # type: ignore[attr-defined]


class KafkaConfig:
    """Bootstrap servers plus an optional topic prefix (isolates tests and environments)."""

    def __init__(self, bootstrap: str, topic_prefix: str = "") -> None:
        self.bootstrap = bootstrap
        self.topic_prefix = topic_prefix
        self._known_topics: set[str] = set()
        self._producer: Producer | None = None

    def topic(self, name: str) -> str:
        return self.topic_prefix + name

    def logical(self, physical: str) -> str:
        return physical.removeprefix(self.topic_prefix)

    def producer(self) -> Producer:
        if self._producer is None:
            self._producer = Producer(
                {"bootstrap.servers": self.bootstrap, "enable.idempotence": True, "acks": "all"}
            )
        return self._producer

    def consumer_config(self, group: str) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap,
            "group.id": self.group_id(group),
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }

    def ensure_topics(self, names: Iterable[str], timeout: float = 30.0) -> None:
        """Create missing topics and wait until the broker serves metadata for all of them.

        `create_topics` can return before partition leaders are elected, and producing or
        subscribing in that window fails with UNKNOWN_TOPIC_OR_PART.
        """
        missing = sorted({self.topic(n) for n in names if self.topic(n) not in self._known_topics})
        if not missing:
            return
        admin = AdminClient({"bootstrap.servers": self.bootstrap})
        futures = admin.create_topics(
            [NewTopic(t, num_partitions=1, replication_factor=1) for t in missing]
        )
        for future in futures.values():
            try:
                future.result(timeout=timeout)
            except KafkaException as exc:
                if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
        deadline = time.monotonic() + timeout
        pending = set(missing)
        while pending:
            topics = admin.list_topics(timeout=5).topics
            pending = {
                name
                for name in pending
                if name not in topics
                or topics[name].error is not None
                or not topics[name].partitions
                or any(p.leader < 0 for p in topics[name].partitions.values())
            }
            if pending and time.monotonic() > deadline:
                raise TimeoutError(f"topics not ready after {timeout}s: {sorted(pending)}")
            if pending:
                time.sleep(0.1)
        self._known_topics.update(missing)

    def group_id(self, group: str) -> str:
        return self.topic_prefix + group

    def produce(self, messages: Iterable[tuple[str, str, bytes]]) -> None:
        """Produce (topic, key, value) messages and wait for every broker ack, or raise."""
        errors: list[KafkaError] = []

        def on_delivery(err: KafkaError | None, _msg: object) -> None:
            if err is not None:
                errors.append(err)

        producer = self.producer()
        for topic, key, value in messages:
            producer.produce(
                self.topic(topic), key=key.encode(), value=value, on_delivery=on_delivery
            )
        if producer.flush(10) > 0:
            raise KafkaException(KafkaError(KafkaError._MSG_TIMED_OUT))
        if errors:
            raise KafkaException(errors[0])

    def consume(
        self,
        topics: list[str],
        group: str,
        *,
        poll_timeout: float = 0.5,
        idle_timeout: float | None = None,
        assign_timeout: float = 30.0,
    ) -> Iterator[tuple[Consumer, Message]]:
        """Yield messages for a consumer group. The caller commits offsets.

        Stops after `idle_timeout` seconds without messages once partitions are assigned
        (None = run forever).
        """
        self.ensure_topics(topics)
        consumer = Consumer(self.consumer_config(group))
        assigned_at: list[float] = []

        def on_assign(_c: Consumer, _partitions: list[Any]) -> None:
            assigned_at.append(time.monotonic())

        consumer.subscribe([self.topic(t) for t in topics], on_assign=on_assign)
        started = last = time.monotonic()
        try:
            while True:
                msg = consumer.poll(poll_timeout)
                now = time.monotonic()
                if msg is None:
                    if not assigned_at:
                        if now - started > assign_timeout:
                            raise TimeoutError(f"no partitions assigned for group {group}")
                        continue
                    last = max(last, assigned_at[-1])
                    if idle_timeout is not None and now - last >= idle_timeout:
                        return
                    continue
                err = msg.error()
                if err is not None:
                    if err.code() == KafkaError._PARTITION_EOF:
                        continue
                    if err.code() == KafkaError.UNKNOWN_TOPIC_OR_PART and not assigned_at:
                        if now - started > assign_timeout:
                            raise KafkaException(err)
                        continue
                    raise KafkaException(err)
                last = now
                yield consumer, msg
        finally:
            consumer.close()
