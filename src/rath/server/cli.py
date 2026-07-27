"""Agent Server and schema migration command-line entry points."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import os
import signal
import threading
from typing import Any


def _load_reference(reference: str) -> Any:
    if ":" not in reference:
        raise ValueError("OPENRATH_APP must use module:attribute syntax")
    module_name, attribute = reference.split(":", 1)
    value = getattr(importlib.import_module(module_name), attribute)
    if callable(value) and not hasattr(value, "router"):
        value = value()
    return value


def _load_app(reference: str) -> Any:
    value = _load_reference(reference)
    return getattr(value, "app", value)


def server_main() -> None:
    parser = argparse.ArgumentParser(prog="openrath-server")
    parser.add_argument(
        "--app",
        default=os.getenv("OPENRATH_APP"),
        help="ASGI application factory or object as module:attribute",
    )
    parser.add_argument("--host", default=os.getenv("OPENRATH_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("OPENRATH_PORT", "8000"))
    )
    parser.add_argument(
        "--workers", type=int, default=int(os.getenv("OPENRATH_WEB_WORKERS", "1"))
    )
    arguments = parser.parse_args()
    if not arguments.app:
        parser.error("--app or OPENRATH_APP is required")
    if arguments.workers != 1:
        parser.error(
            "process workers must be 1; scale OpenRath with container replicas"
        )
    import uvicorn

    uvicorn.run(
        _load_app(arguments.app),
        host=arguments.host,
        port=arguments.port,
        workers=arguments.workers,
        proxy_headers=False,
        server_header=False,
    )


def migrate_main() -> None:
    parser = argparse.ArgumentParser(prog="openrath-migrate")
    parser.add_argument(
        "--dsn",
        default=os.getenv("OPENRATH_POSTGRES_DSN"),
        help="PostgreSQL DSN; defaults to OPENRATH_POSTGRES_DSN",
    )
    parser.add_argument("--schema", default=os.getenv("OPENRATH_DB_SCHEMA", "openrath"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the current schema without applying changes",
    )
    arguments = parser.parse_args()
    if not arguments.dsn:
        parser.error("--dsn or OPENRATH_POSTGRES_DSN is required")
    if arguments.check:
        import psycopg
        from psycopg import sql

        with psycopg.connect(arguments.dsn) as connection:
            value = connection.execute(
                sql.SQL(
                    "SELECT version FROM {}.schema_migrations ORDER BY version DESC LIMIT 1"
                ).format(sql.Identifier(arguments.schema))
            ).fetchone()
        if value is None or int(value[0]) < 1:
            raise SystemExit("OpenRath schema is not current")
        return
    from rath.runtime import PostgresRunStore

    PostgresRunStore(arguments.dsn, schema=arguments.schema).close()


def worker_main() -> None:
    parser = argparse.ArgumentParser(prog="openrath-worker")
    parser.add_argument(
        "--app",
        default=os.getenv("OPENRATH_APP"),
        help="AgentServer object or factory as module:attribute",
    )
    parser.add_argument(
        "--worker-id",
        default=os.getenv("OPENRATH_WORKER_ID", os.getenv("HOSTNAME", "worker")),
    )
    parser.add_argument(
        "--lease-seconds",
        type=float,
        default=float(os.getenv("OPENRATH_WORKER_LEASE_SECONDS", "30")),
    )
    arguments = parser.parse_args()
    if not arguments.app:
        parser.error("--app or OPENRATH_APP is required")
    server = _load_reference(arguments.app)
    if not hasattr(server, "runtime") or not hasattr(server, "store"):
        parser.error("worker application reference must resolve to AgentServer")
    stopped = threading.Event()

    def stop(signum: int, frame: object) -> None:
        stopped.set()

    for name in ("SIGINT", "SIGTERM"):
        with contextlib.suppress(AttributeError):
            signal.signal(getattr(signal, name), stop)
    while not stopped.is_set():
        server.store.expire_interrupts()
        server.store.requeue_expired_leases()
        result = server.runtime.work_once(
            worker_id=arguments.worker_id,
            lease_seconds=arguments.lease_seconds,
        )
        stopped.wait(0 if result is not None else 0.1)
