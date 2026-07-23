from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rath.backend import ToolExecutionFailure
from rath.flow.tool import FlowToolCall, ToolPolicy, dispatch_flow_tool
from rath.session import Session


class _Echo(FlowToolCall):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object"}

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        return {"echoed": dict(arguments)}


def _session() -> Session:
    return Session.from_user_message("u")


def test_no_policy_allows_everything() -> None:
    assert not dispatch_flow_tool(_session(), _Echo(), {"a": 1}).failed


def test_tool_outside_the_allowlist_is_denied() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(allow_tools=frozenset({"other"}))
    result = dispatch_flow_tool(session, _Echo(), {})
    assert result.failed
    assert isinstance(result.raw, ToolExecutionFailure)
    assert result.raw.kind == "tool_policy_denied"
    assert "echo" in result.raw.message


def test_denial_does_not_execute_the_tool() -> None:
    calls: list[int] = []

    class _Counting(_Echo):
        def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
            calls.append(1)
            return {}

    session = _session()
    session.tool_policy = ToolPolicy(allow_tools=frozenset())
    dispatch_flow_tool(session, _Counting(), {})
    assert calls == []


def test_path_outside_fs_roots_is_denied() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(fs_roots=("/workspace",))
    assert dispatch_flow_tool(session, _Echo(), {"path": "/etc/passwd"}).failed
    assert not dispatch_flow_tool(session, _Echo(), {"path": "/workspace/a.py"}).failed


def test_traversal_out_of_an_fs_root_is_denied() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(fs_roots=("/workspace",))
    result = dispatch_flow_tool(session, _Echo(), {"path": "/workspace/../etc/passwd"})
    assert result.failed


def test_denied_command_is_refused() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(command_deny=("rm",))
    result = dispatch_flow_tool(session, _Echo(), {"cmd": "rm -rf /"})
    assert result.failed
    assert isinstance(result.raw, ToolExecutionFailure)
    assert result.raw.kind == "tool_policy_denied"


def test_command_allowlist_refuses_everything_else() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(command_allow=("pytest",))
    assert not dispatch_flow_tool(session, _Echo(), {"cmd": "pytest -q"}).failed
    assert dispatch_flow_tool(session, _Echo(), {"cmd": "curl example.com"}).failed


def test_argv_style_commands_are_checked_too() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(command_deny=("rm",))
    assert dispatch_flow_tool(session, _Echo(), {"cmd": ["rm", "-rf", "/"]}).failed


def test_max_calls_is_enforced_per_session() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(max_calls=2)
    tool = _Echo()
    assert not dispatch_flow_tool(session, tool, {}).failed
    assert not dispatch_flow_tool(session, tool, {}).failed
    third = dispatch_flow_tool(session, tool, {})
    assert third.failed
    assert isinstance(third.raw, ToolExecutionFailure)
    assert "max_calls" in third.raw.message


def test_a_denied_call_does_not_consume_the_call_budget() -> None:
    session = _session()
    session.tool_policy = ToolPolicy(allow_tools=frozenset({"other"}), max_calls=1)
    dispatch_flow_tool(session, _Echo(), {})
    # The denial above never ran, so the one permitted call must still be available.
    session.tool_policy = ToolPolicy(max_calls=1)
    assert not dispatch_flow_tool(session, _Echo(), {}).failed
