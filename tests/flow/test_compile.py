"""P5.3 — Workflow.compile() returns a CompiledWorkflow.

compile() is opt-in and non-breaking: the CompiledWorkflow is callable exactly
like the workflow (delegates to forward), and exposes the static manifest,
children, and a repr of the graph. It never runs the model or materializes a
session.
"""

from __future__ import annotations

from rath.flow.agent_param import AgentParam
from rath.flow.compile import CompiledWorkflow, ResourceManifest
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.session.session import Session


class _Echo(Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.a = AgentParam(Session.from_agent_prompt("sys"), Provider(model="m"))

    def forward(self, session: Session) -> Session:
        return session


def test_compile_returns_compiled_workflow() -> None:
    wf = _Echo()
    cw = wf.compile()
    assert isinstance(cw, CompiledWorkflow)
    assert isinstance(cw.manifest, ResourceManifest)


def test_compiled_is_callable_like_workflow() -> None:
    wf = _Echo()
    cw = wf.compile()
    s = Session.from_user_message("hi")
    out = cw(s)
    # _Echo.forward is identity; the compiled call must behave the same.
    assert out is s


def test_compiled_exposes_graph() -> None:
    wf = _Echo()
    cw = wf.compile()
    assert cw.manifest.provider_models() == ["m"]
    assert "_Echo" in repr(cw)


def test_compile_does_not_mutate_workflow() -> None:
    wf = _Echo()
    before = [n for n, _ in wf.named_agents()]
    wf.compile()
    assert [n for n, _ in wf.named_agents()] == before


def test_compiled_wraps_original() -> None:
    wf = _Echo()
    cw = wf.compile()
    assert cw.workflow is wf
