"""P5.1 — nested Workflow/Agent children register into a module tree.

Mirrors torch.nn.Module child registration: assigning a Workflow (or Agent,
which is a Workflow) as an attribute registers it under named_children();
AgentParam leaves still register under named_agents(). modules() walks the
tree recursively. repr shows the nested structure.
"""

from __future__ import annotations

from rath.flow.agent import Agent
from rath.flow.agent_param import AgentParam
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.session.session import Session


class _Leaf(Workflow):
    def __init__(self) -> None:
        super().__init__(description="leaf")
        self.p = AgentParam(Session.from_agent_prompt("leaf"), Provider(model="m"))


class _Parent(Workflow):
    def __init__(self) -> None:
        super().__init__(description="parent")
        self.child_b = _Leaf()
        self.child_a = _Leaf()
        self.own = AgentParam(Session.from_agent_prompt("own"), Provider(model="m"))


def test_children_registered_sorted() -> None:
    p = _Parent()
    names = [n for n, _ in p.named_children()]
    assert names == ["child_a", "child_b"]  # sorted
    for _n, c in p.named_children():
        assert isinstance(c, _Leaf)


def test_agentparam_leaves_still_register() -> None:
    p = _Parent()
    assert [n for n, _ in p.named_agents()] == ["own"]


def test_modules_walks_recursively() -> None:
    p = _Parent()
    mods = list(p.modules())
    # self + 2 children
    assert p in mods
    assert sum(isinstance(m, _Leaf) for m in mods) == 2


def test_agent_as_child_registers_once() -> None:
    """An Agent assigned to a parent is a child; its own AgentParam is not
    double-counted on the parent."""

    class _Uses(Workflow):
        def __init__(self) -> None:
            super().__init__()
            self.worker = Agent("sys", model="gpt-5.5")

    u = _Uses()
    assert [n for n, _ in u.named_children()] == ["worker"]
    # The parent has no AgentParam of its own — the Agent's param stays inside it.
    assert u.named_agents() == ()
    assert isinstance(u.worker, Agent)
    # The child Agent still has its own registered AgentParam.
    assert [n for n, _ in u.worker.named_agents()] == ["agent"]


def test_delattr_unregisters_child() -> None:
    p = _Parent()
    del p.child_a
    assert [n for n, _ in p.named_children()] == ["child_b"]


def test_repr_shows_nested_tree() -> None:
    p = _Parent()
    text = repr(p)
    assert "_Parent" in text
    assert "child_a" in text and "child_b" in text
