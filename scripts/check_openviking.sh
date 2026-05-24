#!/usr/bin/env bash
# Sanity-check optional OpenViking: Python extra imports and server /health endpoint.
# Uses OPEN_VIKING_URL from the environment (default http://127.0.0.1:1933).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

BASE_URL="${OPEN_VIKING_URL:-http://127.0.0.1:1933}"
HEALTH_URL="${BASE_URL%/}/health"

echo "repo root: ${ROOT_DIR}"
echo "OpenViking API base: ${BASE_URL}"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not on PATH (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

echo ""
echo "[1/2] optional dependency: openviking (uv --extra openviking)"
if ! uv run --extra openviking python -c "import openviking; print(getattr(openviking, '__version__', '?'))"; then
  echo "error: cannot import openviking. Try: uv sync --extra openviking" >&2
  exit 1
fi
echo "      ok"

if ! command -v curl >/dev/null 2>&1; then
  echo "note: curl not on PATH; skipping /health probe."
  echo ""
  echo "OpenViking SDK import check passed (no server probe)."
  exit 0
fi

echo ""
echo "[2/2] HTTP GET ${HEALTH_URL}"
BODY_FILE="$(mktemp)"
trap 'rm -f "${BODY_FILE}"' EXIT
HTTP_CODE="$(
  curl -sS -o "${BODY_FILE}" -w "%{http_code}" \
    --connect-timeout 5 --max-time 15 \
    "${HEALTH_URL}" || true
)"
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "warning: expected HTTP 200 from /health, got ${HTTP_CODE:-<no response>}" >&2
  if [[ -s "${BODY_FILE}" ]]; then
    echo "body:" >&2
    head -c 500 "${BODY_FILE}" >&2 || true
    echo >&2
  fi
  echo "hint: start the server with scripts/launch_openviking.sh, or set OPEN_VIKING_URL to a reachable URL." >&2
  exit 0
fi
echo "      ok (${HTTP_CODE})"
if [[ -s "${BODY_FILE}" ]]; then
  head -c 200 "${BODY_FILE}"
  echo ""
fi

echo ""
echo "OpenViking check passed."
