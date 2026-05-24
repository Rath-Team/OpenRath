"""Async exponential-backoff retry helper (private; runtime-internal).

Mirrors :func:`rath.llm.retry.retry_with_backoff` but ``await``s an awaitable
factory instead of calling a synchronous function. Used by the async OpenAI /
Anthropic clients that run on :class:`rath._async.runtime.OpenRathRuntime`.

Keep the surface identical to the sync helper — same defaults, same retryable
tuple semantics, same logging — so the public retry contract documented for
``Provider.retry_max_attempts`` / ``Provider.retry_base_seconds`` carries over
unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

from rath.llm.retry import (
    DEFAULT_BASE_SECONDS,
    DEFAULT_CAP_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
)

T = TypeVar("T")

logger = logging.getLogger(__name__)

__all__ = ["aretry_with_backoff"]


async def aretry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    retryable: tuple[type[BaseException], ...],
    max_attempts: int | None = None,
    base_seconds: float | None = None,
    cap_seconds: float = DEFAULT_CAP_SECONDS,
    jitter: bool = True,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Await ``fn()`` with exponential backoff on exceptions matching ``retryable``.

    ``fn`` is a zero-arg factory returning a fresh coroutine on each attempt
    (the prior coroutine cannot be re-awaited). Backoff schedule matches the
    sync helper to keep retry semantics identical regardless of which client
    flavour the runtime invokes.
    """
    attempts = max_attempts if max_attempts is not None else DEFAULT_MAX_ATTEMPTS
    base = base_seconds if base_seconds is not None else DEFAULT_BASE_SECONDS
    if attempts < 1:
        attempts = 1

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except retryable as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            delay = min(cap_seconds, base * (2 ** (attempt - 1)))
            if jitter:
                delay += random.uniform(0.0, base)
            logger.warning(
                "aretry_with_backoff: %s on attempt %d/%d; sleeping %.2fs",
                type(exc).__name__,
                attempt,
                attempts,
                delay,
            )
            await sleep(delay)
    assert last_exc is not None
    raise last_exc
