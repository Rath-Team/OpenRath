# syntax=docker/dockerfile:1.7
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /build
COPY pyproject.toml uv.lock README.md README_zh.md LICENSE ./
COPY src ./src
RUN pip install uv==0.7.18 \
    && uv sync --frozen --no-dev --no-editable \
       --extra server --extra postgres --extra s3 --extra redis --extra otel

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENRATH_HOST=0.0.0.0 \
    OPENRATH_PORT=8000
RUN groupadd --system --gid 10001 openrath \
    && useradd --system --uid 10001 --gid openrath --home /app openrath
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY examples ./examples
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["openrath-server"]
