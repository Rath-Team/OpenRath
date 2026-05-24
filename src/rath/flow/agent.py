from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Union

from rath.flow.agent_param import AgentParam
from rath.flow.memory_inject import DefaultRecallInjection, MemoryInjectionPolicy
from rath.flow.tool import FlowToolCall
from rath.flow.workflow import Workflow
from rath.llm import RathLLMStreamDelta
from rath.llm.provider import Provider
from rath.memory import current as _current_memory_backend
from rath.memory import get as _get_memory_backend
from rath.memory.abc import MemoryStore, MemoryStoreSpec
from rath.session import Session, run_session_loop

MemoryArg = Union[MemoryStore, MemoryStoreSpec, str, None]


def _resolve_memory(memory: MemoryArg) -> MemoryStore | None:
    """Resolve any of the three accepted ``memory=`` forms to an open store.

    Acquires one refcount on the returned store; the caller -- usually
    :class:`Agent` -- is responsible for releasing it via
    :meth:`MemoryStore.release` (or its own ``close()``).
    """

    if memory is None:
        return None
    if isinstance(memory, MemoryStore):
        return memory.acquire()
    if isinstance(memory, str):
        backend = _get_memory_backend(memory)
        return backend.open().acquire()
    if isinstance(memory, MemoryStoreSpec):
        backend = _current_memory_backend()
        return backend.open(memory).acquire()
    raise TypeError(
        f"memory must be a MemoryStore, MemoryStoreSpec, backend name, or None; got {type(memory).__name__}"
    )


class Agent(Workflow):
    def __init__(
        self,
        system_prompt: str,
        provider: Provider | None = None,
        tools: list[FlowToolCall] | None = None,
        *,
        model: str | None = None,
        on_event: Callable[[RathLLMStreamDelta], None] | None = None,
        memory: MemoryArg = None,
        memory_inject: MemoryInjectionPolicy | None = None,
        commit_on_forward: bool = False,
    ):
        """Build a single-agent workflow.

        ``provider`` may be a fully-formed :class:`~rath.llm.Provider` (the
        explicit form used when you want to control api_key, base_url,
        sampling, etc.) or omitted in favor of the shortcut ``model="..."``
        kwarg, which constructs a :class:`Provider` with just that model name.

        ``api_key`` and ``base_url`` left empty on the Provider fall back to
        the ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` environment variables,
        then to ``llm.default_provider`` in ``~/.openrath/config.json``
        (see :mod:`rath.config`), inside
        :class:`~rath.llm.RathOpenAIChatClient`, so::

            flow.Agent("Use tools when helpful.", model="gpt-5.5")

        is the minimal form that works once the environment is configured.

        ``on_event`` enables streaming: each forward pass invokes the loop
        with the callback wired up. The resolved chat client must satisfy
        :class:`~rath.llm.StreamingChatClient`.
        """
        super().__init__()
        if provider is None and model is None:
            raise ValueError(
                'flow.Agent requires either provider=Provider(...) or model="..."',
            )
        if provider is None:
            provider = Provider(model=model)
        elif model is not None and provider.model is None:
            provider = replace(provider, model=model)
        self.tools = list(tools or [])
        self._on_event = on_event
        self._memory_inject: MemoryInjectionPolicy = (
            memory_inject or DefaultRecallInjection()
        )
        self._commit_on_forward = commit_on_forward
        resolved_memory = _resolve_memory(memory)
        self.memory = resolved_memory
        self.agent = AgentParam(
            agent_session=Session.from_agent_prompt(system_prompt),
            provider=provider,
            memory=resolved_memory,
        )

    _executor_override = None  # tests-only seam; production paths leave it None

    def forward(self, session: Session) -> Session:
        effective = (
            self._inject_memory_into(session) if self.memory is not None else session
        )
        loop_kwargs: dict[str, object] = dict(
            user_session=effective,
            agent_session=self.agent.agent_session,
            agent_provider=self.agent.provider,
            tools=self.tools,
            on_event=self._on_event,
        )
        if self._executor_override is not None:
            loop_kwargs["executor"] = self._executor_override
        out = run_session_loop(**loop_kwargs)  # type: ignore[arg-type]
        if self._commit_on_forward and self.memory is not None:
            self._commit_session(out, wait=False)
        return out

    def _inject_memory_into(self, session: Session) -> Session:
        """Return a forked session with policy-supplied chunks prepended."""
        assert self.memory is not None  # caller-checked
        try:
            extras = self._memory_inject.inject(session, self.memory)
        except Exception:  # noqa: BLE001 -- recall must not break the loop
            extras = ()
        if not extras:
            return session
        from dataclasses import replace as _dc_replace

        from rath.session.chunk import ChunkTable as _CT

        merged = _CT(rows=tuple(extras) + session.chunk_table.rows)
        return _dc_replace(session, chunk_table=merged)

    def _commit_session(self, session: Session, *, wait: bool) -> None:
        """Best-effort commit of ``session``'s chat history into memory."""
        from rath.memory.op_types import MemoryOpCommit
        from rath.session.chunk import ChunkKind as _CK

        messages: list[dict[str, object]] = []
        for row in session.chunk_table.rows:
            if row.kind == _CK.SYSTEM:
                messages.append(
                    {"role": "system", "content": row.payload.get("content", "")}
                )
            elif row.kind == _CK.USER:
                messages.append(
                    {"role": "user", "content": row.payload.get("content", "")}
                )
            elif row.kind == _CK.ASSISTANT:
                messages.append(
                    {
                        "role": "assistant",
                        "content": row.payload.get("content"),
                    }
                )
        if self.memory is None:
            return
        try:
            self.memory.dispatch(
                MemoryOpCommit(
                    session_id=str(session.id),
                    messages=tuple(messages),
                    wait=wait,
                )
            )
        except Exception:  # noqa: BLE001 -- commit must not break forward
            pass

    # ---------------------------------------------------------------- public memory API

    def remember(
        self,
        content: str,
        *,
        scope: str = "user",
        category: str = "preferences",
        wait: bool = False,
    ) -> "object":
        """Persist a free-form note under ``viking://{scope}/memories/{category}/...``.

        ``scope`` is intentionally permissive (``user`` / ``agent`` /
        ``session``) so user code can decide which namespace to target;
        the URI prefix is adapter-coupled and other backends may rewrite
        it. See :class:`~rath.memory.adapters.openviking.OpenVikingBackend`.
        """
        from rath.memory.op_types import MemoryOpWrite

        store = self._require_memory()
        uri = self._memory_uri(scope=scope, category=category)
        return store.dispatch(MemoryOpWrite(uri=uri, content=content, wait=wait))

    def recall(
        self,
        query: str,
        *,
        top_k: int = 4,
        target_uri: str | None = None,
    ) -> "object":
        """Issue a ``MemoryOpFind`` against the bound store and return the result."""
        from rath.memory.op_types import MemoryOpFind

        store = self._require_memory()
        return store.dispatch(
            MemoryOpFind(query=query, top_k=top_k, target_uri=target_uri)
        )

    def commit(self, session: Session, *, wait: bool = False) -> "object":
        """Commit ``session``'s chat transcript into memory for extraction."""
        from rath.memory.op_types import MemoryOpCommit
        from rath.session.chunk import ChunkKind as _CK

        store = self._require_memory()
        messages: list[dict[str, object]] = []
        for row in session.chunk_table.rows:
            if row.kind == _CK.SYSTEM:
                messages.append(
                    {"role": "system", "content": row.payload.get("content", "")}
                )
            elif row.kind == _CK.USER:
                messages.append(
                    {"role": "user", "content": row.payload.get("content", "")}
                )
            elif row.kind == _CK.ASSISTANT:
                messages.append(
                    {"role": "assistant", "content": row.payload.get("content")}
                )
        return store.dispatch(
            MemoryOpCommit(
                session_id=str(session.id),
                messages=tuple(messages),
                wait=wait,
            )
        )

    def _require_memory(self) -> MemoryStore:
        if self.memory is None:
            raise RuntimeError("agent has no memory store")
        return self.memory

    @staticmethod
    def _memory_uri(*, scope: str, category: str) -> str:
        import uuid as _uuid

        slug = _uuid.uuid4().hex[:8]
        return f"viking://{scope}/memories/{category}/{slug}"

    # ---------------------------------------------------------------- lifecycle

    def close(self) -> None:
        """Release the memory store reference acquired in ``__init__`` (idempotent)."""
        mem = self.memory
        if mem is None:
            return
        self.memory = None
        # Also drop the reference from the AgentParam mirror so repr stops
        # showing a stale handle once the store has been released.
        try:
            self.agent.memory = None
        except Exception:  # noqa: BLE001 -- agent_param may already be gone
            pass
        mem.release()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        self.close()

    def register_tool(self, tool: FlowToolCall) -> None:
        if any(t.name == tool.name for t in self.tools):
            return
        self.tools.append(tool)

    def unregister_tool(self, tool_name: str) -> None:
        self.tools = [t for t in self.tools if t.name != tool_name]
