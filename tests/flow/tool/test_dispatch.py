from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel

from rath.backend import (
    CodeResult,
    CommandResult,
    FileContent,
    FileEntries,
    FileEntry,
    FileWriteResult,
    ToolExecutionFailure,
    get,
)
from rath.flow.tool import (
    FlowToolCall,
    dispatch_flow_tool,
    project_tool_result,
    serialize_tool_result,
)
from rath.session import Session


class _Tool(FlowToolCall):
    def __init__(self, result: Any = None) -> None:
        self.result = result

    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object"}

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        return self.result


class _Payload(BaseModel):
    value: str


def test_result_projection_matches_serialized_content() -> None:
    values = [
        CommandResult(0, b"out", b"err", 1.5),
        CodeResult("value", b"out", b"err", None),
        FileContent("hello"),
        FileContent(b"bytes"),
        FileEntries((FileEntry("a", "/a", False),)),
        FileWriteResult(7),
        True,
        ToolExecutionFailure("backend_error", "failed", "detail"),
        _Payload(value="model"),
        {"nested": [1, "two"]},
        ["json", 3],
        object(),
    ]
    tool = _Tool()
    for raw in values:
        projection = project_tool_result(tool, raw)
        content = serialize_tool_result(tool, raw)
        assert json.loads(content) == projection


def test_dispatch_resource_key_exception_becomes_failure() -> None:
    class _BadKey(_Tool):
        parallel_safe = True

        def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
            raise ValueError("bad key")

    result = dispatch_flow_tool(Session.create("empty"), _BadKey(), {})
    assert result.failed
    assert isinstance(result.raw, ToolExecutionFailure)
    assert result.raw.kind == "tool_execution_exception"
    assert result.raw.message == "ValueError: bad key"
    assert result.raw.detail == "ValueError"
    assert json.loads(result.content) == result.projection


def test_dispatch_call_exception_becomes_failure() -> None:
    class _BadCall(_Tool):
        def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
            raise RuntimeError("boom")

    result = dispatch_flow_tool(Session.create("empty"), _BadCall(), {})
    assert result.failed
    assert isinstance(result.raw, ToolExecutionFailure)
    assert result.raw.kind == "tool_execution_exception"
    assert result.raw.message == "RuntimeError: boom"
    assert result.raw.detail == "RuntimeError"


class _CountingTool(_Tool):
    def __init__(self, *, parallel_safe: bool) -> None:
        super().__init__({"ok": True})
        self.parallel_safe = parallel_safe
        self._counter_lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("resource", str(arguments.get("key", "global")))

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        with self._counter_lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(0.05)
        with self._counter_lock:
            self.in_flight -= 1
        return self.result


def _dispatch_many(tool: _CountingTool, keys: list[str]) -> None:
    session = Session.create("empty")
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        results = list(
            pool.map(
                lambda key: dispatch_flow_tool(session, tool, {"key": key}),
                keys,
            )
        )
    assert all(not result.failed for result in results)


def test_same_unsafe_tool_instance_serializes_across_callers() -> None:
    tool = _CountingTool(parallel_safe=False)
    _dispatch_many(tool, ["a", "b", "c", "d"])
    assert tool.peak == 1


def test_safe_tool_same_resource_key_serializes() -> None:
    tool = _CountingTool(parallel_safe=True)
    _dispatch_many(tool, ["same"] * 4)
    assert tool.peak == 1


def test_safe_tool_distinct_resource_keys_overlap() -> None:
    tool = _CountingTool(parallel_safe=True)
    _dispatch_many(tool, ["a", "b", "c", "d"])
    assert tool.peak >= 2


class _SandboxScopedTool(_CountingTool):
    """Stands in for the built-ins: one shared instance, per-sandbox resource."""

    sandbox_scoped = True


def _dispatch_across_sandboxes(tool: _CountingTool, count: int) -> None:
    def _run(_index: int) -> None:
        backend = get("local")
        with backend.open() as sandbox:
            session = Session.from_user_message("u").bind_sandbox(sandbox)
            assert not dispatch_flow_tool(session, tool, {"key": "same"}).failed

    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(_run, range(count)))


def test_sandbox_scoped_tool_overlaps_across_independent_sandboxes() -> None:
    # The built-ins are process-wide singletons. Without a per-sandbox lane a
    # single shared instance would serialize every environment in the process,
    # which would make parallel rollout collection sequential.
    unsafe = _SandboxScopedTool(parallel_safe=False)
    _dispatch_across_sandboxes(unsafe, 4)
    assert unsafe.peak >= 2

    safe = _SandboxScopedTool(parallel_safe=True)
    _dispatch_across_sandboxes(safe, 4)
    assert safe.peak >= 2


def test_sandbox_scoped_tool_still_serializes_within_one_sandbox() -> None:
    tool = _SandboxScopedTool(parallel_safe=False)
    backend = get("local")
    with backend.open() as sandbox:
        session = Session.from_user_message("u").bind_sandbox(sandbox)
        sibling = Session.from_user_message("u2").bind_sandbox(sandbox)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(
                pool.map(
                    lambda s: dispatch_flow_tool(s, tool, {"key": "same"}),
                    [session, sibling, session, sibling],
                )
            )
    assert tool.peak == 1
