# The cell image for Codex agents: Codex CLI plus the basics a coding agent expects.
# Build it with: ./themis build-images
FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.155.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates ripgrep curl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

# Cells run as the host user's uid with no home directory of their own.
ENV HOME=/tmp
WORKDIR /workspace
