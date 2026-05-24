"""Canary test for the OpenViking skip-gating fixture.

If this test passes, then for the rest of this directory:

- ``openviking`` is importable,
- ``$OPEN_VIKING_URL/health`` (default ``http://127.0.0.1:1933``) returns
  ``{"healthy": true}``,
- ``OPEN_VIKING_ROOT_API_KEY`` is resolvable (env or ``~/.openviking/ov.conf``).

Any of those failing here means the entire backends/ directory is skipped
by ``_openviking_canary``, so the rest of the OpenViking suite never gets
a chance to fail noisily on connection errors.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

pytestmark = pytest.mark.openviking


def test_openviking_health(openviking_url: str) -> None:
    with urllib.request.urlopen(f"{openviking_url}/health", timeout=2.0) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    assert payload.get("healthy") is True, payload


def test_openviking_sdk_imports() -> None:
    import openviking as ov

    assert hasattr(ov, "SyncHTTPClient")
    assert hasattr(ov, "OpenViking")


def test_openviking_root_api_key_present(openviking_root_api_key: str) -> None:
    assert openviking_root_api_key  # non-empty
