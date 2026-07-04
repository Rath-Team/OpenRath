"""Round-trip fidelity for :mod:`rath.backend.persistence.spec_json`.

``spec_to_jsonable`` preserves the ``None``-vs-empty distinction, so
``spec_from_jsonable`` must too: an empty ``entrypoint`` / ``env`` should
survive the round trip as an empty collection rather than collapsing to
``None``.
"""

from __future__ import annotations

from datetime import timedelta

from rath.backend.abc import BackendSandboxSpec
from rath.backend.persistence.spec_json import spec_from_jsonable, spec_to_jsonable


def test_none_spec_round_trips() -> None:
    assert spec_to_jsonable(None) is None
    assert spec_from_jsonable(None) is None


def test_full_spec_round_trips() -> None:
    spec = BackendSandboxSpec(
        image="python:3.12",
        entrypoint=("bash", "-lc"),
        env={"K": "V", "N": "1"},
        timeout=timedelta(seconds=30),
        working_dir="/ws",
    )
    back = spec_from_jsonable(spec_to_jsonable(spec))
    assert back == spec


def test_empty_entrypoint_and_env_survive_round_trip() -> None:
    """Empty collections must stay empty, not decay to ``None``."""
    spec = BackendSandboxSpec(entrypoint=(), env={})
    back = spec_from_jsonable(spec_to_jsonable(spec))
    assert back is not None
    assert back.entrypoint == ()
    assert back.env == {}


def test_unset_fields_stay_none() -> None:
    spec = BackendSandboxSpec()
    back = spec_from_jsonable(spec_to_jsonable(spec))
    assert back == spec
    assert back is not None
    assert back.entrypoint is None
    assert back.env is None
    assert back.timeout is None


def test_zero_timeout_round_trips() -> None:
    """A zero timedelta is distinct from an unset timeout and must be kept."""
    spec = BackendSandboxSpec(timeout=timedelta(0))
    back = spec_from_jsonable(spec_to_jsonable(spec))
    assert back is not None
    assert back.timeout == timedelta(0)
