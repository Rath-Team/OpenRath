"""Registry API; ``registry_snapshot`` restores global state after each test."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from rath.backend import (
    Backend,
    BackendNotFound,
    BackendSandbox,
    BackendSandboxSpec,
    BackendTool,
    Capabilities,
    IsolationLevel,
    ToolResult,
    current,
    get,
    get_class,
    is_available,
    list_names,
    preferred,
    register,
    set_default,
)
from rath.backend.registry import _DEFAULT, _INSTANCES, _REGISTRY


@pytest.fixture
def registry_snapshot() -> Iterator[None]:
    """Save and restore private registry maps so tests can register fakes."""
    saved = dict(_REGISTRY)
    saved_default = dict(_DEFAULT)
    saved_instances = dict(_INSTANCES)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(saved)
    _DEFAULT.clear()
    _DEFAULT.update(saved_default)
    _INSTANCES.clear()
    _INSTANCES.update(saved_instances)


class _FakeBase(Backend):
    """Minimal Backend subclass used purely for registry tests."""

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> Capabilities:
        return Capabilities(
            isolation=IsolationLevel.PROCESS,
            supports_command=False,
            supports_filesystem=False,
            supports_code_interpreter=False,
        )

    @classmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        return frozenset()

    def sandbox_count(self) -> int:
        return 0

    async def _aopen(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        raise NotImplementedError

    async def _aclose(self, sandbox: BackendSandbox) -> None:
        raise NotImplementedError

    async def _adispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        raise NotImplementedError


class _UnavailableFake(_FakeBase):
    @classmethod
    def is_available(cls) -> bool:
        return False


def test_local_registered_at_import(registry_snapshot: None) -> None:
    """Importing ``rath.backend`` must auto-register the ``local`` backend."""
    assert "local" in list_names()


def test_register_assigns_name_attribute(registry_snapshot: None) -> None:
    Reg = register("test_alpha")(type("Reg", (_FakeBase,), {}))
    assert Reg.name == "test_alpha"


def test_register_duplicate_raises(registry_snapshot: None) -> None:
    register("test_dup")(type("R1", (_FakeBase,), {}))
    with pytest.raises(ValueError):
        register("test_dup")(type("R2", (_FakeBase,), {}))


def test_get_returns_singleton_instance(registry_snapshot: None) -> None:
    register("test_g")(type("R", (_FakeBase,), {}))
    a = get("test_g")
    b = get("test_g")
    assert a is b
    assert isinstance(a, _FakeBase)


def test_get_class_returns_class(registry_snapshot: None) -> None:
    Cls = register("test_gc")(type("R", (_FakeBase,), {}))
    assert get_class("test_gc") is Cls


def test_get_unknown_raises(registry_snapshot: None) -> None:
    with pytest.raises(BackendNotFound):
        get("nope")


def test_is_available_for_unknown_returns_false() -> None:
    assert is_available("definitely-not-registered") is False


def test_is_available_consults_class_method(registry_snapshot: None) -> None:
    register("test_avail_yes")(type("Y", (_FakeBase,), {}))
    register("test_avail_no")(type("N", (_UnavailableFake,), {}))
    assert is_available("test_avail_yes") is True
    assert is_available("test_avail_no") is False


def test_preferred_picks_first_available(registry_snapshot: None) -> None:
    register("test_p_no")(type("N", (_UnavailableFake,), {}))
    register("test_p_yes")(type("Y", (_FakeBase,), {}))
    chosen = preferred(["test_p_no", "test_p_yes", "local"])
    assert chosen.name == "test_p_yes"


def test_preferred_raises_when_none_available(registry_snapshot: None) -> None:
    register("test_x")(type("N", (_UnavailableFake,), {}))
    with pytest.raises(BackendNotFound):
        preferred(["test_x", "still-missing"])


def test_set_default_and_current(registry_snapshot: None) -> None:
    register("test_default")(type("D", (_FakeBase,), {}))
    set_default("test_default")
    assert isinstance(current(), _FakeBase)


def test_set_default_unknown_raises(registry_snapshot: None) -> None:
    with pytest.raises(BackendNotFound):
        set_default("ghost")


def test_current_without_default_raises(registry_snapshot: None) -> None:
    _DEFAULT.clear()
    with pytest.raises(BackendNotFound):
        current()
