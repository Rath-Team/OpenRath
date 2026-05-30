"""Workflow / AgentParam registration and scripted forward path."""

from __future__ import annotations

import pytest

from rath.backend import get
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.workflow import Workflow
from rath.llm import RathLLMAssistantMessage, RathLLMChatChoice, RathLLMChatResponse
from rath.session import Session, run_session_loop, session_registry
from rath.session.chunk import ChunkKind
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


@pytest.fixture(autouse=True)
def _clear_active_session_registry() -> None:
    yield
    session_registry().set_active(None)


class _ScriptedEchoWorkflow(Workflow):
    def __init__(self, scripted: RathLLMChatResponse) -> None:
        super().__init__()
        self._exec = ScriptedSessionLoopExecutor([scripted])
        self.agent = AgentParam(
            Session.from_agent_prompt("System prompt for workflow test."),
            Provider(),
        )

    def forward(self, session: Session) -> Session:
        return run_session_loop(
            session,
            self.agent.agent_session,
            agent_provider=self.agent.provider,
            executor=self._exec,
        )


def test_agent_accepts_model_kwarg_without_provider() -> None:
    """``flow.Agent(prompt, model=\"...\")`` is the minimal-form documented in
    the install guide; it must build a Provider with the given model so the
    one-liner example actually runs."""
    from rath import flow

    a = flow.Agent("You are concise.", model="gpt-5.5")
    assert a.agent.provider.model == "gpt-5.5"
    assert a.agent.provider.api_key is None  # api_key picked up from env at call time


def test_agent_explicit_provider_still_works() -> None:
    from rath import flow

    p = Provider(model="gpt-5.5", api_key="sk-fake")
    a = flow.Agent("You are concise.", p)
    assert a.agent.provider is p


def test_agent_model_kwarg_supplements_provider_without_model() -> None:
    """When the caller passes a provider that has no model set, the ``model=``
    kwarg should fill it in (last-mile convenience)."""
    from rath import flow

    p = Provider(api_key="sk-fake")
    a = flow.Agent("x", p, model="gpt-5.5")
    assert a.agent.provider.model == "gpt-5.5"
    # api_key is preserved from the explicit provider
    assert a.agent.provider.api_key == "sk-fake"


def test_agent_requires_provider_or_model() -> None:
    from rath import flow

    with pytest.raises(ValueError, match="provider"):
        flow.Agent("x")


def test_workflow_registers_agent_and_runs_loop() -> None:
    scripted = RathLLMChatResponse(
        id="wf1",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content="from workflow"),
            ),
        ),
        created=9,
        model="scripted",
    )
    wf = _ScriptedEchoWorkflow(scripted)

    assert len(wf.named_agents()) == 1
    name, leaf = wf.named_agents()[0]
    assert name == "agent"
    assert isinstance(leaf, AgentParam)
    assert isinstance(leaf.provider, Provider)

    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("Trigger scripted reply.").bind_sandbox(
            sandbox
        )
        out = wf.forward(user)

    assert out.sandbox is sandbox
    assistant_chunks = [
        r.payload.get("content")
        for r in out.chunk_table.rows
        if r.kind == ChunkKind.ASSISTANT
    ]
    assert any(c == "from workflow" for c in assistant_chunks)


def test_workflow_description_defaults_empty_and_roundtrips() -> None:
    """``description`` is a first-class Workflow field used by Selector routing;
    it defaults to "" and must not be mistaken for an AgentParam attribute."""
    from rath import flow

    base = Workflow()
    assert base.description == ""

    a = flow.Agent("You are concise.", model="gpt-5.5", description="answers tersely")
    assert a.description == "answers tersely"
    # description is a plain str, not registered as an agent
    assert "description" not in dict(a.named_agents())
