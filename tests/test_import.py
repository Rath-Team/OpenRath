"""Import surface and public API contracts."""

from __future__ import annotations

import inspect
import subprocess
import sys


def test_namespace_flow_submodules() -> None:
    """``rath.flow`` exposes the package; agent params and workflows live on submodules."""

    import rath
    from rath import flow

    assert rath.flow is flow

    from rath.flow.agent import Agent
    from rath.flow.agent_param import AgentParam
    from rath.flow.compressor import Compressor
    from rath.flow.workflow import Workflow
    from rath.llm import Provider

    assert flow.AgentParam is AgentParam
    assert flow.Agent is Agent
    assert flow.Compressor is Compressor
    assert AgentParam.__name__ == "AgentParam"
    assert Provider.__name__ == "Provider"
    assert Workflow.__name__ == "Workflow"


def test_agent_constructor_accepts_provider() -> None:
    from rath.flow.agent import Agent

    params = inspect.signature(Agent.__init__).parameters
    assert set(params) >= {"self", "system_prompt", "provider", "tools", "on_event"}


def test_provider_lives_in_llm_reexported_from_flow_agent_param() -> None:
    from rath.flow.agent_param import Provider as FromFlow
    from rath.llm import Provider as FromLlm

    assert FromFlow is FromLlm


def test_import_session_and_flow_modules() -> None:
    """Session and flow types import from their submodules."""

    from rath.flow.agent_param import AgentParam
    from rath.flow.workflow import Workflow
    from rath.llm import Provider
    from rath.session import (
        DefaultSessionLoopExecutor,
        Session,
        SessionLoopExecutor,
        run_session_compress,
        run_session_loop,
    )
    from rath.session.loop import StreamingExecutor

    assert run_session_compress.__name__ == "run_session_compress"

    assert AgentParam.__name__ == "AgentParam"
    assert Provider.__name__ == "Provider"
    assert Workflow.__name__ == "Workflow"
    assert Session.__name__ == "Session"
    assert run_session_loop.__name__ == "run_session_loop"
    assert DefaultSessionLoopExecutor.__name__ == "DefaultSessionLoopExecutor"
    assert SessionLoopExecutor.__name__ == "SessionLoopExecutor"
    assert StreamingExecutor.__name__ == "StreamingExecutor"


def test_run_session_loop_tools_parameter_documents_flow_tool_calls() -> None:
    from rath.session.loop import run_session_loop

    ann = inspect.signature(run_session_loop).parameters["tools"].annotation
    assert "FlowToolCall" in str(ann)


def test_global_system_tools_contains_builtin_instances() -> None:
    from rath.flow.tool import FlowToolCall, global_system_tools

    g = global_system_tools()
    for key in (
        "run_shell_command",
        "read_workspace_file",
        "write_workspace_file",
        "list_workspace_files",
        "workspace_path_exists",
        "run_code",
    ):
        assert key in g
        assert isinstance(g[key], FlowToolCall)


def test_rl_infrastructure_public_imports() -> None:
    from rath.benchmark import (
        BenchmarkRunner,
        BenchmarkRunResult,
        BenchmarkTask,
        PytestVerifier,
        VerifierExecutionError,
    )
    from rath.env import (
        OpenRathEnv,
        OpenRathEnvConfig,
        ToolAction,
        TrajectoryEpisode,
        load_trajectory_jsonl,
    )
    from rath.training import (
        EpisodeRollout,
        RolloutBatch,
        collect_benchmark_rollouts,
        to_verl_data_proto,
    )

    for symbol in (
        BenchmarkRunResult,
        BenchmarkRunner,
        BenchmarkTask,
        PytestVerifier,
        VerifierExecutionError,
        OpenRathEnv,
        OpenRathEnvConfig,
        ToolAction,
        TrajectoryEpisode,
        load_trajectory_jsonl,
        EpisodeRollout,
        RolloutBatch,
        collect_benchmark_rollouts,
        to_verl_data_proto,
    ):
        assert symbol is not None


def test_training_import_is_optional_dependency_lazy() -> None:
    code = (
        "import sys, rath.training; "
        "assert not {'verl', 'torch', 'numpy', 'tensordict'}.intersection(sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
