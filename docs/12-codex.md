---
title: Connecting Codex
group: Using Themis
summary: Sign in with ChatGPT once so tasks use your plan's Codex usage, and how the login is kept safe.
---

# Connecting Codex

Codex can run on your **ChatGPT plan** instead of an API key. Plan usage and API usage are billed separately, so
connecting Codex this way means task runs draw from your plan's Codex allowance, not API credit.

## Connect

1. Open **Settings** in the sidebar. The Codex section is at the top for everyone, and administrators see the rest below.
2. Press **Connect Codex**. Themis shows a link and a one-time code.
3. Open the link on any device, sign in with ChatGPT and enter the code.

You do this **once**. The login is stored, refreshed automatically and survives restarts, reloads and rebuilds. You only
connect again if you disconnect, if the code was not used within 15 minutes, or if the administrator changes the
secret key.

Every user connects their own Codex. Nobody else, administrators included, can see or use your connection.

## Requirements

- The **Codex CLI** installed on the server. If it is not on `PATH`, set `THEMIS_CODEX_BIN` to its location
  (on Windows, for example `codex.cmd`).
- A real `THEMIS_SECRET_KEY`. Themis refuses to store a login while the development default is in use.

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

**Disconnect** removes the login from Themis. To also revoke it at OpenAI, sign out of Codex in your ChatGPT
security settings.

## Running a task with Codex

Set a task's **Run with** to **Codex agent**. When it runs, Themis:

1. starts a cell from the **Codex image** (Settings, Cells),
2. hands it the project owner's Codex login (see above) and the task as instructions,
3. runs Codex there with its own sandbox off. The container is the sandbox, which also works for any other agent
   later,
4. shows what the agent said and ran in the attempt **log**, and stores its final message as the **result**,
5. saves the login back if Codex refreshed it during the run.

Build the image once with `./themis build-images`. Each run gets its own private working folder at `/workspace`,
so two agents never edit the same files. If the owner has not connected Codex, the attempt fails and says so.

Runs of the same user take turns: Codex rotates its refresh tokens, so two cells refreshing the same login at once
could lock each other out. A second run waits and says so in its log.
