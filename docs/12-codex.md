---
title: Connecting Codex
group: Using ThemisForge
summary: Sign in with ChatGPT once so tasks use your plan's Codex usage, and how the login is kept safe.
---

# Connecting Codex

Codex can run on your **ChatGPT plan** instead of an API key. Plan usage and API usage are billed separately, so
connecting Codex this way means task runs draw from your plan's Codex allowance, not API credit.

## Connect

1. Open your name in the sidebar, then **Connections**.
2. Press **Connect Codex**. ThemisForge shows a link and a one-time code.
3. Open the link on any device, sign in with ChatGPT and enter the code.

You do this **once**. The login is stored, refreshed automatically and survives restarts, reloads and rebuilds. You only
connect again if you disconnect, if the code was not used within 15 minutes, or if the administrator changes the
secret key.

Every user connects their own Codex. Nobody else, administrators included, can see or use your connection.

## Requirements

- The **Codex CLI** installed on the server. If it is not on `PATH`, set `THEMIS_CODEX_BIN` to its location
  (on Windows, for example `codex.cmd`).
- A real `THEMIS_SECRET_KEY`. ThemisForge refuses to store a login while the development default is in use.

## How the login is kept safe

- It is **encrypted at rest** with a key derived from `THEMIS_SECRET_KEY`, and never shown or returned by the API.
- The sign in happens in a temporary folder in the system temp directory, outside the repository, and that folder is
  deleted right after. A login can not end up in a commit.
- When a task needs it, the login is streamed into the cell's memory (a tmpfs under `/run/themis-secrets`), never an
  environment variable, command line argument, host file or log line. It disappears with the cell.
- Runs for one user take turns using the login, because Codex rotates refresh tokens and two cells refreshing at once
  could invalidate each other.

> [!NOTE]
> Whatever runs inside a cell can read the login while the cell is alive. Only connect Codex if you trust the
> tasks and images you run.

## Disconnect

**Disconnect** removes the login from ThemisForge. To also revoke it at OpenAI, sign out of Codex in your ChatGPT
security settings.
