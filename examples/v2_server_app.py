"""Minimal standalone OpenRath v2 reference application."""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, PostgresEffectLedger, PostgresRunStore
from rath.security import (
    Principal,
    PrincipalKind,
    SecurityContext,
    StructuredAuditSink,
)
from rath.server import AgentServer, StaticTokenAuth
from rath.session import Session


class EchoWorkflow(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY)
    def echo(self, state, context):  # type: ignore[no-untyped-def]
        return {**state, "completed": True}

    def forward(self, session: Session) -> Session:
        return session


class SlowWorkflow(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY, timeout_seconds=60)
    async def wait(self, state, context):  # type: ignore[no-untyped-def]
        delay = min(max(float(state.get("delay", 1)), 0), 30)
        await asyncio.sleep(delay)
        return {**state, "completed": True}

    def forward(self, session: Session) -> Session:
        return session


dsn = os.environ["OPENRATH_POSTGRES_DSN"]
token = os.environ["OPENRATH_TOKEN"]
tenant_id = os.getenv("OPENRATH_TENANT_ID", "default")
grants = frozenset(
    grant.strip()
    for grant in os.environ["OPENRATH_GRANTS"].split(",")
    if grant.strip()
)
if not grants or "*" in grants:
    raise RuntimeError(
        "OPENRATH_GRANTS must contain explicit action grants and must not use '*'"
    )
store = PostgresRunStore(
    dsn,
    schema=os.getenv("OPENRATH_DB_SCHEMA", "openrath"),
    auto_migrate=False,
    pool_max_size=int(os.getenv("OPENRATH_DB_POOL_MAX_SIZE", "20")),
)
effect_ledger = PostgresEffectLedger(
    dsn,
    schema=os.getenv("OPENRATH_DB_SCHEMA", "openrath"),
)
runtime = LocalRuntime(store, effect_ledger=effect_ledger, production_mode=True)
server = AgentServer(
    store,
    runtime,
    auth=StaticTokenAuth(
        {
            token: SecurityContext(
                principal=Principal(id="reference-user", kind=PrincipalKind.SERVICE),
                tenant_id=tenant_id,
                grants=grants,
            )
        }
    ),
    audit_sink=StructuredAuditSink(),
    embedded_worker=os.getenv("OPENRATH_EMBEDDED_WORKER", "true").lower() == "true",
    worker_id=os.getenv("HOSTNAME", "standalone-worker"),
    worker_lease_seconds=float(os.getenv("OPENRATH_WORKER_LEASE_SECONDS", "30")),
)
server.register_assistant(
    "echo",
    EchoWorkflow(),
    revision_id=UUID(
        os.getenv("OPENRATH_REVISION_ID", "00000000-0000-4000-8000-000000000001")
    ),
)
server.register_assistant(
    "slow",
    SlowWorkflow(),
    revision_id=UUID(
        os.getenv(
            "OPENRATH_SLOW_REVISION_ID",
            "00000000-0000-4000-8000-000000000002",
        )
    ),
)
app = server.app
