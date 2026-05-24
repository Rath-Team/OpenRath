"""Static guard: :mod:`rath.memory` must not import from :mod:`rath.backend`.

The memory plane and sandbox plane are deliberately parallel and independent.
Any ``from rath.backend …`` or ``import rath.backend`` inside ``rath/memory/``
(excluding ``adapters/``, where third-party adapters may bridge the two) is
a regression.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import rath.memory

_MEMORY_ROOT = Path(rath.memory.__file__).parent


def _python_files() -> list[Path]:
    files = [
        p
        for p in _MEMORY_ROOT.rglob("*.py")
        if "adapters" not in p.relative_to(_MEMORY_ROOT).parts
    ]
    assert files, "expected to find python files under rath/memory/"
    return files


def test_no_from_rath_backend_imports():
    offenders: list[tuple[Path, int, str]] = []
    for path in _python_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("from rath.backend"):
                offenders.append((path, i, line))
            if stripped.startswith("import rath.backend"):
                offenders.append((path, i, line))
    assert not offenders, f"forbidden cross-imports: {offenders!r}"


def test_rath_memory_exposes_public_api():
    expected = {
        "MemoryBackend",
        "MemoryStore",
        "MemoryStoreSpec",
        "MemoryCapabilities",
        "ScopeModel",
        "MemoryOp",
        "MemoryOpWrite",
        "MemoryOpRead",
        "MemoryOpList",
        "MemoryOpTree",
        "MemoryOpFind",
        "MemoryOpSearch",
        "MemoryOpResource",
        "MemoryOpCommit",
        "MemoryResult",
        "MemoryHit",
        "MemoryEntry",
        "MemoryFindResult",
        "MemoryReadResult",
        "MemoryListResult",
        "MemoryWriteResult",
        "MemoryCommitResult",
        "MemoryExecutionFailure",
        "MemoryBackendError",
        "MemoryBackendNotFound",
        "MemoryStoreClosed",
        "UnsupportedMemoryOp",
        "MemoryNotFound",
        "MemoryConflict",
        "register",
        "list_names",
        "get",
        "get_class",
        "is_available",
        "preferred",
        "set_default",
        "current",
    }
    missing = expected - set(dir(rath.memory))
    assert not missing, f"missing public exports: {sorted(missing)}"


def test_rath_memory_registry_only_contains_optional_extras():
    """Importing :mod:`rath.memory` in a fresh interpreter must not register
    any backend whose optional extra is *not* installed.

    ``"local"`` is the always-on default (stdlib only, no extras). The
    OpenViking adapter self-registers on import IFF ``openviking`` is
    importable; that is intentional (mirrors how ``rath.backend`` auto-loads
    OpenSandbox when its extra is present). The contract this test guards
    is the *negative* one: a name only appears in ``list_names()`` when its
    SDK is importable (or, for ``"local"``, when stdlib is present, which is
    trivially always) -- never as a stub.
    """
    script = textwrap.dedent(
        """
        import importlib
        import rath.memory
        names = set(rath.memory.list_names())
        # ``"local"`` is the always-on default; other names must each be
        # backed by an importable optional SDK.
        assert "local" in names, "local backend must always be registered"
        for name in names - {"local"}:
            if name == "openviking":
                importlib.import_module("openviking")
            else:
                raise AssertionError(f"unknown adapter registered: {name!r}")
        print("OK", sorted(names))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_rath_top_level_exposes_memory_submodule():
    import rath

    assert hasattr(rath, "memory")
    # And `memory` is in __all__ alongside the other planes.
    assert "memory" in rath.__all__
