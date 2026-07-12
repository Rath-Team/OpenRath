"""Default SessionLoopExecutor: blocking LLM completions plus sandbox tool dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rath.flow.tool import FlowToolCall, dispatch_flow_tool
from rath.llm import (
    ChatClient,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMFunctionTool,
)
from rath.session.session import Session


class DefaultSessionLoopExecutor:
    """Default :class:`SessionLoopExecutor`: sync chat client + sandbox ``dispatch``.

    Accepts any :class:`~rath.llm.ChatClient` (Protocol). The session loop
    builds a default :class:`~rath.llm.RathOpenAIChatClient` when no
    ``executor`` is passed, but custom clients (e.g. Anthropic) plug in here
    without subclassing.
    """

    __slots__ = ("_client",)

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        """Defer to :func:`~rath.session.loop.run_session_loop` loop-local tool table."""

        return ()

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        """Call the synchronous :class:`~rath.llm.client.RathOpenAIChatClient`."""

        return self._client.complete(req)

    def dispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Invoke ``tool(session, arguments)`` (sandbox or user-defined)."""

        return dispatch_flow_tool(session, tool, arguments).raw


__all__ = ["DefaultSessionLoopExecutor"]
