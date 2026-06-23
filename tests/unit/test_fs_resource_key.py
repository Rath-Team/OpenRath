"""Filesystem tools must serialize on one resource-key per path.

The async tool runner groups one round's tool calls into lanes keyed by
:meth:`FlowToolCall.resource_key` and runs each lane sequentially while
different lanes fan out concurrently. If read and write of the *same* path
returned different keys they would land in different lanes and race, so a
read could observe the file before or mid-write. These tests pin the
contract: same path -> same key across every fs operation; different paths
-> different keys.
"""

from __future__ import annotations

from rath.flow.tool.system_tool import (
    FlowToolFilesExists,
    FlowToolFilesList,
    FlowToolFilesRead,
    FlowToolFilesWrite,
)

_FS_TOOLS = [
    FlowToolFilesWrite(),
    FlowToolFilesRead(),
    FlowToolFilesList(),
    FlowToolFilesExists(),
]


def test_same_path_shares_one_key_across_all_fs_ops() -> None:
    keys = {tool.resource_key({"path": "/work/a.txt"}) for tool in _FS_TOOLS}
    assert len(keys) == 1, f"fs ops on one path must share a lane, got {keys}"


def test_write_and_read_same_path_serialize() -> None:
    write_key = FlowToolFilesWrite().resource_key({"path": "/work/a.txt"})
    read_key = FlowToolFilesRead().resource_key({"path": "/work/a.txt"})
    assert write_key == read_key


def test_distinct_paths_get_distinct_keys() -> None:
    a = FlowToolFilesWrite().resource_key({"path": "/work/a.txt"})
    b = FlowToolFilesWrite().resource_key({"path": "/work/b.txt"})
    assert a != b


def test_missing_path_is_handled() -> None:
    # Falls back to a stable sentinel key rather than raising.
    key = FlowToolFilesRead().resource_key({})
    assert key[0] == "fs"
