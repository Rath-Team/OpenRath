from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from rath.runtime import RedisSignalBus, RunSignal, SignalKind

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENRATH_TEST_REDIS_URL"),
    reason="OPENRATH_TEST_REDIS_URL is not configured",
)


def test_redis_signal_real_round_trip() -> None:
    namespace = f"openrath-test-{uuid4().hex}"
    bus = RedisSignalBus(os.environ["OPENRATH_TEST_REDIS_URL"], namespace=namespace)
    signal = RunSignal(
        kind=SignalKind.CANCEL,
        run_id=uuid4(),
        tenant_id="tenant",
        created_at=datetime.now(timezone.utc),
    )
    bus.publish(signal)
    assert bus.receive(timeout_seconds=1) == signal
