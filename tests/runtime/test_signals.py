from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from rath.runtime import (
    GuardedSignalBus,
    InMemorySignalBus,
    RunSignal,
    SignalKind,
)


def test_in_memory_signal_round_trip() -> None:
    bus = InMemorySignalBus()
    signal = RunSignal(
        kind=SignalKind.WAKE,
        run_id=uuid4(),
        tenant_id="tenant",
        created_at=datetime.now(timezone.utc),
    )
    bus.publish(signal)
    assert bus.receive() == signal


def test_signal_failure_does_not_change_durable_outcome() -> None:
    class Broken:
        def publish(self, signal: RunSignal) -> None:
            raise ConnectionError("redis down")

        def receive(self, *, timeout_seconds: float = 0) -> RunSignal | None:
            raise ConnectionError("redis down")

    bus = GuardedSignalBus(Broken())
    bus.publish(
        RunSignal(
            kind=SignalKind.CANCEL,
            run_id=uuid4(),
            tenant_id="tenant",
            created_at=datetime.now(timezone.utc),
        )
    )
    assert bus.receive() is None
    assert bus.failures == 2


def test_in_memory_receive_without_timeout_is_non_blocking() -> None:
    bus = InMemorySignalBus()
    assert bus.receive(timeout_seconds=0) is None
