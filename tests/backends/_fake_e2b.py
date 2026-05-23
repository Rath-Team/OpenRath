"""In-memory stand-in for ``e2b_code_interpreter.Sandbox`` used by adapter tests.

Records ``kill()`` calls so refcount tests can verify exactly-once teardown.
Each instance carries an in-memory filesystem dict so files.* operations
round-trip without touching disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class _FakeCommandResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class _FakeExecution:
    text: str | None
    logs: Any
    error: Any
    exit_code: int = 0


@dataclass
class _FakeLogs:
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)


@dataclass
class _FakeCommands:
    _parent: "FakeSandbox"

    def run(
        self,
        cmd: str | list[str],
        cwd: str | None = None,
        envs: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> _FakeCommandResult:
        # Deterministic stand-in: ignores ``cmd`` content; tests assert on the
        # fixed "ok\n" payload. Adjust here if a future test needs branching.
        self._parent.last_command = (cmd, cwd, envs, timeout)
        return _FakeCommandResult(stdout="ok\n", stderr="", exit_code=0)


@dataclass
class _FakeFiles:
    _parent: "FakeSandbox"

    def read(self, path: str) -> str:
        return self._parent.fs[path]

    def write(self, path: str, data: bytes | str) -> None:
        payload = data.decode("utf-8") if isinstance(data, bytes) else data
        self._parent.fs[path] = payload

    def list(self, path: str) -> list[Any]:
        from types import SimpleNamespace

        prefix = path.rstrip("/") + "/"
        names = sorted({
            p[len(prefix):].split("/", 1)[0]
            for p in self._parent.fs
            if p.startswith(prefix)
        })
        return [
            SimpleNamespace(name=n, path=prefix + n, type="file") for n in names
        ]

    def exists(self, path: str) -> bool:
        return path in self._parent.fs


class FakeSandbox:
    """Drop-in stand-in for ``e2b_code_interpreter.Sandbox``."""

    def __init__(self, template: str | None = None) -> None:
        self.sandbox_id = f"fake-{uuid4().hex[:8]}"
        self.template = template
        self.fs: dict[str, str] = {}
        self.kill_count = 0
        self.last_command: tuple[Any, ...] | None = None
        self.commands = _FakeCommands(self)
        self.files = _FakeFiles(self)

    @classmethod
    def create(
        cls,
        template: str | None = None,
        timeout: float | None = None,
        envs: dict[str, str] | None = None,
    ) -> "FakeSandbox":
        return cls(template=template)

    @classmethod
    def connect(cls, sandbox_id: str) -> "FakeSandbox":
        inst = cls(template=None)
        inst.sandbox_id = sandbox_id
        return inst

    def kill(self) -> None:
        self.kill_count += 1

    def run_code(self, code: str, language: str | None = None) -> _FakeExecution:
        logs = _FakeLogs(stdout=[f"ran {len(code)} bytes\n"])
        return _FakeExecution(text="42", logs=logs, error=None, exit_code=0)
