"""Unit tests for ``rath._async.aretry.aretry_with_backoff``.

Pure async-backoff plumbing — no LLM SDK, no network. Mirrors the sync helper's
tests so async retry semantics match the contract documented for
``Provider.retry_max_attempts`` / ``Provider.retry_base_seconds``.
"""

from __future__ import annotations

import pytest

from rath._async.aretry import aretry_with_backoff
from rath._async.runtime import runtime


class _Boom(Exception):
    pass


def test_aretry_returns_first_success() -> None:
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        return "ok"

    rt = runtime()
    out = rt.run(
        aretry_with_backoff(
            fn,
            retryable=(_Boom,),
            max_attempts=3,
            base_seconds=0.0,
            jitter=False,
        )
    )
    assert out == "ok"
    assert calls["n"] == 1


def test_aretry_retries_until_success() -> None:
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Boom("transient")
        return "ok"

    async def fast_sleep(_d: float) -> None:
        return None

    rt = runtime()
    out = rt.run(
        aretry_with_backoff(
            fn,
            retryable=(_Boom,),
            max_attempts=5,
            base_seconds=0.01,
            jitter=False,
            sleep=fast_sleep,
        )
    )
    assert out == "ok"
    assert calls["n"] == 3


def test_aretry_raises_after_max_attempts() -> None:
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise _Boom(f"attempt {calls['n']}")

    async def fast_sleep(_d: float) -> None:
        return None

    rt = runtime()
    with pytest.raises(_Boom, match="attempt 3"):
        rt.run(
            aretry_with_backoff(
                fn,
                retryable=(_Boom,),
                max_attempts=3,
                base_seconds=0.01,
                jitter=False,
                sleep=fast_sleep,
            )
        )
    assert calls["n"] == 3


def test_aretry_does_not_swallow_non_retryable_exceptions() -> None:
    calls = {"n": 0}

    class _Fatal(Exception):
        pass

    async def fn():
        calls["n"] += 1
        raise _Fatal("nope")

    rt = runtime()
    with pytest.raises(_Fatal):
        rt.run(
            aretry_with_backoff(
                fn,
                retryable=(_Boom,),
                max_attempts=5,
                base_seconds=0.0,
                jitter=False,
            )
        )
    assert calls["n"] == 1


def test_aretry_calls_sleep_between_attempts() -> None:
    """Each failed-and-retried attempt must trigger one sleep."""
    delays: list[float] = []

    async def fn():
        raise _Boom("always")

    async def record(d: float) -> None:
        delays.append(d)

    rt = runtime()
    with pytest.raises(_Boom):
        rt.run(
            aretry_with_backoff(
                fn,
                retryable=(_Boom,),
                max_attempts=4,
                base_seconds=0.01,
                jitter=False,
                sleep=record,
            )
        )
    # 4 attempts → 3 sleeps; schedule is base × 2^(attempt-1).
    assert len(delays) == 3
    assert delays[0] == pytest.approx(0.01)
    assert delays[1] == pytest.approx(0.02)
    assert delays[2] == pytest.approx(0.04)
