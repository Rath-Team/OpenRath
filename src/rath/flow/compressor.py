"""Workflow wrapper that runs :func:`~rath.session.compress.run_session_compress`."""

from __future__ import annotations

from collections.abc import Callable

from rath.flow.agent_param import AgentParam
from rath.flow.workflow import Workflow
from rath.llm import RathLLMStreamDelta
from rath.llm.provider import Provider
from rath.session import Session, run_session_compress


class Compressor(Workflow):
    def __init__(
        self,
        compress_instruction: str,
        provider: Provider,
        *,
        on_event: Callable[[RathLLMStreamDelta], None] | None = None,
        description: str = "",
    ):
        super().__init__(description=description)
        self._on_event = on_event
        self.agent = AgentParam(
            agent_session=Session.from_agent_prompt(compress_instruction),
            provider=provider,
        )

    def forward(self, session: Session) -> Session:
        return run_session_compress(
            user_session=session,
            agent_session=self.agent.agent_session,
            agent_provider=self.agent.provider,
            on_event=self._on_event,
        )


__all__ = ["Compressor"]
