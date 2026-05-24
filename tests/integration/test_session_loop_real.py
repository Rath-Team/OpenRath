"""Integration tests: live LLM chat + OpenSandbox.

Markers: ``integration``, ``live_llm``, ``opensandbox``.
"""

from __future__ import annotations

import os

import pytest

from rath.backend import preferred
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.workflow import Workflow
from rath.llm import RathOpenAIChatClient
from rath.session import (
    ChunkKind,
    DefaultSessionLoopExecutor,
    Session,
    run_session_loop,
    session_registry,
)
from rath.session.graph import LineageKind
from tests.conftest import opensandbox_real
from tests.openai_env_provider import live_openai_provider


def _openai_key_plausible() -> bool:
    return len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8


_needs_live_llm = pytest.mark.skipif(
    not _openai_key_plausible(),
    reason="OPENAI_API_KEY missing or too short (export in environment)",
)

pytestmark = [
    opensandbox_real,
    _needs_live_llm,
    pytest.mark.opensandbox,
    pytest.mark.live_llm,
    pytest.mark.integration,
]


def _tool_rows_text(session: Session) -> str:
    parts: list[str] = []
    for row in session.chunk_table.rows:
        if row.kind != ChunkKind.TOOL_RESULT:
            continue
        parts.append(str(row.payload.get("content", "")))
    return "\n".join(parts)


def test_run_session_loop_opensandbox_shell_echo() -> None:
    """Model issues ``run_shell_command``; stdout is recorded in tool chunks."""

    backend = preferred(["opensandbox"])
    prov = live_openai_provider()
    client = RathOpenAIChatClient(prov)
    executor = DefaultSessionLoopExecutor(client)
    marker = "RATH_SESSION_E2E_ECHO_92653"
    agent = AgentParam(
        Session.from_agent_prompt(
            "You are a test harness. Follow user instructions exactly. "
            "When the user asks you to run a shell command via a tool, call "
            "run_shell_command once with the cmd string they specify—no extra steps."
        ),
        prov,
    )
    with backend.open() as sandbox:
        user = Session.from_user_message(
            f"Use run_shell_command exactly once. The cmd must run: echo {marker}"
        ).bind_sandbox(sandbox)

        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
            max_tool_rounds=12,
        )

        assert out.sandbox is sandbox
        assert out.sandbox.closed is False
        assert user.sandbox is sandbox
        # Inside the ``with`` block: 1 ref from the context manager, 1 from
        # ``user.bind_sandbox`` and 1 from the loop's output session.
        assert sandbox.refcount == 3
        assert out.lineage is not None
        assert out.lineage.producer_user_session_id == user.id
        assert out.parent_session_ids == (user.id, agent.agent_session.id)
        assert out.lineage_kind == LineageKind.OP_SESSION_LOOP
        assert session_registry().get_active_id() == out.id

        tool_blob = _tool_rows_text(out)
        assert marker in tool_blob, tool_blob


class _ShellEchoWorkflow(Workflow):
    """Minimal workflow forwarding to :func:`run_session_loop`."""

    def __init__(
        self,
        system_prompt: str,
        executor: DefaultSessionLoopExecutor,
        provider: Provider,
    ) -> None:
        super().__init__()
        self.actor = AgentParam(Session.from_agent_prompt(system_prompt), provider)
        self._loop_executor = executor

    def forward(self, session: Session) -> Session:
        return run_session_loop(
            session,
            self.actor.agent_session,
            agent_provider=self.actor.provider,
            executor=self._loop_executor,
        )


def test_workflow_opensandbox_shell_echo() -> None:
    """Same stack through :class:`Workflow.forward`."""

    backend = preferred(["opensandbox"])
    prov = live_openai_provider()
    client = RathOpenAIChatClient(prov)
    executor = DefaultSessionLoopExecutor(client)
    marker = "RATH_SINGLE_AGENT_E2E_17402"
    system_prompt = (
        "You are a test harness. Use run_shell_command when the user asks "
        "for a shell command, exactly once with the cmd they describe."
    )
    with backend.open() as sandbox:
        user = Session.from_user_message(
            f"Call run_shell_command once with cmd: echo {marker}"
        ).bind_sandbox(sandbox)

        wf = _ShellEchoWorkflow(system_prompt, executor, prov)
        assert len(wf.named_agents()) == 1
        assert wf.named_agents()[0][0] == "actor"

        out = wf.forward(user)

        assert out.sandbox is sandbox
        assert _tool_rows_text(out).count(marker) >= 1
