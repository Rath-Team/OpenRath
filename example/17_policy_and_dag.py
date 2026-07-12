"""Bound what a training model can reach, then mine the branches it left behind.

Two things happen here:

1. A :class:`ToolPolicy` bounds the session at the dispatch boundary. A call outside
   the bound never reaches the tool body; it comes back as a recorded failure the
   model can react to, not an exception that kills the episode.
2. Two sessions forked from one parent are scored, and the reward gap between them
   becomes a preference pair. Both branches saw the same state before they diverged,
   which is what makes the comparison meaningful.

Run: uv run python example/17_policy_and_dag.py
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from rath.backend import get
from rath.data import (
    build_session_graph,
    extract_preference_pairs,
    write_session_graph_jsonl,
)
from rath.flow.tool import ToolPolicy, dispatch_flow_tool, global_system_tools
from rath.session import Session


def main() -> None:
    tools = global_system_tools()

    print("== 1. a tool policy, enforced where tools execute ==")
    with get("local").open() as sandbox:
        session = Session.from_user_message("do the task").bind_sandbox(sandbox)
        session.tool_policy = ToolPolicy(command_deny=("rm",), max_calls=5)

        allowed = dispatch_flow_tool(
            session, tools["run_shell_command"], {"cmd": "echo hello"}
        )
        print(f"   echo hello   -> failed={allowed.failed}")

        denied = dispatch_flow_tool(
            session, tools["run_shell_command"], {"cmd": "rm -rf /"}
        )
        print(f"   rm -rf /     -> failed={denied.failed}  ({denied.raw.message})")
        print("   the denial is a recorded result, not an exception\n")

    print("== 2. forked branches become preference pairs ==")
    parent = Session.from_user_message("solve it")
    good = parent.fork()
    bad = parent.fork()

    graph = build_session_graph(
        [parent, good, bad],
        rewards={str(good.id): 1.0, str(bad.id): 0.0},
        statuses={str(good.id): "completed", str(bad.id): "stopped"},
    )
    print(f"   graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    pairs = extract_preference_pairs(graph)
    for pair in pairs:
        print(
            f"   pair: chosen={pair.chosen[:8]} over rejected={pair.rejected[:8]} "
            f"(margin {pair.margin})"
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "graph.jsonl"
        write_session_graph_jsonl(graph, path)
        print(f"   wrote {len(path.read_text().splitlines())} JSONL records")


if __name__ == "__main__":
    main()
