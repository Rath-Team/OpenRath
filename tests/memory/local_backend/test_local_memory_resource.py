"""Resource ingest tests for :class:`LocalMemoryBackend`.

Real filesystem; no mocks. HTTP fetches go through a stdlib
``http.server`` running on a thread on ``127.0.0.1`` so no network
egress and no fixtures from third-party libs.
"""

from __future__ import annotations

import hashlib
import http.server
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from rath.memory import MemoryStore
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.op_types import MemoryOpResource
from rath.memory.results import (
    MemoryExecutionFailure,
    MemoryWriteResult,
)

# ----------------------------------------------------- Local-file ingestion


def test_resource_ingest_local_file_creates_dir(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    src = tmp_path / "note.txt"
    src.write_text("hello resource", encoding="utf-8")
    res = backend.dispatch(store, MemoryOpResource(source=str(src)))
    assert isinstance(res, MemoryWriteResult)
    assert res.uri.startswith("viking://resources/")
    assert res.bytes_written == len("hello resource".encode("utf-8"))

    sha = hashlib.sha256(b"hello resource").hexdigest()[:16]
    root = Path(store.handle) / "resources" / sha
    assert root.is_dir()
    # Raw blob + metadata both land under the SHA directory.
    blob = root / "source.txt"
    assert blob.is_file()
    assert blob.read_bytes() == b"hello resource"
    meta = root / "meta.md"
    assert meta.is_file()
    body = meta.read_text(encoding="utf-8")
    assert "note.txt" in body  # original filename surfaces in meta


def test_resource_ingest_records_reason_and_instruction(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    src = tmp_path / "x.txt"
    src.write_text("body", encoding="utf-8")
    res = backend.dispatch(
        store,
        MemoryOpResource(
            source=str(src),
            reason="why we kept it",
            instruction="summarise in one line",
        ),
    )
    assert isinstance(res, MemoryWriteResult)
    sha = hashlib.sha256(b"body").hexdigest()[:16]
    meta_body = (Path(store.handle) / "resources" / sha / "meta.md").read_text(
        encoding="utf-8"
    )
    assert "why we kept it" in meta_body
    assert "summarise in one line" in meta_body


def test_resource_ingest_is_idempotent_on_same_bytes(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    src = tmp_path / "dup.txt"
    src.write_text("same bytes", encoding="utf-8")

    r1 = backend.dispatch(store, MemoryOpResource(source=str(src)))
    assert isinstance(r1, MemoryWriteResult)
    sha = hashlib.sha256(b"same bytes").hexdigest()[:16]
    blob = Path(store.handle) / "resources" / sha / "source.txt"
    first_mtime = blob.stat().st_mtime_ns

    r2 = backend.dispatch(store, MemoryOpResource(source=str(src)))
    assert isinstance(r2, MemoryWriteResult)
    assert r2.uri == r1.uri
    # Second ingest must NOT rewrite the blob — dedup short-circuits.
    assert blob.stat().st_mtime_ns == first_mtime


def test_resource_ingest_missing_local_file_is_not_found(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    res = backend.dispatch(store, MemoryOpResource(source=str(tmp_path / "nope.txt")))
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "not_found"


def test_resource_ingest_rejects_unknown_target_scope(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    src = tmp_path / "y.txt"
    src.write_text("z", encoding="utf-8")
    res = backend.dispatch(
        store,
        MemoryOpResource(source=str(src), target_uri="viking://bogus"),
    )
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


def test_resource_ingest_honours_explicit_target_uri(
    backend: LocalMemoryBackend, store: MemoryStore, tmp_path: Path
) -> None:
    src = tmp_path / "explicit.bin"
    src.write_bytes(b"\x00\x01\x02hello")
    res = backend.dispatch(
        store,
        MemoryOpResource(
            source=str(src),
            target_uri="viking://user/memories/inbox",
        ),
    )
    assert isinstance(res, MemoryWriteResult)
    assert res.uri.startswith("viking://user/memories/inbox/")
    sha = hashlib.sha256(b"\x00\x01\x02hello").hexdigest()[:16]
    assert res.uri.endswith(sha)
    root = Path(store.handle) / "user" / "memories" / "inbox" / sha
    assert root.is_dir()
    assert (root / "source.bin").read_bytes() == b"\x00\x01\x02hello"


# ----------------------------------------------------- HTTP ingestion


class _ServeBody(http.server.BaseHTTPRequestHandler):
    """Tiny in-memory HTTP handler — returns ``BODY`` for any GET."""

    BODY = b"<html>resource fetched via http</html>"

    def do_GET(self) -> None:  # noqa: N802 -- stdlib name
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.BODY)))
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, *_a, **_k) -> None:  # noqa: D401 -- silence stdlib
        return


@pytest.fixture
def http_server() -> Iterator[str]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = http.server.HTTPServer(("127.0.0.1", port), _ServeBody)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/asset.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_resource_ingest_http_url_persists_body(
    backend: LocalMemoryBackend, store: MemoryStore, http_server: str
) -> None:
    res = backend.dispatch(store, MemoryOpResource(source=http_server))
    assert isinstance(res, MemoryWriteResult), res
    sha = hashlib.sha256(_ServeBody.BODY).hexdigest()[:16]
    root = Path(store.handle) / "resources" / sha
    assert root.is_dir()
    blob = root / "source.html"
    assert blob.is_file()
    assert blob.read_bytes() == _ServeBody.BODY
    meta_body = (root / "meta.md").read_text(encoding="utf-8")
    assert "127.0.0.1" in meta_body  # original URL in meta
