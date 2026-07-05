"""P4.4 — run_session_loop provider precedence.

- explicit agent_provider= wins (Agent path unchanged);
- when omitted, the loop falls back to the session-bound provider
  (session.to(Provider(...)));
- omitting both raises a clear ValueError before any model call.

Uses a fake executor so no network/key is needed (this tests provider
*resolution*, not a live completion).
"""

from __future__ import annotations

import pytest

from rath.llm.chat_response import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
    RathLLMTokenUsage,
)
from rath.llm.provider import Provider
from rath.session.loop import run_session_loop
from rath.session.session import Session


class _RecordingExecutor:
    """Minimal SessionLoopExecutor that records the request's resolved model.

    The effective provider is folded into the chat request (model etc.) before
    ``complete`` runs, so ``req.model`` reflects which provider won.
    """

    def __init__(self) -> None:
        self.seen_model: str | None = None

    def complete(self, req):  # type: ignore[no-untyped-def]
        self.seen_model = req.model
        return RathLLMChatResponse(
            id="resp-1",
            choices=(
                RathLLMChatChoice(
                    index=0,
                    finish_reason="stop",
                    message=RathLLMAssistantMessage(content="done"),
                ),
            ),
            created=0,
            model=req.model or "",
            usage=RathLLMTokenUsage(
                prompt_tokens=1, completion_tokens=1, total_tokens=2
            ),
        )

    def tool_schemas(self):  # type: ignore[no-untyped-def]
        return ()

    def dispatch_tool(self, session, tool, arguments):  # type: ignore[no-untyped-def]
        raise AssertionError("no tools in this test")


def _run(user: Session, agent: Session, **kw):  # type: ignore[no-untyped-def]
    ex = _RecordingExecutor()
    out = run_session_loop(user, agent, executor=ex, lazy=False, **kw)
    out.synchronize()
    return out, ex


def test_explicit_agent_provider_wins() -> None:
    user = Session.from_user_message("hi").to(Provider(model="SESSION", api_key="s"))
    agent = Session.from_agent_prompt("sys")
    _out, ex = _run(user, agent, agent_provider=Provider(model="AGENT", api_key="a"))
    assert ex.seen_model == "AGENT"


def test_session_provider_fallback() -> None:
    user = Session.from_user_message("hi").to(Provider(model="SESSION", api_key="s"))
    agent = Session.from_agent_prompt("sys")
    _out, ex = _run(user, agent)  # no agent_provider
    assert ex.seen_model == "SESSION"


def test_missing_both_raises() -> None:
    user = Session.from_user_message("hi")  # no provider bound
    agent = Session.from_agent_prompt("sys")
    with pytest.raises(ValueError, match="no provider"):
        run_session_loop(user, agent, executor=_RecordingExecutor(), lazy=False)
