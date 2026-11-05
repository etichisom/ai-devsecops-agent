# syntax=docker/dockerfile:1
# Multi-stage build: wheels are built in a throwaway stage, the runtime image has no build tools
# and runs as a non-root user.

FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[scanners]"

FROM python:3.12-slim
LABEL org.opencontainers.image.title="devsecops-agent" \
      org.opencontainers.image.description="Claude-powered security scanning and triage CLI" \
      org.opencontainers.image.source="https://github.com/etichisom/ai-devsecops-agent"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-index --find-links=/wheels "devsecops-agent[scanners]" \
    && useradd --create-home --uid 10001 agent

USER agent
WORKDIR /workspace
ENTRYPOINT ["devsecops-agent"]
CMD ["scan", ".", "--out", "reports"]
