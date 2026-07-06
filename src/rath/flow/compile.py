"""Static compilation of a :class:`~rath.flow.workflow.Workflow`.

``Workflow.compile()`` performs a **static** pass over the module tree (P5.1)
without running the model or materializing any session. It collects a
:class:`ResourceManifest` — every reachable ``AgentParam``'s provider identity,
whether memory is bound, and the agent-prompt session id — and records
``Selector`` nodes as *dynamic* (known-unknown) rather than pretending to know
their runtime routing.

Soundness is the point: compile never predicts a ``Selector`` branch, a loop
count, or a ``fork``. It answers *what resources can this workflow use* (for
pre-flight validation and deterministic acquire/teardown), not *what will it do*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rath.flow.workflow import Workflow

from rath.llm.provider import Provider

__all__ = [
    "AgentResource",
    "DynamicNode",
    "ResourceManifest",
    "collect_manifest",
    "CompiledWorkflow",
]


@dataclass(frozen=True, slots=True)
class AgentResource:
    """One reachable ``AgentParam`` in the compiled module tree."""

    path: str  # dotted path from the root workflow (e.g. "a.p")
    provider: Provider
    has_memory: bool
    agent_session_id: str


@dataclass(frozen=True, slots=True)
class DynamicNode:
    """A node whose runtime behavior compile cannot statically resolve."""

    path: str
    kind: str  # e.g. "selector"
    reason: str


@dataclass(slots=True)
class ResourceManifest:
    """The static resource inventory of a compiled workflow."""

    agents: list[AgentResource] = field(default_factory=list)
    dynamic_nodes: list[DynamicNode] = field(default_factory=list)

    def provider_models(self) -> list[str]:
        """Distinct, sorted provider model names reachable in the workflow."""
        return sorted({a.provider.model for a in self.agents if a.provider.model})

    def provider_kinds(self) -> list[str]:
        """Distinct, sorted provider kinds reachable (``None`` -> ``"openai"``)."""
        return sorted({a.provider.provider_kind or "openai" for a in self.agents})


def _join(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def collect_manifest(workflow: "Workflow") -> ResourceManifest:
    """Walk ``workflow``'s module tree and build its :class:`ResourceManifest`.

    Deterministic pre-order traversal. A ``Selector`` is recorded as a dynamic
    node (its router ``AgentParam`` is still collected, since that provider is a
    real static dependency), and its runtime routing targets are NOT followed —
    they are decided by the model at run time.
    """
    from rath.flow.selector import Selector

    manifest = ResourceManifest()

    def _visit(node: "Workflow", prefix: str) -> None:
        if isinstance(node, Selector):
            manifest.dynamic_nodes.append(
                DynamicNode(
                    path=prefix or type(node).__name__,
                    kind="selector",
                    reason=(
                        "Selector routes to a workflow chosen by the model at "
                        "runtime; successor set is not statically known"
                    ),
                )
            )
        # Collect this node's own AgentParam leaves (incl. a Selector's router).
        for name, ap in node.named_agents():
            manifest.agents.append(
                AgentResource(
                    path=_join(prefix, name),
                    provider=ap.provider,
                    has_memory=ap.memory is not None,
                    agent_session_id=str(ap.agent_session.id),
                )
            )
        # Descend into nested workflow children (but not a Selector's dynamic
        # routing — a Selector holds no static workflow children anyway).
        for name, child in node.named_children():
            _visit(child, _join(prefix, name))

    _visit(workflow, "")
    return manifest


class CompiledWorkflow:
    """Static, callable wrapper around a :class:`~rath.flow.workflow.Workflow`.

    Produced by :meth:`Workflow.compile`. It is callable exactly like the
    workflow — ``cw(session)`` delegates to ``workflow.forward`` — so compiling
    is opt-in and non-breaking. It also exposes the static
    :class:`ResourceManifest`, the module tree, and a graph ``repr``.

    Compiling runs no model and materializes no session; it only walks the
    static module tree (P5.1) to build the manifest.
    """

    __slots__ = ("workflow", "manifest")

    def __init__(self, workflow: "Workflow") -> None:
        self.workflow = workflow
        self.manifest = collect_manifest(workflow)

    def __call__(self, session):  # type: ignore[no-untyped-def]
        return self.workflow(session)

    def named_children(self):  # type: ignore[no-untyped-def]
        """The compiled workflow's registered children (delegates)."""
        return self.workflow.named_children()

    def __repr__(self) -> str:
        n_agents = len(self.manifest.agents)
        n_dyn = len(self.manifest.dynamic_nodes)
        return (
            f"CompiledWorkflow({self.workflow!r}, "
            f"agents={n_agents}, dynamic_nodes={n_dyn})"
        )
