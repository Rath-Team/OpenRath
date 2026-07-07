"""P2.6 — opensandbox default image/entrypoint track the current image.

The code-interpreter image moved its entrypoint from
``/opt/opensandbox/code-interpreter.sh`` (v1.0.2) to
``/opt/code-interpreter/code-interpreter.sh`` (v1.1.0+). A fresh install
pulling today's image with the old hardcoded entrypoint fails at container
start with exit 127. These offline guards pin the defaults to the current
image so that regression is caught without needing a live backend.
"""

from __future__ import annotations

from rath.backend.opensandbox import OpenSandboxBackend


def test_default_image_is_current() -> None:
    # Must target a pullable, current tag (not the retired v1.0.2).
    assert OpenSandboxBackend._DEFAULT_IMAGE == "opensandbox/code-interpreter:v1.1.0"


def test_default_entrypoint_matches_current_image_layout() -> None:
    # v1.1.0 relocated the launcher under /opt/code-interpreter/.
    assert OpenSandboxBackend._DEFAULT_ENTRYPOINT == (
        "/opt/code-interpreter/code-interpreter.sh",
    )
