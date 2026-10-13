# The cell image for Codex agents: Codex CLI plus the basics a coding agent expects.
# Build it with: ./themis build-images
# uv (and uvx) come from Astral's own image, copied in below.
ARG UV_VERSION=0.12.15
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.160.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates ripgrep curl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

# The GitHub CLI, so an agent with a GitHub connection can work with issues and pull requests (git is above). It
# signs in with the GH_TOKEN the connection provides.
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# uv, so a tool server published on PyPI can be started with `uvx` (tools added from the MCP registry, see
# backend/app/mcp_registry.py). uv downloads the Python it needs when the tool first starts, so the image has none.
COPY --from=uv /uv /uvx /usr/local/bin/

# Cells run as the host user's uid with no home directory of their own.
ENV HOME=/tmp
WORKDIR /workspace
