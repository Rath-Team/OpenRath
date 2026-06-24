"""Offline smoke test for the dynamic-Selector example (example/11).

The example previously crashed on its first run because it called
``session.text()``, which did not exist. These tests exercise the same two
patterns the example uses -- run an agent then read its answer, and route
between self-describing workflows with a Selector -- against a scripted
executor so they run with no live LLM and guard the marquee feature in CI.
"""

from __future__ import annotations

from rath import flow
from rath.llm import (
    Provider,
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
)
from rath.session import Session
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


def _stop(content: str) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="r",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(role="assistant", content=content),
            ),
        ),
        created=0,
        model="scripted",
    )


def test_agent_forward_then_text_returns_answer() -> None:
    # Mirrors example/11: `session = chosen(session); print(session.text())`.
    agent = flow.Agent("be brief", Provider(), description="answers things")
    agent._executor_override = ScriptedSessionLoopExecutor([_stop("the answer")])

    out = agent.forward(Session.from_user_message("question?"))

    assert out.text() == "the answer"


def test_selector_routes_to_chosen_workflow() -> None:
    selector = flow.Selector(Provider())
    # Scripted router reply "1" -> pick the second candidate.
    selector._test_executor = ScriptedSessionLoopExecutor([_stop("1")])

    billing = flow.Agent("billing", Provider(), description="billing questions")
    tech = flow.Agent("tech", Provider(), description="technical questions")

    chosen = selector.forward(
        Session.from_user_message("my app crashes"), billing, tech
    )

    assert chosen is tech


def test_selector_done_returns_empty_workflow() -> None:
    selector = flow.Selector(Provider())
    # Router reply "-1" -> nothing applies / task complete.
    selector._test_executor = ScriptedSessionLoopExecutor([_stop("-1")])

    billing = flow.Agent("billing", Provider(), description="billing questions")
    tech = flow.Agent("tech", Provider(), description="technical questions")

    chosen = selector.forward(Session.from_user_message("done now"), billing, tech)

    assert isinstance(chosen, flow.EmptyWorkflow)
