"""Inventory and import v1 JSONL Sessions as immutable v2 legacy Runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from rath.artifacts import LocalArtifactStore
from rath.runtime import PostgresRunStore, Run, RunStatus
from rath.server import PostgresResourceStore, SessionRecord
from rath.session.persistence.loader import load_session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--postgres-dsn")
    parser.add_argument("--schema", default="openrath")
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        parser.error("--source must be an existing v1 sessions directory")
    if args.apply and (not args.postgres_dsn or not args.artifact_root):
        parser.error("--apply requires --postgres-dsn and --artifact-root")

    candidates = sorted(
        [
            *source.glob("*.jsonl"),
            *source.glob("*.jsonl.__partial__"),
        ]
    )
    rows: list[dict[str, object]] = []
    runtime = (
        PostgresRunStore(args.postgres_dsn, schema=args.schema)
        if args.apply
        else None
    )
    resources = PostgresResourceStore(runtime) if runtime is not None else None
    artifacts = (
        LocalArtifactStore(args.artifact_root, max_bytes=1024 * 1024 * 1024)
        if args.apply
        else None
    )
    try:
        for path in candidates:
            session_id = UUID(path.name.split(".jsonl", 1)[0])
            try:
                legacy = load_session(session_id, path=path)
                row: dict[str, object] = {
                    "session_id": str(session_id),
                    "path": str(path),
                    "closed": legacy.closed,
                    "created_at": legacy.header.created_at.isoformat(),
                    "chunks": len(legacy.chunk_table.rows),
                    "status": "ready",
                }
                if runtime is not None and resources is not None and artifacts is not None:
                    artifact = artifacts.put(
                        args.tenant,
                        path.read_bytes(),
                        media_type="application/x-ndjson",
                        metadata={
                            "provenance": "legacy-import",
                            "legacy_session_id": str(session_id),
                        },
                    )
                    resources.ensure_session(
                        SessionRecord(
                            id=session_id,
                            tenant_id=args.tenant,
                            created_at=legacy.header.created_at,
                        )
                    )
                    run = Run.create(
                        id=uuid5(NAMESPACE_URL, f"openrath:v1:{session_id}"),
                        plan_id=uuid5(NAMESPACE_URL, "openrath:v1:transcript-import"),
                        revision_id=uuid5(NAMESPACE_URL, "openrath:v1.3.0"),
                        session_id=session_id,
                        tenant_id=args.tenant,
                        status=(
                            RunStatus.SUCCEEDED
                            if legacy.closed
                            else RunStatus.NEEDS_REVIEW
                        ),
                        state={
                            "legacy": True,
                            "resumable": False,
                            "artifact_uri": artifact.uri,
                            "chunk_count": len(legacy.chunk_table.rows),
                            "trust": "untrusted",
                            "provenance": "legacy-import",
                        },
                        idempotency_key=f"legacy-session:{session_id}",
                        context={
                            "migration": "v1-to-v2",
                            "provenance": "legacy-import",
                        },
                    )
                    runtime.create_run(run)
                    row["status"] = "imported"
                    row["run_id"] = str(run.id)
                    row["artifact_uri"] = artifact.uri
                rows.append(row)
            except Exception as exc:
                rows.append(
                    {
                        "session_id": str(session_id),
                        "path": str(path),
                        "status": "invalid",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    finally:
        if runtime is not None:
            runtime.close()

    report = {
        "schema": "openrath.v2.migration-report/1",
        "mode": "apply" if args.apply else "inventory",
        "source": str(source),
        "tenant": args.tenant,
        "summary": {
            "total": len(rows),
            "ready": sum(item["status"] == "ready" for item in rows),
            "imported": sum(item["status"] == "imported" for item in rows),
            "invalid": sum(item["status"] == "invalid" for item in rows),
        },
        "sessions": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
