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
| `/workspace/NAME` | A **shared folder** mounted inside it, read and write or read only. `/workspace/shared` is in every cell; see [Shared folders](#shared-folders). |
| `/workspace/.agents/skills` | Agent tasks only: the agent's [skills](/docs/agents#skills), read only. |
| `/cell/prompt.md` | Agent tasks only: the instructions handed to the agent. |
| `/run/themis-secrets` | Agent tasks only: credentials for this attempt (the Codex login, keys given to the agent, the tool configuration), in memory and gone with the cell. The agent is told never to read it. |
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
result. Shared folders are the exception: they live outside the working folder and outlive every run.

## Shared folders

A working folder is thrown away, so runs cannot hand files to each other through it. A **shared folder** (a volume) is
mounted inside the working folder at `/workspace/NAME` and keeps its files between runs. Every project has one called
**shared**, in every cell, with nothing to set up. More are added on the project's **overview**, under **Shared folders**.

| Kind | What it is |
| --- | --- |
| **Managed** | A folder ThemisForge makes for you, at `data/projects/<project id>/volumes/<name>`. You can open it on the server like any other folder. |
| **A folder on this machine** | An existing folder, such as a notes folder or a checkout. It must be inside a folder an administrator approved under **Settings, Mount roots**. |

Each folder has an **access** setting (read and write, or read only) and an agent can ask for less than that. A read-only
folder cannot be changed from inside the cell, whatever the agent tries.

**Writers take turns** is an option for folders where two runs writing at the same time would hurt. Only one run at a time
may hold the folder for writing; a task that needs it waits for its turn without taking up room in the resource budget,
and other tasks go ahead. It is off for `shared` and on by default for host folders that cells may write to. Runs that
only read are never held up.

Removing a folder from a project does not delete any files. A host folder is checked again every time a cell starts:
if it is gone, or no longer approved, the run fails with a note that says why.

> [!WARNING]
> A folder with read and write access can have its files changed or deleted by an unattended agent, with no undo. For a
> real folder on your machine, prefer read only unless the agent has to write there.

## Resource limits

Every cell gets the defaults from **Settings, Cells**:

| Setting | Default | Range |
| --- | --- | --- |
| Image | `alpine:3` | any image that has `sh` |
| CPUs per cell | 1 | up to 64 |
| Memory per cell | 1024 MB | 64 MB and up |
| Time limit | 3600 seconds | 10 to 86400 |

A **project** can change any of these for its own cells (the **Cell** section when you create or edit it, which stays on **Automatic** until you press **Customise**), and an
[agent](/docs/agents) can change them again for itself. Only what is filled in overrides anything, so a default you
change later still reaches everything that did not set its own.

When the time limit is reached the cell is stopped and the attempt is recorded as failed with a note in the log.

### How many cells run at once

All running cells together may use the **resource budget** from **Settings, Resources**: a number of CPUs and an amount of
memory (default 2 CPUs and 2048 MB, which fits two cells of the default size). A cell starts when its CPUs and memory fit
in what is left. A task whose cell is bigger than the whole budget cannot ever start, so it fails right away with a note
that says so, instead of waiting forever.

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
> Stored keys reach a cell only when an administrator gives them to an agent, and then as in-memory files and environment
> variables, never on the command line. See [Agents](/docs/agents#keys).

## Using your own image

Set **Image** to anything Docker can pull. Docker downloads it on first use, and the progress appears in the first
attempt's log. The image needs `sh`, because the placeholder program is a shell script. If the image cannot be pulled
the attempt fails and the log shows Docker's error message.
