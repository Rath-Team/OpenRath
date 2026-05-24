"""Internal async runtime for OpenRath.

Everything under ``rath._async`` is private. The public API surface
(``Session``, ``Workflow``, ``run_session_loop``, ``ChatClient`` …) is fully
synchronous; this package backs that facade with a single background asyncio
loop and exposes nothing to users.

Importing names from ``rath._async`` from outside the OpenRath codebase is
a layering violation — the leading underscore on the package name is the
machine-readable signal that a public API contract does not exist here.
"""

from rath._async.runtime import OpenRathRuntime, runtime

__all__ = ["OpenRathRuntime", "runtime"]
