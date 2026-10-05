---
title: Cells and workspaces
group: Using ThemisForge
summary: What a cell is, what it can see, where files and results end up.
---

# Cells and workspaces

A **cell** is the short-lived container a task runs in. ThemisForge creates one for every attempt, streams its output
into the task history, collects its result, and removes it. Nothing persists inside a cell, which is the point:
every attempt starts clean, and a misbehaving task cannot leave a mess behind.

## The cell contract

Whatever runs in a cell (today a placeholder, later an agent harness) gets the same simple contract:

| Path or signal | Meaning |
| --- | --- |
| `/workspace` | This attempt's **private working folder**, read and write. Nothing else sees it, and it is removed after the retention period (default 7 days, see Settings). |
| `/cell/prompt.md` | Agent tasks only: the instructions handed to the agent. |
| `/run/themis-secrets` | Agent tasks only: credentials for this attempt (such as the Codex login), in memory and gone with the cell. |
| `/cell/input.json` | The task, written before the cell starts: title, description and properties. |
| `/cell/result.md` | Optional. Whatever the cell writes here is stored as the attempt's **result**. |
| Exit code `0` | The attempt **succeeded**. Any other exit code means it **failed**. |
| Output (stdout and stderr) | Streamed into the attempt **log** while it runs. |

The cell also receives the environment variables `THEMIS_TASK_ID` and `THEMIS_TASK_TITLE`.

## Where files live on the server

Under the ThemisForge data directory (`data/` next to the code by default, change it with `THEMIS_DATA_DIR`):

```text
data/projects/<project id>/workspaces/<attempt>/ private working folder, mounted at /workspace
data/projects/<project id>/attempts/<attempt>/   input.json, prompt.md and result.md for one attempt
```

Cells run as your ThemisForge user, so files they create are owned by you and easy to inspect or back up.
Deleting a project removes its database records but **keeps** these folders. Working folders of finished attempts
are deleted automatically after **Settings, Cells, Keep working folders for** days; keep what matters in the
result. Shared folders that outlive a run are planned (see the [roadmap](/docs/roadmap)).

## Resource limits

Every cell gets the defaults from **Settings, Cells**:

| Setting | Default | Range |
| --- | --- | --- |
| Image | `alpine:3` | any image that has `sh` |
| CPUs per cell | 1 | up to 64 |
| Memory per cell | 1024 MB | 64 MB and up |
| Time limit | 3600 seconds | 10 to 86400 |
| Cells at the same time | 2 | 1 to 64 |

When the time limit is reached the cell is stopped and the attempt is recorded as failed with a note in the log.

## Logs and results

- The **log** is everything the cell printed. It is saved about once a second while the cell runs, and capped at
  200,000 characters (a notice is added when it is cut).
- The **result** is the content of `/cell/result.md`, capped at 100,000 characters.
- Both are visible in the **History** tab of the task.

## Stopping a cell

- **Cancel run** on the task stops the container immediately and records the attempt as cancelled.
- Shutting ThemisForge down stops running cells. On the next start, leftover containers (those labelled
  `themis.cell`) are removed automatically.

## What runs today

Until agent harnesses arrive, each cell runs a small placeholder program: it prints the task, writes a short
`result.md` and exits with `0`. That makes the whole pipeline testable end to end. The image, limits, mounts and
contract above are the real thing.

> [!NOTE]
> Stored keys are not passed into cells yet. A connected Codex login can be (see [Connecting Codex](/docs/codex)). That arrives together with agents. See the
> [roadmap](/docs/roadmap).

## Using your own image

Set **Image** to anything Docker can pull. Docker downloads it on first use, and the progress appears in the first
attempt's log. The image needs `sh`, because the placeholder program is a shell script. If the image cannot be pulled
the attempt fails and the log shows Docker's error message.
