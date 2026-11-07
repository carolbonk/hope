"""Long-running pillar workers: `hope-pillar-relay` and `hope-pillar-projector`."""

from __future__ import annotations

import logging
import signal
import threading

from hope_core.settings import get_settings

from hope_pillar.kafka import KafkaConfig
from hope_pillar.outbox import OutboxRelay
from hope_pillar.pillar import KafkaPostgresPillar
from hope_pillar.projector import GROUP, Projector


def relay() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        OutboxRelay(
            KafkaConfig(settings.kafka_bootstrap), settings.database_system_url
        ).run_forever(stop)
    except KeyboardInterrupt:
        stop.set()


def projector() -> None:
    logging.basicConfig(level=logging.INFO)
    pillar = KafkaPostgresPillar()
    pillar.consume(Projector.EVENT_TYPES, GROUP, Projector(pillar.system_url))
