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

- **Docker** on the server (Themis needs it anyway). The sign in runs Codex inside a throwaway container of the agent
  image, so there is **nothing else to install**: no Node, no Codex on the server itself.
- A real `THEMIS_SECRET_KEY`. Themis refuses to store a login while the development default is in use.

## How the login is kept safe

- It is **encrypted at rest** with a key derived from `THEMIS_SECRET_KEY`, and never shown or returned by the API.
- The sign in happens in a throwaway container, from which Themis copies the login file out; the container (and the
  temporary copy) are removed right after. A login can not end up in a commit. (For development, `THEMIS_CODEX_LOGIN=host`
  signs in with a Codex CLI installed on the server instead, found through `THEMIS_CODEX_BIN`.)
- When a task needs it, the login is streamed into the cell's memory (a tmpfs under `/run/themis-secrets`), never an
  environment variable, command line argument, host file or log line. It disappears with the cell.
- Runs for one user share the login side by side (up to the limit in **Settings, Codex agents**), except for the moment
  it may be refreshed: see [Runs at the same time](#runs-at-the-same-time).

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

The installer gets the image for you (and `themis upgrade` gets the one that matches each new version). In a development checkout, build it once with `./themis build-images`. Each run gets its own private working folder at `/workspace`,
so two agents never edit the same files. If the owner has not connected Codex, the attempt fails and says so.

## What the agent's computer has

The Codex image has git, ripgrep, the GitHub CLI, Node with `npm` and `npx`, `uv` and `uvx`, and Chromium (for checking a
page or taking a screenshot). A cell runs without root, so there is no `apt` and no installing system packages; `npm`,
`npx` and `uv` still work inside `/workspace`. A short skill, `themis-cell`, tells every agent this and how to launch the
browser, so the agent does not try to install one. Themis adds it to every cell itself (it is not one of an agent's own
skills and agents cannot change it), and an administrator can read it, edit it or switch it off under **Settings, Cell
package**, without rebuilding the image. If you use your own image, edit it to match what your image has. The browser makes
the default image about 700 MB larger on disk.

### Runs at the same time

Parallel workflow branches and several ready tasks can use the same Codex login at once, up to **Runs at the same time**
in **Settings, Codex agents** (3 by default; 1 makes runs take turns). Extra runs wait and say so in their log.

Each cell gets its own copy of the login, and Codex **rotates its refresh tokens**: the first copy to refresh makes every
other copy of the old login unusable. Codex only refreshes a login that is about 8 days old, or one that is rejected, so
Themis keeps the refreshing apart rather than the running:

- While the login is fresh enough that a run cannot make Codex refresh it, runs share it.
- A run that might (the login is close to 8 days old, or its access token would end before the run's time limit) waits
  for the others to finish and has the login alone. The runs after it share the refreshed login again.
- A refreshed login is only stored when it is newer than the stored one, so a long run that began earlier can not put an
  old login back.
- If a run is refused because another run already refreshed the login, it starts again once with the newer login. If
  nothing newer exists the login is dead and the run fails with "connect Codex again".

> [!NOTE]
> All parallel runs draw on the same ChatGPT plan, so its usage limit is reached faster. Themis only ever shares a login
> between the runs of the person who connected it.
