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

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rath.flow.agent_param import AgentParam
    from rath.flow.workflow import Workflow
    from rath.memory.abc import MemoryStore

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

    __slots__ = ("workflow", "manifest", "_acquired")

    def __init__(self, workflow: "Workflow") -> None:
        self.workflow = workflow
        self.manifest = collect_manifest(workflow)
        self._acquired: list[MemoryStore] = []  # stores acquired by __enter__

    def __call__(self, session):  # type: ignore[no-untyped-def]
        return self.workflow(session)

    def __enter__(self) -> "CompiledWorkflow":
        """Pre-acquire the planned resources (bound memory stores).

        Acquires one reference on every distinct memory store bound to a
        reachable ``AgentParam`` so they stay open for the compiled run and are
        released deterministically on exit. Provider is a value (no lifecycle);
        sandboxes open lazily per session and are not force-opened here.
        """
        acquired: list[MemoryStore] = []
        seen: set[int] = set()
        try:
            for _path, ap in _reachable_agent_params(self.workflow):
                store = ap.memory
                if store is not None and id(store) not in seen:
                    seen.add(id(store))
                    store.acquire()
                    acquired.append(store)
        except BaseException:
            for store in reversed(acquired):
                _safe_release(store)
            raise
        self._acquired = acquired
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        # Release in reverse acquisition order; never mask an in-flight error.
        for store in reversed(self._acquired):
            _safe_release(store)
        self._acquired = []

    def named_children(self):  # type: ignore[no-untyped-def]
        """The compiled workflow's registered children (delegates)."""
        return self.workflow.named_children()

    def validate(self, *, raise_on_error: bool = False) -> list[str]:
        """Pre-flight check every reachable provider (offline; no model call).

        For each agent in the manifest, verify (1) its ``provider_kind`` is a
        registered chat-client kind, and (2) a credential resolves for it via
        the same Provider → env → config chain the client uses at construction —
        without building an SDK client or hitting the network.

        Returns a list of human-readable problems (empty when clean). With
        ``raise_on_error=True``, raises :class:`ValueError` if any problem is
        found. This lets callers fail fast before a run instead of deep inside
        the first completion.
        """
        from rath.llm.registry import registered_kinds

        problems: list[str] = []
        kinds = set(registered_kinds())
        for agent in self.manifest.agents:
            kind = agent.provider.provider_kind or "openai"
            if kind not in kinds:
                problems.append(
                    f"agent {agent.path!r}: unknown provider_kind={kind!r} "
                    f"(registered: {sorted(kinds)})"
                )
                continue
            if not _credential_resolves(kind, agent.provider):
                problems.append(
                    f"agent {agent.path!r}: no api credential resolves for "
                    f"provider_kind={kind!r} (set Provider.api_key, the vendor env "
                    f"var, or a config provider)"
                )
        if raise_on_error and problems:
            raise ValueError(
                "workflow pre-flight validation failed:\n  - " + "\n  - ".join(problems)
            )
        return problems

    def __repr__(self) -> str:
        n_agents = len(self.manifest.agents)
        n_dyn = len(self.manifest.dynamic_nodes)
        return (
            f"CompiledWorkflow({self.workflow!r}, "
            f"agents={n_agents}, dynamic_nodes={n_dyn})"
        )


def _credential_resolves(kind: str, provider: Provider) -> bool:
    """Whether an api key resolves for ``provider`` under ``kind`` (offline).

    Uses each adapter's pure resolver (Provider -> env -> config), which does
    not construct an SDK client or make a network call. LiteLLM resolves creds
    from provider-specific env vars internally, so it is treated as always
    satisfiable at the pre-flight layer.
    """
    try:
        if kind == "anthropic":
            from rath.llm.anthropic.client import _resolve_anthropic_key

            return bool(_resolve_anthropic_key(provider))
        if kind == "litellm":
            # LiteLLM defers credential resolution to its own per-vendor env
            # lookups; a missing rath-level key is not necessarily an error.
            return True
        # openai-compatible (default)
        from rath.llm.openai.client import _resolve_api_key, _resolve_base_url

        base_url = _resolve_base_url(provider)
        return bool(_resolve_api_key(provider, base_url))
    except Exception:  # noqa: BLE001 -- validation must never raise itself
        return False


def _reachable_agent_params(
    workflow: "Workflow",
) -> "Iterator[tuple[str, AgentParam]]":
    """Yield ``(path, AgentParam)`` for every agent in the module tree."""

    def _walk(node: "Workflow", prefix: str) -> "Iterator[tuple[str, AgentParam]]":
        for name, ap in node.named_agents():
            yield _join(prefix, name), ap
        for name, child in node.named_children():
            yield from _walk(child, _join(prefix, name))

    yield from _walk(workflow, "")


def _safe_release(store) -> None:  # type: ignore[no-untyped-def]
    """Release a memory store, swallowing errors so teardown never masks."""
    try:
        store.release()
    except Exception:  # noqa: BLE001 -- teardown must not raise
        pass
