#!/usr/bin/env bash
# CI-only: create and close one sandbox so pytest never hits cold-start create.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export OPENSANDBOX_INSECURE_SERVER="${OPENSANDBOX_INSECURE_SERVER:-YES}"

echo "Warming up OpenSandbox (create + close one sandbox)..."
uv run python -c "
from rath.backend import get

backend = get('opensandbox')
sandbox = backend.open()
try:
    print(f'warm-up ok: {sandbox.handle}')
finally:
    backend.close(sandbox)
"
