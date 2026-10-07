---
title: Cells and workspaces
group: Using Themis
summary: What a cell is, what it can see, where files and results end up.
---

# Cells and workspaces

A **cell** is the short-lived container a task runs in. Themis creates one for every attempt, streams its output
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

Under the Themis data directory (`data/` next to the code by default, change it with `THEMIS_DATA_DIR`):

```text
data/projects/<project id>/workspaces/<attempt>/ private working folder, mounted at /workspace
data/projects/<project id>/attempts/<attempt>/   input.json, prompt.md and result.md for one attempt
```

Cells run as your Themis user, so files they create are owned by you and easy to inspect or back up.
Deleting a project removes its database records but **keeps** these folders. Working folders of finished attempts
are deleted automatically after **Settings, Cells, Keep working folders for** days; keep what matters in the
result. Shared folders are the exception: they live outside the working folder and outlive every run.

## Shared folders

A working folder is thrown away, so runs cannot hand files to each other through it. A **shared folder** (a volume) is
mounted inside the working folder at `/workspace/NAME` and keeps its files between runs. Every project has one called
**shared**, in every cell, with nothing to set up. More are added on the project's **overview**, under **Shared folders**, or with **New shared folder** on the **Files** page.

| Kind | What it is |
| --- | --- |
| **Managed** | A folder Themis makes for you, at `data/projects/<project id>/volumes/<name>`. You can open it on the server like any other folder. |
| **A folder on this machine** | An existing folder, such as a notes folder or a checkout. It must be inside a folder an administrator approved under **Settings, Mount roots**. |

Each folder has an **access** setting (read and write, or read only) and an agent can ask for less than that. A read-only
folder cannot be changed from inside the cell, whatever the agent tries.

**Writers take turns** is an option for folders where two runs writing at the same time would hurt. Only one run at a time
may hold the folder for writing; a task that needs it waits for its turn without taking up room in the resource budget,
and other tasks go ahead. It is off for `shared` and on by default for host folders that cells may write to. Runs that
only read are never held up.

On Windows a host folder is a folder on a drive, such as `C:\Users\you\notes`; a whole drive, a network share
(`\\server\share`) and a colon anywhere but after the drive letter are refused. Docker Desktop must be allowed to share
the drive.

A folder can be **renamed** from the gear on its tab on the Files page, except `shared`, which keeps its name because every
cell expects it. Agents, workflows and runs keep pointing at the folder, and a managed folder is moved on disk with it. The
new name applies to the next run: a folder cannot be renamed while a run is using it, and instructions, skills or scripts
that mention `/workspace/old-name` have to be changed by hand.

Removing a folder from a project does not delete any files. A host folder is checked again every time a cell starts:
if it is gone, or no longer approved, the run fails with a note that says why.

### Browsing and managing the files

The project's **Files** page (under Tasks in the sidebar) shows what is inside each shared folder: `shared` first, then
the others. This is where agents leave what they deliver. You can open folders, preview text and images, download files,
and, when the folder allows writing, upload files, make folders, rename and delete.

- Each shared folder is a tab. The gear on the open tab changes its access and whether writers take turns. The last tab,
  **config**, is not a shared folder: it holds the project's agents, skills and tools as files (see [Agents](/docs/agents#the-config-folder)),
  is checked when you save, and is never mounted into a cell.
- Folders open in place, like a tree. **New items go in** the folder you clicked last, shown above the list.
- **Search**, **order** (name, newest, oldest, largest, smallest) and a **type** filter (text, images, other) narrow the
  files. Folders always stay first so you can still open them; the gallery steps through the files as listed.
- A read-only folder (or a host folder whose approved root only allows reading) can be browsed and downloaded, not changed: the upload, new folder, rename and delete buttons are not shown there.
- **A folder that runs are using is locked.** While any run has it mounted (read only or not), the page shows a lock and
  a spinner on its files and folders and says which tasks are using it. You can still browse, preview and download, but
  upload, new folder, rename, move, delete and save all wait until the runs finish, because a change from outside could
  break what an agent is in the middle of. `shared` is mounted in every cell, so it is locked whenever a task in the
  project runs. Nothing in a cell itself is locked: an agent can always change the files it was given.
- The page follows the folders you have open. While a run is using them, or just after something changed, it checks every
  second or two; when everything is quiet, every few seconds. Files that agents add, change or move show up on their own,
  and an open text file or picture refreshes when it changes (not while you are editing it).
  A file that appears or changes gets a short pulse (a border and a shine) in the tree, and the preview of the open file
  pulses more slowly when its file changes.
- A file's preview is shown as plain text or as an image (png, jpg, gif, webp, avif, bmp, ico and svg). HTML files are never run, only shown as text or downloaded, and an SVG is shown as a picture only, so its scripts never run.
- Pictures can be zoomed, in the side preview and when enlarged: scroll over the picture (or pinch), use the slider on its
  side, drag to move a zoomed picture, and double-click to fit it again.
- Markdown files (`.md`) are shown as rich text, with a **Raw** switch for the text as written. What the file contains
  cannot run anything: raw HTML is shown as text, only web, mail and in-page links are kept, and pictures load only from
  the file's own folder (pictures from the web are left out).
- Text files (up to 1 MB) have an **Edit** button when the folder allows writing. **Save** (or Ctrl+S) writes the file
  back, keeping its permissions. If you try to leave with unsaved changes (another file, another folder, another page, or
  closing the tab), Themis asks whether to keep editing, discard or save first. If the file changed on disk after you
  opened it, Save is refused with a note, and **Save anyway** replaces it with your version.
- Deleting a file or folder is permanent, on a host folder too. The private working folders of attempts are not shown.

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
- Shutting Themis down stops running cells. On the next start, leftover containers (those labelled
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
