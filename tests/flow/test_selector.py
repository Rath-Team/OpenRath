"""``Selector`` routes to a candidate workflow, or an EmptyWorkflow when done."""

from __future__ import annotations

from rath.flow import Agent, EmptyWorkflow, Selector
from rath.flow.agent_param import Provider
from rath.llm import RathLLMAssistantMessage, RathLLMChatChoice, RathLLMChatResponse
from rath.session import Session


def _resp(content: str) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="sel",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=content),
            ),
        ),
        created=1,
        model="scripted",
    )


class _ScriptedOnce:
    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, req):  # type: ignore[no-untyped-def]
        return _resp(self._content)

    def dispatch_tool(self, session, tool, arguments):  # type: ignore[no-untyped-def]
        return tool(session, dict(arguments or {}))

    def tool_schemas(self):  # type: ignore[no-untyped-def]
        return ()


def _selector(content: str) -> Selector:
    s = Selector(Provider())
    # Backend-free seam: passed straight to select_session(..., executor=...).
    s._test_executor = _ScriptedOnce(content)  # type: ignore[attr-defined]
    return s


def _branches() -> tuple[Agent, Agent, Agent]:
    p = Provider()
    return (
        Agent("a", p, description="Billing"),
        Agent("b", p, description="Technical"),
        Agent("c", p, description="Wrap up"),
    )


def test_empty_workflow_returns_session_unchanged() -> None:
    s = Session.from_user_message("x")
    assert EmptyWorkflow().forward(s) is s


def test_selector_routes_to_indexed_workflow() -> None:
    sel = _selector("1")
    a, b, c = _branches()
    assert sel.forward(Session.from_user_message("x"), a, b, c) is b


def test_selector_returns_empty_workflow_on_minus_one() -> None:
    sel = _selector("-1")
    a, b, c = _branches()
    assert isinstance(
        sel.forward(Session.from_user_message("x"), a, b, c), EmptyWorkflow
    )


def test_selector_returns_empty_workflow_with_no_candidates() -> None:
    sel = _selector("0")
    assert isinstance(sel.forward(Session.from_user_message("x")), EmptyWorkflow)
