from __future__ import annotations

import json
from pathlib import Path

from rath.server.app import _openapi_document


def test_committed_openapi_matches_generator() -> None:
    committed = json.loads(
        Path("deploy/docs/openapi-v2.json").read_text(encoding="utf-8")
    )
    assert committed == _openapi_document(
        "2.0.0",
        store_enabled=True,
    )


def test_openapi_documents_security_actions_and_schemas() -> None:
    document = _openapi_document("2.0.0rc1", store_enabled=True)
    paths = document["paths"]
    assert paths["/v1/runs"]["post"]["x-openrath-action"] == "run.create"
    assert paths["/metrics"]["get"]["security"] == [{"bearerAuth": []}]
    assert (
        paths["/v1/runs"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/CreateRunRequest"
    )
    assert document["components"]["schemas"]["Run"]["required"]
