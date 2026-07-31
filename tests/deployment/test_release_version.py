from __future__ import annotations

import json
import re
from pathlib import Path

RELEASE_VERSION = "2.0.0"


def test_release_version_surfaces_are_consistent() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    assert match.group(1) == RELEASE_VERSION

    openapi = json.loads(
        Path("deploy/docs/openapi-v2.json").read_text(encoding="utf-8")
    )
    assert openapi["info"]["version"] == RELEASE_VERSION

    compose = Path("deploy/compose/compose.yaml").read_text(encoding="utf-8")
    kubernetes = Path("deploy/kubernetes/openrath.yaml").read_text(encoding="utf-8")
    assert compose.count(f"openrath:{RELEASE_VERSION}") == 3
    assert kubernetes.count(f"openrath:{RELEASE_VERSION}") == 3

    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")
    assert 'org.opencontainers.image.version="${OPENRATH_VERSION}"' in dockerfile
    assert 'org.opencontainers.image.revision="${OPENRATH_REVISION}"' in dockerfile
