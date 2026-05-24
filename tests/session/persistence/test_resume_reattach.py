"""``PersistedSession.to_resumable_pair`` reattaches to the recorded opensandbox.

Persists a session whose header records an opensandbox remote id via
:class:`PersistentSandboxRegistry`, then loads + revives it and asserts the
returned user session is bound to a sandbox whose handle matches the
original remote id — i.e. the registry's ``attach`` path ran instead of a
fresh ``open``.
"""

from __future__ import annotations

import pytest

from rath.backend import get
from rath.backend.persistence.registry import PersistentSandboxRegistry
from rath.session.chunk import ChunkTable, user_text_chunk
from rath.session.persistence import SessionWriter, load_session
from rath.session.session import Session
from tests.conftest import opensandbox_real


@opensandbox_real
@pytest.mark.opensandbox
def test_resume_reattaches_to_recorded_opensandbox() -> None:
    backend = get("opensandbox")
    sb = backend.open()
    sb.acquire()
    original_handle = sb.handle
    try:
        reg = PersistentSandboxRegistry()
        sandbox_uuid = reg.record_remote(
            backend="opensandbox",
            remote_id=sb.handle,
            spec=sb.spec,
        )

        s = Session(
            chunk_table=ChunkTable(rows=(user_text_chunk("hi"),)),
            sandbox_backend="opensandbox",
            _sandbox_open_spec=sb.spec,
        )
        with SessionWriter(s, sandbox_handle_id=str(sandbox_uuid)) as writer:
            writer.write_chunk(0, s.chunk_table.rows[0])

        loaded = load_session(s.id)
        assert loaded.header.sandbox_backend == "opensandbox"
        assert loaded.header.sandbox_handle_id == str(sandbox_uuid)

        user, _agent = loaded.to_resumable_pair()
        try:
            assert user.sandbox is not None, "resume should reattach the sandbox"
            assert user.sandbox.handle == original_handle, (
                "reattach must point at the same remote container"
            )
            assert user.sandbox is not sb, (
                "reattach should produce a new BackendSandbox handle object "
                "(refcount on the original is untouched)"
            )
        finally:
            user.close_sandbox()
    finally:
        sb.release()
