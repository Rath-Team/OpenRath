"""Deterministic compiler from Python Workflow declarations to ExecutionPlan."""

from __future__ import annotations

import hashlib
import inspect
import json
import textwrap
from collections.abc import Callable, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from rath._json import JSONValue, thaw_json
from rath.definition.decorators import _metadata
from rath.definition.model import (
    EdgeSpec,
    EffectClass,
    ExecutionPlan,
    NodeKind,
    NodeSpec,
    ProviderResource,
    ResourceManifestV2,
    RetryPolicy,
    WorkflowDefinition,
)

__all__ = ["DefinitionError", "WorkflowCompiler"]


class DefinitionError(ValueError):
    """Workflow declaration cannot produce a safe deterministic plan."""


class WorkflowCompiler:
    """Compile explicit Python step boundaries without executing workflow code."""

    def compile(
        self,
        workflow: object,
        *,
        revision_id: UUID,
        production_durable: bool = False,
        input_schema: Mapping[str, JSONValue] | None = None,
        state_schema: Mapping[str, JSONValue] | None = None,
        policy_manifest: Mapping[str, JSONValue] | None = None,
    ) -> ExecutionPlan:
        name = f"{type(workflow).__module__}.{type(workflow).__qualname__}"
        version = str(getattr(workflow, "workflow_version", "1"))
        nodes, entrypoint, durable, issues = self._nodes(workflow)
        self._validate(
            nodes,
            entrypoint,
            production_durable=production_durable,
        )
        edges = tuple(
            EdgeSpec(source=node.id, target=target)
            for node in nodes
            for target in node.successors
        )
        definition_payload = {
            "name": name,
            "version": version,
            "entrypoint": entrypoint,
            "nodes": [node.to_dict() for node in nodes],
            "edges": [edge.to_dict() for edge in edges],
            "input_schema": thaw_json(input_schema or {}),
            "state_schema": thaw_json(state_schema or {}),
        }
        definition_json = json.dumps(
            definition_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        definition_hash = hashlib.sha256(definition_json.encode("utf-8")).hexdigest()
        definition_id = uuid5(NAMESPACE_URL, f"openrath:definition:{definition_hash}")
        definition = WorkflowDefinition(
            id=definition_id,
            name=name,
            version=version,
            entrypoint=entrypoint,
            nodes=nodes,
            edges=edges,
            input_schema=input_schema or {},
            state_schema=state_schema or {},
        )
        resources = self._resources(workflow)
        plan_seed = json.dumps(
            {
                "definition_hash": definition_hash,
                "revision_id": str(revision_id),
                "resources": resources.to_dict(),
                "policy_manifest": thaw_json(policy_manifest or {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        plan_id = uuid5(NAMESPACE_URL, f"openrath:plan:{plan_seed}")
        return ExecutionPlan(
            id=plan_id,
            definition_hash=definition_hash,
            revision_id=revision_id,
            definition=definition,
            nodes=nodes,
            resources=resources,
            policy_manifest=policy_manifest or {},
            durable=durable,
            compatibility_issues=issues,
        )

    def _nodes(
        self,
        workflow: object,
    ) -> tuple[tuple[NodeSpec, ...], str, bool, tuple[str, ...]]:
        discovered: list[tuple[str, Callable[..., object]]] = []
        for name, function in inspect.getmembers(type(workflow), predicate=callable):
            if _metadata(function) is not None:
                discovered.append((name, function))
        if not discovered:
            opaque = NodeSpec(
                id="legacy.forward",
                kind=NodeKind.OPAQUE,
                handler=f"{type(workflow).__module__}.{type(workflow).__qualname__}.forward",
                implementation_hash=self._implementation_hash(
                    getattr(type(workflow), "forward")
                ),
                is_async=inspect.iscoroutinefunction(
                    getattr(workflow, "forward", None)
                ),
                retry=RetryPolicy(),
                effects=EffectClass.NON_IDEMPOTENT,
                checkpoint=False,
            )
            return (
                (opaque,),
                opaque.id,
                False,
                (
                    "legacy forward() is opaque and cannot resume across checkpoint boundaries",
                ),
            )

        nodes: list[NodeSpec] = []
        entries: list[str] = []
        for name, function in discovered:
            metadata = _metadata(function)
            assert metadata is not None
            if metadata.entry:
                entries.append(name)
            nodes.append(
                NodeSpec(
                    id=name,
                    kind=metadata.kind,
                    handler=f"{type(workflow).__module__}.{type(workflow).__qualname__}.{name}",
                    implementation_hash=self._implementation_hash(function),
                    is_async=inspect.iscoroutinefunction(function),
                    retry=metadata.retry,
                    effects=metadata.effects,
                    idempotency_key=metadata.idempotency_key,
                    timeout_seconds=metadata.timeout_seconds,
                    checkpoint=metadata.checkpoint,
                    successors=metadata.successors,
                )
            )
        if len(entries) != 1:
            raise DefinitionError(
                f"workflow must declare exactly one entrypoint; found {len(entries)}"
            )
        return tuple(nodes), entries[0], True, ()

    @staticmethod
    def _implementation_hash(function: Callable[..., object]) -> str:
        """Fingerprint executable source so behavior changes alter plan identity."""
        try:
            material = textwrap.dedent(inspect.getsource(function)).strip()
        except (OSError, TypeError):
            code = function.__code__
            material = json.dumps(
                {
                    "bytecode": code.co_code.hex(),
                    "constants": repr(code.co_consts),
                    "names": code.co_names,
                    "varnames": code.co_varnames,
                    "argcount": code.co_argcount,
                    "kwonlyargcount": code.co_kwonlyargcount,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _validate(
        self,
        nodes: tuple[NodeSpec, ...],
        entrypoint: str,
        *,
        production_durable: bool = False,
    ) -> None:
        ids = {node.id for node in nodes}
        if len(ids) != len(nodes):
            raise DefinitionError("workflow node ids must be unique")
        for node in nodes:
            if (
                production_durable
                and not node.is_async
                and node.timeout_seconds is not None
            ):
                raise DefinitionError(
                    "synchronous durable steps cannot guarantee preemptive timeout; "
                    "use an async handler or an isolated executor"
                )
            for successor in node.successors:
                if successor not in ids:
                    raise DefinitionError(
                        f"node {node.id!r} references unknown successor {successor!r}"
                    )
            if node.kind is NodeKind.ROUTER and not node.successors:
                raise DefinitionError(f"router {node.id!r} requires successors")

        reachable: set[str] = set()
        pending = [entrypoint]
        by_id = {node.id: node for node in nodes}
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(by_id[current].successors)
        unreachable = sorted(ids - reachable)
        if unreachable:
            raise DefinitionError(f"unreachable workflow nodes: {unreachable}")

    def _resources(self, workflow: object) -> ResourceManifestV2:
        providers: list[ProviderResource] = []
        named_agents = getattr(workflow, "named_agents", None)
        if callable(named_agents):
            for path, agent in named_agents():
                provider = agent.provider
                providers.append(
                    ProviderResource(
                        path=path,
                        provider_kind=provider.provider_kind or "openai",
                        model=provider.model,
                        has_memory=agent.memory is not None,
                    )
                )
        return ResourceManifestV2(providers=tuple(providers))
