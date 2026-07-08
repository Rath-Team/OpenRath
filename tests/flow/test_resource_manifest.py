"""P5.2 — static ResourceManifest collected from a workflow module tree.

The collector walks the module tree (P5.1) and every reachable AgentParam,
recording provider identity, whether memory is bound, and the agent-prompt
session id. Selector children are recorded as DYNAMIC nodes (known-unknowns),
never silently dropped, and their runtime routing is not predicted.
"""

from __future__ import annotations

from rath.flow.agent_param import AgentParam
from rath.flow.compile import ResourceManifest, collect_manifest
from rath.flow.selector import Selector
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.session.session import Session


class _Leaf(Workflow):
    def __init__(self, model: str) -> None:
        super().__init__()
        self.p = AgentParam(Session.from_agent_prompt("sys"), Provider(model=model))


class _Tree(Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.a = _Leaf("m-a")
        self.b = _Leaf("m-b")
        self.own = AgentParam(Session.from_agent_prompt("own"), Provider(model="m-own"))


def test_collect_reaches_all_agentparams() -> None:
    m = collect_manifest(_Tree())
    assert isinstance(m, ResourceManifest)
    models = m.provider_models()
    assert set(models) == {"m-a", "m-b", "m-own"}


def test_manifest_records_agent_paths() -> None:
    m = collect_manifest(_Tree())
    paths = {a.path for a in m.agents}
    # dotted paths from the root through named_children/named_agents
    assert "own" in paths
    assert any(p.endswith(".p") for p in paths)


def test_selector_is_dynamic_node() -> None:
    class _WithSelector(Workflow):
        def __init__(self) -> None:
            super().__init__()
            self.router = Selector(Provider(model="r"))
            self.leaf = _Leaf("m-x")

    m = collect_manifest(_WithSelector())
    dyn_paths = {d.path for d in m.dynamic_nodes}
    assert "router" in dyn_paths
    # dynamic node carries a reason, and is not treated as a static leaf
    assert all(d.reason for d in m.dynamic_nodes)


def test_memory_binding_recorded() -> None:
    class _Mem(Workflow):
        def __init__(self, store) -> None:  # type: ignore[no-untyped-def]
            super().__init__()
            self.p = AgentParam(
                Session.from_agent_prompt("s"), Provider(model="m"), memory=store
            )

    # A sentinel object standing in for a MemoryStore (collector only records
    # presence, it does not open anything).
    sentinel = object()
    m = collect_manifest(_Mem(sentinel))
    assert any(a.has_memory for a in m.agents)


def test_empty_workflow_manifest_is_empty() -> None:
    class _E(Workflow):
        pass

    m = collect_manifest(_E())
    assert m.agents == []
    assert m.dynamic_nodes == []
