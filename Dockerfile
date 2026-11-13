FROM node:22-bookworm-slim AS claude-cli

ARG CLAUDE_CODE_VERSION=2.1.323
ENV NODE_OPTIONS=--dns-result-order=ipv4first

RUN npm install -g --no-fund --no-audit --fetch-timeout=120000 --fetch-retries=5 \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && claude --version


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    AUTHORING_WORK_DIR=/ctfy/work \
    AUTHORING_MODEL_BACKEND=auto \
    HOME=/home/forge \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

RUN useradd --create-home --uid 10001 forge

WORKDIR /app
COPY --from=claude-cli \
    /usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe \
    /usr/local/bin/claude
COPY pyproject.toml README.md /app/
COPY agent.py /app/agent.py
COPY src /app/src

RUN chmod 0755 /usr/local/bin/claude \
    && claude --version \
    && python -m compileall -q /app/src /app/agent.py \
    && chown -R forge:forge /app

USER forge
WORKDIR /ctfy/work
ENTRYPOINT ["python3", "/app/agent.py", "run"]
