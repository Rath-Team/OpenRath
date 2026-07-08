"""P2.1 — central EnvSpec registry.

Every environment variable OpenRath reads is declared once with a kind
(secret/routing/flag), its consumers, and a default. The registry is a
single-read + documentation layer; it does NOT change the documented
precedence (explicit field > env > config), which callers express via
``resolve(name, *explicit)``.
"""

from __future__ import annotations

import pytest

from rath.config.env import (
    EnvKind,
    env_flag,
    env_reference_rows,
    env_value,
    get_env_spec,
    resolve_env,
)


def test_declared_vars_present() -> None:
    # A representative sample of the inventory must be declared.
    for name in (
        "OPENRATH_HOME",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_DEFAULT_MODEL",
        "ANTHROPIC_API_KEY",
        "LITELLM_API_KEY",
        "OPEN_SANDBOX_DOMAIN",
        "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND",
    ):
        spec = get_env_spec(name)
        assert spec.name == name
        assert spec.kind in EnvKind
        assert spec.consumers  # non-empty description of who reads it


def test_secret_vars_marked_secret() -> None:
    assert get_env_spec("OPENAI_API_KEY").kind is EnvKind.SECRET
    assert get_env_spec("ANTHROPIC_API_KEY").kind is EnvKind.SECRET
    assert get_env_spec("OPENAI_BASE_URL").kind is EnvKind.ROUTING
    assert get_env_spec("RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND").kind is EnvKind.FLAG


def test_env_value_reads_and_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  sk-abc  ")
    assert env_value("OPENAI_API_KEY") == "sk-abc"
    monkeypatch.setenv("OPENAI_API_KEY", "   ")  # whitespace-only → None
    assert env_value("OPENAI_API_KEY") is None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert env_value("OPENAI_API_KEY") is None


def test_unknown_var_is_typed_error() -> None:
    with pytest.raises(KeyError, match="not a declared"):
        env_value("NOT_A_REAL_VAR")
    with pytest.raises(KeyError):
        get_env_spec("NOT_A_REAL_VAR")


def test_resolve_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    # explicit wins over env
    assert resolve_env("OPENAI_API_KEY", "sk-explicit") == "sk-explicit"
    # empty explicit falls through to env
    assert resolve_env("OPENAI_API_KEY", None, "") == "sk-from-env"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # nothing set → empty string (resolve_credential contract)
    assert resolve_env("OPENAI_API_KEY", None) == ""


def test_flag_coercion(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND"
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(name, truthy)
        assert env_flag(name) is True
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(name, falsy)
        assert env_flag(name) is False
    monkeypatch.delenv(name, raising=False)
    assert env_flag(name) is False  # default


def test_reference_rows_sorted_and_complete() -> None:
    rows = env_reference_rows()
    names = [r["name"] for r in rows]
    assert names == sorted(names)
    # Every row documents name/kind/consumers/default keys.
    for r in rows:
        assert set(r) >= {"name", "kind", "consumers", "default"}
    assert "OPENAI_API_KEY" in names
