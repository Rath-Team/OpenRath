"""Local-backend-only tests (always-on, temp and user-supplied working dirs)."""

from __future__ import annotations

import os
import sys

import pytest

from rath.backend import (
    BackendSandboxSpec,
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
    IsolationLevel,
    ToolExecutionFailure,
    get,
)
from rath.backend.local import LocalBackend, TrustedHostBackend


def test_is_available_is_true() -> None:
    assert LocalBackend.is_available() is True


def test_capabilities_match_spec() -> None:
    cap = LocalBackend.capabilities()
    assert cap.isolation is IsolationLevel.PROCESS
    assert cap.supports_command is True
    assert cap.supports_filesystem is True
    assert cap.supports_code_interpreter is True
    assert cap.max_sandboxes is None


def test_supported_calls_covers_all_phase1_types() -> None:
    expected = {
        BackendToolCommandRun,
        BackendToolFilesRead,
        BackendToolFilesWrite,
        BackendToolFilesList,
        BackendToolFilesExists,
        BackendToolCodeRun,
    }
    assert LocalBackend.supported_calls() == expected


def test_local_is_registered_under_name_local() -> None:
    inst = get("local")
    assert isinstance(inst, LocalBackend)
    assert inst.name == "local"


def test_trusted_host_is_the_canonical_explicit_backend_name() -> None:
    inst = get("trusted-host")
    assert isinstance(inst, TrustedHostBackend)
    assert not isinstance(inst, LocalBackend)
    assert inst.name == "trusted-host"


def test_handle_is_a_real_working_directory() -> None:
    backend = get("local")
    sb = backend.open()
    try:
        assert os.path.isdir(sb.handle)
    finally:
        backend.close(sb)


def test_close_removes_working_directory() -> None:
    backend = get("local")
    sb = backend.open()
    handle = sb.handle
    backend.close(sb)
    assert not os.path.exists(handle)


def test_user_supplied_working_dir_honoured(tmp_path: object) -> None:
    backend = get("local")
    target = str(tmp_path)  # type: ignore[arg-type]
    sb = backend.open(BackendSandboxSpec(working_dir=target))
    try:
        assert sb.handle == target
    finally:
        backend.close(sb)
    assert os.path.isdir(target)


def test_close_does_not_remove_user_supplied_working_dir(tmp_path: object) -> None:
    """``close()`` must NOT rmtree a directory the caller supplied."""
    import pathlib

    target = pathlib.Path(str(tmp_path)) / "keep"  # type: ignore[arg-type]
    target.mkdir()
    sentinel = target / "important.txt"
    sentinel.write_text("do not delete me", encoding="utf-8")

    backend = get("local")
    sb = backend.open(BackendSandboxSpec(working_dir=str(target)))
    backend.close(sb)

    assert target.is_dir(), "user-supplied working_dir was removed by close()"
    assert sentinel.read_text(encoding="utf-8") == "do not delete me"


def test_filesystem_calls_reject_absolute_paths_outside_workspace(
    tmp_path: object,
) -> None:
    import pathlib

    root = pathlib.Path(str(tmp_path)) / "workspace"  # type: ignore[arg-type]
    outside = pathlib.Path(str(tmp_path)) / "outside.txt"  # type: ignore[arg-type]
    root.mkdir()
    outside.write_text("secret", encoding="utf-8")
    backend = LocalBackend()
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        result = sb.dispatch(BackendToolFilesRead(path=str(outside)))
    finally:
        backend.close(sb)

    assert isinstance(result, ToolExecutionFailure)
    assert result.kind == "path_violation"
    assert "outside sandbox workspace" in result.message


def test_filesystem_calls_reject_parent_traversal(tmp_path: object) -> None:
    import pathlib

    root = pathlib.Path(str(tmp_path)) / "workspace"  # type: ignore[arg-type]
    root.mkdir()
    backend = LocalBackend()
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        result = sb.dispatch(BackendToolFilesWrite(path="../escape.txt", data="x"))
    finally:
        backend.close(sb)

    assert isinstance(result, ToolExecutionFailure)
    assert result.kind == "path_violation"
    assert not (root.parent / "escape.txt").exists()


def test_command_cwd_must_remain_in_workspace(tmp_path: object) -> None:
    import pathlib

    root = pathlib.Path(str(tmp_path)) / "workspace"  # type: ignore[arg-type]
    root.mkdir()
    backend = LocalBackend()
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        result = sb.dispatch(
            BackendToolCommandRun(
                cmd=[sys.executable, "-c", "print('should not run')"],
                cwd="..",
            )
        )
    finally:
        backend.close(sb)

    assert isinstance(result, ToolExecutionFailure)
    assert result.kind == "path_violation"


def test_symlink_escape_is_rejected_when_supported(tmp_path: object) -> None:
    import pathlib

    root = pathlib.Path(str(tmp_path)) / "workspace"  # type: ignore[arg-type]
    outside = pathlib.Path(str(tmp_path)) / "outside"  # type: ignore[arg-type]
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    backend = LocalBackend()
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        result = sb.dispatch(BackendToolFilesRead(path="link/secret.txt"))
    finally:
        backend.close(sb)

    assert isinstance(result, ToolExecutionFailure)
    assert result.kind == "path_violation"


def test_command_missing_executable_returns_failure() -> None:
    backend = get("local")
    with backend.open() as sb:
        r = sb.dispatch(
            BackendToolCommandRun(cmd=["/nonexistent/rath_no_such_exe_xyz"])
        )
        assert isinstance(r, ToolExecutionFailure)
        assert r.kind in ("os_error", "unexpected")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Path.chmod on Windows does not reliably strip write bits "
        "(POSIX-style mode bits don't map onto NTFS ACLs); the test's "
        "premise of an unwritable parent cannot be set up portably here. "
        "Reported on PR #3 by an upstream Windows run."
    ),
)
def test_files_write_returns_failure_when_parent_unwritable(tmp_path: object) -> None:
    """OSError on write must surface as ToolExecutionFailure, not bubble up."""
    import pathlib
    import stat

    root = pathlib.Path(str(tmp_path)) / "ro"  # type: ignore[arg-type]
    root.mkdir()
    backend = get("local")
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        # Remove all write bits from the sandbox root so writing a new file
        # under it raises PermissionError on POSIX.
        root.chmod(stat.S_IRUSR | stat.S_IXUSR)
        r = sb.dispatch(BackendToolFilesWrite(path="should_fail.txt", data="x"))
        assert isinstance(r, ToolExecutionFailure)
        assert r.kind == "os_error"
    finally:
        # Restore permissions so tmp_path cleanup doesn't fail.
        root.chmod(stat.S_IRWXU)
        backend.close(sb)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Path.chmod on Windows cannot make a directory truly unreadable "
        "(NTFS ACLs aren't reachable from POSIX mode bits); same root cause "
        "as test_files_write_returns_failure_when_parent_unwritable."
    ),
)
def test_files_exists_returns_false_on_permission_denied(tmp_path: object) -> None:
    """exists() against an unreadable parent must return False, not raise."""
    import pathlib
    import stat

    root = pathlib.Path(str(tmp_path)) / "denied"  # type: ignore[arg-type]
    root.mkdir()
    backend = get("local")
    sb = backend.open(BackendSandboxSpec(working_dir=str(root)))
    try:
        # No-permission directory: stat on a child should raise OSError;
        # _files_exists must swallow it and return False.
        root.chmod(0)
        result = sb.dispatch(BackendToolFilesExists(path="anything"))
        assert result is False
    finally:
        root.chmod(stat.S_IRWXU)
        backend.close(sb)
