from __future__ import annotations

from rath.backend import BackendCapability, get


def test_local_backend_declares_no_container_features() -> None:
    features = get("local").capabilities().features
    assert BackendCapability.PER_TASK_IMAGE not in features
    assert BackendCapability.HOST_DOCKER not in features


def test_opensandbox_backend_can_open_a_task_specified_image() -> None:
    from rath.backend.opensandbox import OpenSandboxBackend

    features = OpenSandboxBackend.capabilities().features
    assert BackendCapability.PER_TASK_IMAGE in features
    assert BackendCapability.NETWORK_ISOLATION in features
    # Scoring in a second container needs the host daemon; a container-based
    # sandbox cannot provide it.
    assert BackendCapability.HOST_DOCKER not in features
