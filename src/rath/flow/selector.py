"""``Selector`` workflow: LLM-routed choice over self-describing workflows."""

from __future__ import annotations

from collections.abc import Callable

from rath.flow.agent_param import AgentParam
from rath.flow.empty import EmptyWorkflow
from rath.flow.workflow import Workflow
from rath.llm import RathLLMStreamDelta
from rath.llm.provider import Provider
from rath.session import Session, select_session
from rath.session.loop import SessionLoopExecutor

_DEFAULT_SELECT_INSTRUCTION = (
    "You are a router. Given the conversation and a numbered menu of candidate "
    "workflows, reply with the single best index, or -1 if none applies / the task "
    "is already complete."
)


class Selector(Workflow):
    """Pick the next :class:`~rath.flow.workflow.Workflow` for a session.

    Sibling of :class:`~rath.flow.agent.Agent` / :class:`~rath.flow.compressor.Compressor`.
    """

    def __init__(
        self,
        provider: Provider,
        *,
        select_instruction: str = _DEFAULT_SELECT_INSTRUCTION,
        description: str = "",
        on_event: Callable[[RathLLMStreamDelta], None] | None = None,
    ):
        super().__init__(description=description)
        self._on_event = on_event
        self._test_executor: SessionLoopExecutor | None = None
        self.agent = AgentParam(
            agent_session=Session.from_agent_prompt(select_instruction),
            provider=provider,
        )

    def forward(  # type: ignore[override]
        self, session: Session, *workflows: Workflow
    ) -> Workflow:
        """Return the workflow the model picks for ``session``, or an
        :class:`~rath.flow.empty.EmptyWorkflow` when no candidate fits / the session
        is complete.

        NOTE: this deliberately deviates from the base ``forward(session) -> Session``
        contract. ``Selector`` is a routing *decision* component, not a session
        transformer: it returns the chosen :class:`Workflow` (never ``None``), and the
        caller dispatches it (``session = chosen(session)``). Completion is signalled by
        returning an ``EmptyWorkflow`` (a no-op), detected via
        ``isinstance(result, EmptyWorkflow)``.
        """

        idx = -1
        if workflows:
            idx, _ = select_session(
                session,
                self.agent.agent_session,
                *(wf.description for wf in workflows),
                agent_provider=self.agent.provider,
                executor=self._test_executor,
            )
        return workflows[idx] if 0 <= idx < len(workflows) else EmptyWorkflow()


__all__ = ["Selector"]
