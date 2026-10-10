---
title: Architecture
group: Reference
summary: How the pieces fit together, the data model and the security model.
---

# Architecture

Themis is deliberately small: **one server process** that does everything, plus Docker for the cells.

<div class="docs-stack">
<div class="box"><b>Browser</b><span>Svelte web app: dashboard, board, settings, docs</span></div>
<div class="link">HTTPS and the /api routes</div>
<div class="box primary"><b>Themis server (FastAPI, Python)</b><span>REST API &middot; scheduler loop &middot; cell manager &middot; migrations</span></div>
<div class="split">
<div class="box"><b>SQLite</b><span>projects, tasks, attempts, accounts, keys</span></div>
<div class="box"><b>Docker engine</b><span>local socket or a remote host</span></div>
</div>
<div class="link">one container per attempt</div>
<div class="box"><b>Cells</b><span>/workspace and /cell mounted, removed afterwards</span></div>
</div>

## What runs where

| Part | Role |
| --- | --- |
| **API** | REST endpoints under `/api` for projects, tasks, attempts, settings, access and system status. |
| **Scheduler** | A loop inside the server. Every few seconds it picks Ready tasks that are due and starts cells, within the resource budget. |
| **Cell manager** | The only code that talks to Docker. A small interface (run, kill, clean up) so Docker can be replaced later. |
| **Database** | SQLite in WAL mode, with Alembic migrations that run when the server starts. |
| **Web app** | Svelte 5 with Tailwind and shadcn-svelte. The server serves the built app, so there is just one process to run. |

## One task, start to finish

1. A task becomes **Ready** and is due.
2. The scheduler creates an **attempt**, marks the task **Running** and builds the cell's settings.
3. The cell manager writes `/cell/input.json` and runs `docker run` with the work folder and cell folder mounted.
4. Output streams into the attempt's log, saved about once a second.
5. The cell exits. The result file and exit code are read, the container is removed.
6. The attempt is closed (succeeded, failed or cancelled) and the task moves on: recurring tasks back to Ready with the
   next occurrence, one-off tasks to Done, Review, Failed or Blocked.

## Data model

| Table | Holds |
| --- | --- |
| `users` | Accounts, with an administrator flag. |
| `projects` | Name, description and the custom property definitions. Owned by one user. |
| `workspaces` and `boards` | A project holds workspaces, a workspace holds boards. Organisation only: tasks, the scheduler and cells stay project wide. Not the `/workspace` folder inside a cell. |
| `tasks` | Title, description, board, status, position, property values, schedule and next run time, and the task it was spawned from. |
| `attempts` | One row per execution: status, times, exit code, log and result. |
| `secrets` | Named credentials, encrypted. |
| `connections` and `project_connections` | A user's sign ins to outside services (encrypted), and the one a project uses per service. An agent's opt-in is a list of services on the agent. |
| `app_settings` | The operator settings edited on the Settings page. |
| `access_requests` and `invites` | The invite only access flow. Only a hash of each invite token is stored. |

## Restart safety

On every start the server reconciles reality with the database: attempts that were running are closed as failed,
containers left behind by a crash are removed, recurring tasks wait for their next occurrence and interrupted one-off
tasks are marked Failed so a human decides whether to retry.

## Security model

- **Invite only accounts**, with a single administrator who manages access, Docker and keys.
- **Sessions** are signed cookies (`HttpOnly`, `SameSite=Lax`, optionally `Secure`). Passwords use Argon2.
- **Keys** are encrypted at rest with a key derived from `THEMIS_SECRET_KEY` and never shown again after saving.
  **Connections** are kept the same way, belong to one user, and reach a cell only through the agents that opted in.
- **Isolation**: tasks run in containers with limited CPU and memory and only the work folder mounted. Cell names and
  mount paths come from numeric ids, never from user input.
- **Docker access** is the sensitive part: the server's user can control Docker. Run it on a machine you trust, keep it
  behind HTTPS, and keep the administrator account safe.

## API reference

The backend publishes an interactive API reference. When you are signed in, open
<a href="/api/docs" target="_blank" rel="noopener">/api/docs</a> in the browser. The raw OpenAPI description is at
<a href="/api/openapi.json" target="_blank" rel="noopener">/api/openapi.json</a>. Authentication is the same session
cookie the web app uses.
