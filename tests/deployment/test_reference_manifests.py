from __future__ import annotations

import re
from pathlib import Path


def test_external_reference_images_are_digest_pinned() -> None:
    compose = Path("deploy/compose/compose.yaml").read_text(encoding="utf-8")
    for image in re.findall(r"^\s+image:\s+(\S+)", compose, flags=re.MULTILINE):
        if image.startswith("openrath:"):
            continue
        assert "@sha256:" in image, image

    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")
    for image in re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE):
        assert "@sha256:" in image, image


def test_kubernetes_template_covers_workloads_and_dns() -> None:
    manifest = Path("deploy/kubernetes/openrath.yaml").read_text(encoding="utf-8")
    assert 'values: ["openrath", "openrath-worker", "openrath-migrate"]' in manifest
    assert "protocol: UDP\n          port: 53" in manifest
    assert "protocol: TCP\n          port: 53" in manifest
    assert manifest.count("Release automation must replace") == 3
    assert "imagePullPolicy: Always" in manifest


def test_production_workflow_pins_actions_and_service_images() -> None:
    workflow = Path(".github/workflows/ci-v2-production.yml").read_text(
        encoding="utf-8"
    )
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in workflow
    assert "postgres:17-alpine@sha256:" in workflow
    assert "redis:8-alpine@sha256:" in workflow
    assert "minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:" in workflow
    assert "pip-audit" in workflow
    assert "scanners: secret" in workflow
