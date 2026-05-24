"""Token usage accumulation and budget guard for the session loop."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import pytest

from rath.backend import get
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.tool import FlowToolCall
from rath.llm import (
    BudgetExceededError,
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
    RathLLMTokenUsage,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
)
from rath.session import Session, run_session_loop, session_registry
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    yield
    session_registry().set_active(None)


def _stop_response(*, prompt: int, completion: int) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="usage-test",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content="ok"),
            ),
        ),
        created=1,
        model="scripted",
        usage=RathLLMTokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


def test_cumulative_usage_starts_none_and_accumulates() -> None:
    """One scripted completion with usage produces a Session.cumulative_usage."""
    executor = ScriptedSessionLoopExecutor([_stop_response(prompt=10, completion=20)])
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )
    assert out.cumulative_usage is not None
    assert out.cumulative_usage.prompt_tokens == 10
    assert out.cumulative_usage.completion_tokens == 20
    assert out.cumulative_usage.total_tokens == 30


def test_usage_remains_none_when_provider_reports_no_usage() -> None:
    no_usage = RathLLMChatResponse(
        id="x",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content="ok"),
            ),
        ),
        created=1,
        model="scripted",
        usage=None,
    )
    executor = ScriptedSessionLoopExecutor([no_usage])
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )
    assert out.cumulative_usage is None


def test_budget_exceeded_invokes_callback() -> None:
    """Provider.on_budget_exceeded is called once total_tokens crosses the cap."""
    seen: list[tuple[object, RathLLMTokenUsage]] = []

    def _cb(sess: object, usage: RathLLMTokenUsage) -> None:
        seen.append((sess, usage))

    executor = ScriptedSessionLoopExecutor([_stop_response(prompt=100, completion=50)])
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(budget_total_tokens=100, on_budget_exceeded=_cb),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )
        out.synchronize()
    assert len(seen) == 1
    cb_session, cb_usage = seen[0]
    assert cb_session is out
    assert cb_usage.total_tokens == 150


def test_budget_callback_raising_aborts_loop() -> None:
    """Raising BudgetExceededError from the callback aborts run_session_loop."""

    def _hard_stop(sess: object, usage: RathLLMTokenUsage) -> None:
        raise BudgetExceededError(
            f"hit cap; cumulative={usage.total_tokens}",
        )

    # First response triggers the budget; a second response would otherwise
    # be consumed if the loop continued.
    executor = ScriptedSessionLoopExecutor(
        [
            _stop_response(prompt=200, completion=50),
            _stop_response(prompt=999, completion=999),
        ]
    )
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(budget_total_tokens=100, on_budget_exceeded=_hard_stop),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )
        with pytest.raises(BudgetExceededError, match="hit cap"):
            out.synchronize()


class _NoopTool(FlowToolCall):
    """Trivial FlowToolCall for budget tests; no sandbox interaction."""

    @property
    def name(self) -> str:
        return "noop"

    @property
    def description(self) -> str | None:
        return "noop"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object", "properties": {"x": {"type": "string"}}}

    def __call__(
        self, session: Session, arguments: Mapping[str, Any]
    ) -> dict[str, bool]:
        del session, arguments
        return {"ok": True}


def _tool_call_response(
    tcid: str, *, prompt: int, completion: int
) -> RathLLMChatResponse:
    """Tool-call response carrying usage, so the loop runs another round."""
    body = {"x": tcid}
    return RathLLMChatResponse(
        id=f"budget-tc-{tcid}",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="tool_calls",
                message=RathLLMAssistantMessage(
                    tool_calls=(
                        RathLLMToolCallPart(
                            id=tcid,
                            type="function",
                            function=RathLLMToolCallFunction(
                                name="noop",
                                arguments=json.dumps(body),
                                arguments_parsed=body,
                                arguments_parse_error=False,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        created=0,
        model="scripted",
        usage=RathLLMTokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


def test_budget_callback_fires_only_on_first_crossing() -> None:
    """Across a multi-round tool-calling loop, ``on_budget_exceeded`` must fire
    exactly once even if cumulative usage stays above the cap for every
    subsequent completion (the docstring contract: latched per session).
    """
    seen: list[int] = []

    def _cb(_sess: object, usage: RathLLMTokenUsage) -> None:
        seen.append(usage.total_tokens)

    noop = _NoopTool()

    # Round 1: 60 tokens (still under 100 cap).
    # Round 2: +60 = 120 (first crossing — fires).
    # Round 3: +60 = 180 (already above — must NOT re-fire).
    # Round 4: +5 = 185, stop. (also must NOT re-fire).
    executor = ScriptedSessionLoopExecutor(
        [
            _tool_call_response("tc1", prompt=30, completion=30),
            _tool_call_response("tc2", prompt=30, completion=30),
            _tool_call_response("tc3", prompt=30, completion=30),
            _stop_response(prompt=3, completion=2),
        ]
    )
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(budget_total_tokens=100, on_budget_exceeded=_cb),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            tools=[noop],
            executor=executor,
        )
        out.synchronize()

    assert len(seen) == 1, f"callback fired {len(seen)}x, want exactly 1"
    assert seen[0] == 120, (
        "callback should fire on the first round that pushes total past the cap"
    )
    assert out.cumulative_usage is not None
    assert out.cumulative_usage.total_tokens == 185


def test_budget_warning_emits_only_on_first_crossing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same latch behavior when no callback is set: warn once, not per round."""

    noop = _NoopTool()

    executor = ScriptedSessionLoopExecutor(
        [
            _tool_call_response("tc1", prompt=80, completion=40),
            _tool_call_response("tc2", prompt=80, completion=40),
            _stop_response(prompt=10, completion=10),
        ]
    )
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(budget_total_tokens=100),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        with caplog.at_level(logging.WARNING, logger="rath.session.loop"):
            out = run_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                tools=[noop],
                executor=executor,
            )
            out.synchronize()

    budget_warnings = [
        rec for rec in caplog.records if "budget_total_tokens" in rec.message
    ]
    assert len(budget_warnings) == 1, (
        f"expected exactly one budget warning across {len(executor._queue) + 3} "
        f"completions, got {len(budget_warnings)}"
    )


def test_budget_without_callback_emits_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No callback set: still warn so the overrun is at least visible."""
    executor = ScriptedSessionLoopExecutor([_stop_response(prompt=200, completion=0)])
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(budget_total_tokens=100),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        with caplog.at_level(logging.WARNING, logger="rath.session.loop"):
            out = run_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
            )
            out.synchronize()

    assert out.cumulative_usage is not None
    assert any("budget_total_tokens" in rec.message for rec in caplog.records)
