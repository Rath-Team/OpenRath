"""``select_session`` primitive: numbered-menu routing decision via one completion."""

from __future__ import annotations

from rath.llm import RathLLMAssistantMessage, RathLLMChatChoice, RathLLMChatResponse
from rath.llm.provider import Provider
from rath.session import Session, select_session
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


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


def _call(content: str) -> tuple[int, str]:
    user = Session.from_user_message("My invoice is wrong.")
    rubric = Session.from_agent_prompt("Route to the best workflow.")
    return select_session(
        user,
        rubric,
        "Billing and invoices",
        "Technical troubleshooting",
        "Wrap up the conversation",
        agent_provider=Provider(),
        executor=ScriptedSessionLoopExecutor([_resp(content)]),
    )


def test_select_session_returns_index_and_description() -> None:
    assert _call("0") == (0, "Billing and invoices")


def test_select_session_minus_one_means_none() -> None:
    assert _call("-1") == (-1, "")


def test_select_session_clamps_out_of_range_to_minus_one() -> None:
    assert _call("9") == (-1, "")


def test_select_session_clamps_unparseable_to_minus_one() -> None:
    assert _call("I think billing") == (-1, "")


def test_select_session_parses_leading_integer_token() -> None:
    # Model may answer "1." or "1)"; first integer token wins.
    assert _call("1.") == (1, "Technical troubleshooting")
