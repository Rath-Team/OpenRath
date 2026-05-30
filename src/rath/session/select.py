"""Workflow routing decision via one-shot LLM call (:func:`select_session`)."""

from __future__ import annotations

import re
from dataclasses import replace

from rath.llm import Provider, RathLLMChatResponse, RathLLMMessage
from rath.session.chat_request_build import provider_into_chat_request
from rath.session.chunk import chunk_table_to_messages
from rath.session.loop import SessionLoopExecutor, resolve_executor
from rath.session.session import Session

_DEFAULT_SELECT_INSTRUCTION = (
    "You are a router. Given the conversation above and a numbered menu of candidate "
    "workflows, reply with ONLY the single integer index of the best-matching workflow. "
    "Reply -1 if none of them applies or the task is already complete. Output the "
    "integer and nothing else."
)

_INT_TOKEN = re.compile(r"-?\d+")


def _completion_body(resp: RathLLMChatResponse) -> str:
    choice = resp.primary_choice
    msg = choice.message
    if msg.tool_calls:
        raise RuntimeError(
            "select_session: model returned tool calls but tools are disabled"
        )
    fr = choice.finish_reason
    if fr not in ("stop", "length", "content_filter"):
        raise RuntimeError(f"select_session: unexpected finish_reason={fr!r}")
    content = msg.content
    if content is None or not str(content).strip():
        raise RuntimeError("select_session: empty model content")
    return str(content)


def _parse_index(body: str, count: int) -> int:
    """First integer token in ``body``; out-of-range / missing -> -1."""

    m = _INT_TOKEN.search(body)
    if m is None:
        return -1
    idx = int(m.group())
    return idx if 0 <= idx < count else -1


def select_session(
    user_session: Session,
    agent_session: Session,
    *workflow_descriptions: str,
    agent_provider: Provider,
    executor: SessionLoopExecutor | None = None,
) -> tuple[int, str]:
    """LLM picks the best-matching description for the current user session.

    Folds ``agent_session`` (the selection rubric) + ``user_session`` (current state) +
    a numbered menu of ``workflow_descriptions`` into a single completion
    (``tools=None``, ``tool_choice="none"``), parses the chosen 0-based index, and
    returns ``(index, workflow_descriptions[index])``.

    Returns ``(-1, "")`` when the model replies -1, gives no parseable index, or returns
    an out-of-range index — meaning no candidate fits or the session needs no further
    workflow. Creates no new :class:`Session` and stamps no lineage.
    """

    if not workflow_descriptions:
        return (-1, "")

    # Join lazy input sessions before reading their chunk_table.
    if user_session._pending is not None:
        user_session.synchronize()
    if agent_session._pending is not None:
        agent_session.synchronize()

    executor = resolve_executor(
        agent_provider=agent_provider, executor=executor, on_event=None
    )

    menu = "\n".join(f"{i}: {desc}" for i, desc in enumerate(workflow_descriptions))
    head = chunk_table_to_messages(agent_session.chunk_table)
    tail = chunk_table_to_messages(user_session.chunk_table)
    messages: tuple[RathLLMMessage, ...] = (
        *head,
        *tail,
        RathLLMMessage(
            role="user",
            content=f"Candidate workflows:\n{menu}\n\nReply with one index, or -1.",
        ),
    )

    prefs = replace(agent_provider, tool_choice=None)
    req = provider_into_chat_request(messages, None, prefs, default_tool_choice="none")

    resp = executor.complete(req)
    idx = _parse_index(_completion_body(resp), len(workflow_descriptions))
    return (idx, workflow_descriptions[idx]) if idx >= 0 else (-1, "")


__all__ = ["select_session"]
