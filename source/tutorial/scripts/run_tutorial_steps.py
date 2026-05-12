"""Generate deterministic tutorial logs for OpenRath docs.

The script intentionally avoids real LLM calls. It exercises the same runtime
paths using scripted completions so the tutorial output remains reproducible.
The public tutorials use Markdown code blocks instead of code images, so this
script keeps only text logs and lightweight HTML views for local inspection.
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import re
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from rath import flow  # noqa: E402
from rath.backend import get  # noqa: E402
from rath.flow.tool import (  # noqa: E402
    FlowToolCall,
    flow_tool_code_run,
    flow_tool_command_run,
    flow_tool_files_read,
    flow_tool_files_write,
    global_system_tools,
)
from rath.llm import (  # noqa: E402
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMFunctionTool,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
)
from rath.session import Session, run_session_loop  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
ASSETS = BASE / "assets"
MANIFEST = ASSETS / "manifest.json"


class ScriptedSessionLoopExecutor:
    """Small deterministic loop executor used only by the tutorials."""

    def __init__(self, responses: list[RathLLMChatResponse]) -> None:
        self._queue = list(responses)

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        if not self._queue:
            raise RuntimeError("scripted response queue is empty")
        return self._queue.pop(0)

    def dispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any:
        return tool(session, dict(arguments or {}))

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        return ()


class WordCountTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "word_count"

    @property
    def description(self) -> str:
        return "Count words and unique lowercase tokens in a short text."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to count.",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
        text = str(arguments["text"])
        words = re.findall(r"[A-Za-z0-9_]+", text.lower())
        return {
            "word_count": len(words),
            "unique_words": len(set(words)),
            "session_backend": session.sandbox_backend,
        }


def _asset_dirs(tutorial: str) -> tuple[Path, Path]:
    root = ASSETS / tutorial
    return root / "logs", root / "html"


def _clean_dirs(section: str | None = None) -> None:
    for legacy in ("logs", "html", "screenshots"):
        shutil.rmtree(ASSETS / legacy, ignore_errors=True)
    targets = tuple(SECTIONS) if section is None else (section,)
    for tutorial in targets:
        shutil.rmtree(ASSETS / tutorial / "screenshots", ignore_errors=True)
        for directory in _asset_dirs(tutorial):
            directory.mkdir(parents=True, exist_ok=True)
            for path in directory.iterdir():
                if path.is_file():
                    path.unlink()
    if section is None:
        MANIFEST.unlink(missing_ok=True)


def _normalise(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return _normalise(dataclasses.asdict(obj))
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Mapping):
        return {str(k): _normalise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalise(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _pretty(obj: Any) -> str:
    return json.dumps(_normalise(obj), ensure_ascii=False, indent=2, default=str)


def _format_session_rows(session: Session) -> str:
    lines = [
        f"session_id={session.id}",
        f"sandbox_backend={session.sandbox_backend}",
        f"sandbox_open={session.sandbox is not None and not session.sandbox.closed}",
        f"lineage_operator={session.lineage_operator}",
        "chunks:",
    ]
    for idx, row in enumerate(session.chunk_table.rows):
        lines.append(f"  [{idx}] {row.kind.value}: {_pretty(row.payload)}")
    return "\n".join(lines)


def _tool_response(
    *,
    response_id: str,
    created: int,
    call_id: str,
    name: str,
    arguments: Mapping[str, Any],
) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id=response_id,
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="tool_calls",
                message=RathLLMAssistantMessage(
                    tool_calls=(
                        RathLLMToolCallPart(
                            id=call_id,
                            type="function",
                            function=RathLLMToolCallFunction(
                                name=name,
                                arguments=json.dumps(arguments, ensure_ascii=False),
                                arguments_parsed=dict(arguments),
                                arguments_parse_error=False,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        created=created,
        model="scripted",
    )


def _stop_response(
    *,
    response_id: str,
    created: int,
    content: str,
) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id=response_id,
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=content),
            ),
        ),
        created=created,
        model="scripted",
    )


def _render_step_html(title: str, command: str, output: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7fb;
      color: #172033;
    }}
    body {{
      margin: 0;
      padding: 36px;
    }}
    .frame {{
      width: 1080px;
      min-height: 640px;
      border: 1px solid #d6dce8;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 8px 30px rgba(23, 32, 51, 0.10);
      overflow: hidden;
    }}
    .bar {{
      display: flex;
      gap: 7px;
      align-items: center;
      padding: 12px 16px;
      background: #edf1f8;
      border-bottom: 1px solid #d6dce8;
      font-size: 14px;
      font-weight: 600;
    }}
    .dot {{
      width: 11px;
      height: 11px;
      border-radius: 999px;
      background: #c5ccd8;
    }}
    .title {{
      margin-left: 8px;
    }}
    .terminal {{
      margin: 0;
      padding: 22px;
      background: #111827;
      color: #e5e7eb;
      font: 15px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      min-height: 570px;
    }}
    .prompt {{
      color: #93c5fd;
    }}
  </style>
</head>
<body>
  <div class="frame">
    <div class="bar">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="title">{html.escape(title)}</span>
    </div>
    <pre class="terminal"><span class="prompt">$ {html.escape(command)}</span>

{html.escape(output)}</pre>
  </div>
</body>
</html>
"""


class Recorder:
    def __init__(self) -> None:
        self.manifest: list[dict[str, str | int]] = []

    def step(self, tutorial: str, number: int, title: str, command: str, output: str) -> None:
        log_dir, html_dir = _asset_dirs(tutorial)
        stem = f"{tutorial}-{number:02d}-{_slug(title)}"
        log_path = log_dir / f"{stem}.txt"
        html_path = html_dir / f"{stem}.html"

        log_path.write_text(f"$ {command}\n\n{output}\n", encoding="utf-8")
        html_path.write_text(_render_step_html(title, command, output), encoding="utf-8")

        self.manifest.append(
            {
                "tutorial": tutorial,
                "step": number,
                "title": title,
                "command": command,
                "log": str(log_path.relative_to(BASE)),
                "html": str(html_path.relative_to(BASE)),
            }
        )

    def save(self) -> None:
        MANIFEST.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "step"


def tutorial_session_basics(rec: Recorder) -> None:
    tutorial = "session-basics"
    agent = Session.from_agent_prompt("You are a concise tutorial assistant.")
    user = Session.from_user_message("List files in the sandbox.")
    rec.step(
        tutorial,
        1,
        "create sessions",
        "python docs/source/tutorial/scripts/run_tutorial_steps.py --section session-basics",
        "\n\n".join(
            [
                "agent_session",
                _format_session_rows(agent),
                "user_session",
                _format_session_rows(user),
            ]
        ),
    )

    forked = user.fork()
    detached = forked.detach()
    rec.step(
        tutorial,
        2,
        "fork and detach",
        "user.fork(); forked.detach()",
        "\n".join(
            [
                f"user.id={user.id}",
                f"forked.id={forked.id}",
                f"forked.parent_session_ids={[str(x) for x in forked.parent_session_ids]}",
                f"forked.lineage_operator={forked.lineage_operator}",
                f"detached.id={detached.id}",
                f"detached.parent_session_ids={[str(x) for x in detached.parent_session_ids]}",
                f"detached.lineage_operator={detached.lineage_operator}",
            ]
        ),
    )

    user.to("local")
    handle: str | None = None
    exists_inside = False
    with user:
        handle = user.sandbox.handle if user.sandbox else None
        exists_inside = Path(handle).exists() if handle else False
    rec.step(
        tutorial,
        3,
        "lazy local sandbox",
        'user.to("local"); with user: ...',
        "\n".join(
            [
                f"sandbox_backend={user.sandbox_backend}",
                f"handle_during_context={handle}",
                f"handle_exists_during_context={exists_inside}",
                f"sandbox_after_context={user.sandbox}",
                f"handle_exists_after_context={Path(handle).exists() if handle else None}",
            ]
        ),
    )


def tutorial_local_sandbox_tools(rec: Recorder) -> None:
    tutorial = "local-sandbox-tools"
    backend = get("local")
    sandbox = backend.open()
    handle = sandbox.handle
    try:
        rec.step(
            tutorial,
            1,
            "open local backend",
            'backend = get("local"); sandbox = backend.open()',
            "\n".join(
                [
                    f"backend.name={backend.name}",
                    f"backend.is_available={backend.is_available()}",
                    f"sandbox.handle={sandbox.handle}",
                    f"sandbox.closed={sandbox.closed}",
                    f"sandbox_count={backend.sandbox_count()}",
                    "capabilities=" + _pretty(backend.capabilities()),
                ]
            ),
        )

        write = sandbox.dispatch(
            flow_tool_files_write(
                "notes/hello.txt",
                "hello from OpenRath local backend\n",
            )
        )
        rec.step(
            tutorial,
            2,
            "write workspace file",
            'sandbox.dispatch(flow_tool_files_write("notes/hello.txt", "..."))',
            _pretty(write),
        )

        command = sandbox.dispatch(
            flow_tool_command_run(
                "pwd && find . -maxdepth 2 -type f | sort && cat notes/hello.txt"
            )
        )
        rec.step(
            tutorial,
            3,
            "run shell command",
            'sandbox.dispatch(flow_tool_command_run("pwd && find ..."))',
            _pretty(command),
        )

        read = sandbox.dispatch(flow_tool_files_read("notes/hello.txt"))
        code = sandbox.dispatch(
            flow_tool_code_run(
                "from pathlib import Path\n"
                "text = Path('notes/hello.txt').read_text()\n"
                "print(text.upper())"
            )
        )
        rec.step(
            tutorial,
            4,
            "read file and run code",
            "sandbox.dispatch(flow_tool_files_read(...)); sandbox.dispatch(flow_tool_code_run(...))",
            "\n\n".join(["read result", _pretty(read), "code result", _pretty(code)]),
        )
    finally:
        backend.close(sandbox)

    rec.step(
        tutorial,
        5,
        "close local sandbox",
        "backend.close(sandbox)",
        "\n".join(
            [
                f"sandbox.closed={sandbox.closed}",
                f"handle_was={handle}",
                f"handle_exists_after_close={Path(handle).exists()}",
                f"sandbox_count={backend.sandbox_count()}",
            ]
        ),
    )


def tutorial_session_loop_tools(rec: Recorder) -> None:
    tutorial = "session-loop-tools"
    responses = [
        _tool_response(
            response_id="scripted-write",
            created=1,
            call_id="call_write",
            name="write_workspace_file",
            arguments={
                "path": "tutorial_loop.txt",
                "content": "created by run_session_loop\n",
            },
        ),
        _tool_response(
            response_id="scripted-shell",
            created=2,
            call_id="call_shell",
            name="run_shell_command",
            arguments={"cmd": "pwd && cat tutorial_loop.txt"},
        ),
        _stop_response(
            response_id="scripted-stop",
            created=3,
            content="done: file created and read back",
        ),
    ]
    rec.step(
        tutorial,
        1,
        "prepare scripted llm",
        "ScriptedSessionLoopExecutor([...tool calls..., stop])",
        "\n".join(
            [
                "response[0] -> write_workspace_file(path='tutorial_loop.txt')",
                "response[1] -> run_shell_command(cmd='pwd && cat tutorial_loop.txt')",
                "response[2] -> final assistant answer",
                "No network or real API key is used in this tutorial run.",
            ]
        ),
    )

    agent_session = Session.from_agent_prompt("Use tools when the user asks for file work.")
    user_session = Session.from_user_message("Create a file, then read it back.").to("local")
    out = run_session_loop(
        user_session=user_session,
        agent_session=agent_session,
        agent_provider=flow.Provider(model="scripted"),
        executor=ScriptedSessionLoopExecutor(responses),
    )
    try:
        rows = []
        for index, row in enumerate(out.chunk_table.rows):
            rows.append(f"[{index}] {row.kind.value}")
            rows.append(_pretty(row.payload))
        rec.step(
            tutorial,
            2,
            "run session loop",
            "run_session_loop(user_session, agent_session, executor=scripted)",
            "\n".join(rows),
        )

        shell_tool = global_system_tools()["run_shell_command"]
        verify = shell_tool(out, {"cmd": "ls -1 && cat tutorial_loop.txt"})
        rec.step(
            tutorial,
            3,
            "verify loop side effect",
            'global_system_tools()["run_shell_command"](out, {"cmd": "ls -1 && cat tutorial_loop.txt"})',
            _pretty(verify),
        )
    finally:
        out.close_sandbox()


def tutorial_custom_flow_tool(rec: Recorder) -> None:
    tutorial = "custom-flow-tool"
    tool = WordCountTool()
    rec.step(
        tutorial,
        1,
        "define custom tool",
        "class WordCountTool(FlowToolCall): ...",
        "\n".join(
            [
                f"name={tool.name}",
                f"description={tool.description}",
                "parameters=" + _pretty(tool.parameters),
                "The tool executes in Python and returns a plain dict.",
            ]
        ),
    )

    responses = [
        _tool_response(
            response_id="scripted-word-count",
            created=1,
            call_id="call_word_count",
            name="word_count",
            arguments={
                "text": "Session carries state and tools produce structured results."
            },
        ),
        _stop_response(
            response_id="scripted-custom-stop",
            created=2,
            content="The text has 8 words and 8 unique words.",
        ),
    ]
    agent_session = Session.from_agent_prompt("Call word_count before answering.")
    user_session = Session.from_user_message("Count the words in this sentence.").to("local")
    out = run_session_loop(
        user_session=user_session,
        agent_session=agent_session,
        agent_provider=flow.Provider(model="scripted"),
        tools=[tool],
        executor=ScriptedSessionLoopExecutor(responses),
    )
    try:
        rows = []
        for index, row in enumerate(out.chunk_table.rows):
            rows.append(f"[{index}] {row.kind.value}")
            rows.append(_pretty(row.payload))
        rec.step(
            tutorial,
            2,
            "run custom tool loop",
            "run_session_loop(..., tools=[WordCountTool()], executor=scripted)",
            "\n".join(rows),
        )
    finally:
        out.close_sandbox()


SECTIONS = {
    "session-basics": tutorial_session_basics,
    "local-sandbox-tools": tutorial_local_sandbox_tools,
    "session-loop-tools": tutorial_session_loop_tools,
    "custom-flow-tool": tutorial_custom_flow_tool,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--section",
        choices=tuple(SECTIONS) + ("all",),
        default="all",
        help="Tutorial section to regenerate.",
    )
    args = parser.parse_args(argv)

    _clean_dirs(None if args.section == "all" else args.section)
    rec = Recorder()
    if args.section == "all":
        for run in SECTIONS.values():
            run(rec)
    else:
        SECTIONS[args.section](rec)
    rec.save()
    print(f"generated {len(rec.manifest)} tutorial steps")
    for item in rec.manifest:
        print(f"- {item['tutorial']} step {item['step']}: {item['title']}")


if __name__ == "__main__":
    main()
