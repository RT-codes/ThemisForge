# ThemisForge

**A self-hosted workspace for agent projects, scheduled tasks, and visual workflows.**

Give an agent a job, run it now or on a schedule, and come back to its logs and results. ThemisForge keeps the work organised into projects and runs each attempt in a fresh Docker container, with the instructions, folders, and resource limits you choose.

It runs on a machine you own and is managed from your browser. The scheduler keeps working when you close the tab.

**[Get started](#get-started)** · **[Run your first agent task](#run-your-first-agent-task)** · **[Documentation](#documentation)** · **[Development](#development)**

> **Screenshot placeholder:** Project overview and task board, showing a running task and its result.

## What you can do

- **Organise work into projects.** Use a Kanban board, a list, or a schedule timeline, with custom task properties and a history of every attempt.
- **Run tasks on your schedule.** Start work manually, at a specific time, or repeatedly using presets or cron expressions.
- **Configure your agents.** Give each worker a name, role, instructions, model, and reasoning effort. Codex is the supported agent harness today.
- **Draw workflows.** Connect tasks, agents, and conditions in a visual editor. Test a workflow, inspect each node's result, or let a scheduled task run it.
- **Share files between runs.** Each attempt has a private working folder. Persistent shared folders let agents keep useful output and pass files to other runs, with read-only or write access and optional turn taking for writers.
- **Control resource use.** Set a total CPU and memory budget, plus container limits and timeouts. Projects, agents, and individual workflow steps can override the defaults.
- **Review what happened.** Follow a running task's output, read its final result, inspect workflow history, and cancel work from the interface.
- **Manage access.** The first account is the administrator; additional users join by invitation. Each user can connect their own Codex account.

For example, a recurring task can ask an agent to review files in a shared folder each morning. A workflow can pass that result to another agent, branch on the outcome, and finish with a result for you to review.

> **Screenshot placeholder:** Workflow editor with connected Agent, Condition, and End nodes, alongside a run's history.

## How it works

| Concept | What it means |
| --- | --- |
| **Project** | A home for related tasks, agents, workflows, and shared folders. |
| **Task** | A job with instructions, a status, and an optional schedule. It can run an agent or a workflow. |
| **Agent** | A configured worker: its role, instructions, model, container settings, and folder access. |
| **Attempt** | One execution of a task, with its own log, result, and outcome. |
| **Cell** | The Docker container created for an attempt and removed afterwards. |

You make a task **Ready**. When it is due and resources are available, the scheduler starts it, records its output, and collects the result. Recurring tasks return to Ready for their next run. Files you want to keep between runs belong in a shared folder.

The application uses one FastAPI server for the API, scheduler, and built web interface, with SQLite for state and Docker for task execution. There is no separate queue service to configure.

## Get started

### Install on a server

The installer targets **Debian and Ubuntu**, using a normal user with `sudo` access.

```bash
git clone https://github.com/RT-codes/ThemisForge.git
cd ThemisForge
./themis install
```

It installs missing Docker, uv, and Node.js dependencies, builds the application, generates a secret key, and sets up a systemd service that starts on boot.

Open **http://127.0.0.1:8000** on that machine and create the administrator account. In **Settings**, check that Docker is connected, then create your first project.

Installing on a remote server? The default address is local to that server. See [Install and operations](docs/08-operations.md#exposing-themisforge-safely) for reverse proxy, HTTPS, and private network setup.

To preview the installation steps or see the available options:

```bash
./themis install --dry-run
./themis install --help
```

### Run your first agent task

To run Codex agents, you also need the **Codex CLI installed on the server** and an account that can use Codex. The application installer does not install the host Codex CLI. If it is not on the service's `PATH`, set `THEMIS_CODEX_BIN` in `backend/.env` to its full path and restart the service.

1. Build the agent container image from the repository root:

   ```bash
   ./themis build-images
   ```

2. In **Settings**, select **Connect Codex** and follow the sign-in link and code.
3. Open a project, go to **Agents**, and create an agent with a name and instructions. Save it.
4. Create a task, describe the work, and select that agent under **Run with**.
5. Press **Run now**, then open the task's **History** to follow its log and read the result.

To repeat the work, choose a recurring schedule and put the task in **Ready**. A recurring task in **Inbox** is paused.

You can also run a task with the built-in placeholder to try the scheduling and container pipeline before connecting an agent.

### Day-to-day commands

```bash
./themis service status     # Check the server
./themis service logs       # Follow its logs
./themis service restart    # Restart after configuration changes
./themis doctor             # Diagnose setup problems
```

For updates and backups, see [Install and operations](docs/08-operations.md).

## Documentation

**The full guide is built into the application at `/docs`, with no sign-in required.** It includes search, navigation, setup instructions, and explanations of the settings. On a default installation, open **http://localhost:8000/docs**.

The same source files are available here in the repository:

| Guide | Covers |
| --- | --- |
| [Getting started](docs/02-getting-started.md) | Installation, accounts, and your first task. |
| [Projects and tasks](docs/03-tasks.md) · [Scheduling](docs/04-scheduling.md) | Boards, task states, custom properties, and recurring work. |
| [Agents](docs/14-agents.md) · [Connecting Codex](docs/12-codex.md) | Worker configuration and account connections. |
| [Workflows](docs/13-workflows.md) | The visual editor, nodes, and run history. |
| [Cells and workspaces](docs/05-cells.md) · [Settings](docs/07-settings.md) | Containers, shared folders, and resource budgets. |
| [Access and accounts](docs/06-access.md) | Access requests and invitations. |
| [Install and operations](docs/08-operations.md) · [Troubleshooting](docs/09-troubleshooting.md) | Deployment, configuration, backups, and diagnostics. |
| [Architecture](docs/10-architecture.md) · [Roadmap](docs/11-roadmap.md) | Internals and planned work. |

Some links within those guides use the application's `/docs/...` addresses, and their diagrams use the app's styling. The in-app version provides the complete reading experience.

## Current status

ThemisForge is under active development. Codex agent execution, recurring tasks, visual workflows, shared folders, and resource budgets are implemented today.

Planned work includes agent skills and MCP tools, additional credential delivery into cells, webhooks, notifications, and live updates. Workflow **Trigger** nodes currently behave like Start nodes; automatic event triggers are not implemented yet. You can schedule a task that runs a workflow.

See the [roadmap](docs/11-roadmap.md) for more detail.

## Running your own instance

The server controls Docker, and agents run unattended with the folder access you grant them. Use trusted images and tasks, and choose read-only access for host folders whenever writing is unnecessary.

The installer generates `THEMIS_SECRET_KEY`. Keep it private and stable: it signs sessions and encrypts stored credentials. For access over the internet, use HTTPS and secure session cookies as described in the [operations guide](docs/08-operations.md#exposing-themisforge-safely).

Back up the database, the data directory, and `backend/.env` together. The secret key is needed to decrypt stored credentials.

## Development

The project uses **Python 3.13+ with uv**, **Svelte 5 and TypeScript with Vite**, **Tailwind and shadcn-svelte**, and **Svelte Flow** for the workflow editor. SQLite schema changes are managed with Alembic.

With uv, a current Node.js LTS release, and Docker installed:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set THEMIS_SECRET_KEY to a long, random secret.
./themis start
```

Open **http://localhost:5173** for hot reload. The backend runs on port **8000**, and Vite proxies `/api` requests to it. Use `./themis stop` to stop both processes and `./themis logs` to follow their output.

For development without Docker execution, set `THEMIS_CELL_BACKEND=fake` in `backend/.env`. This simulates cells; it does not run real agents.

### Project layout

```text
backend/       FastAPI API, scheduler, cell manager, database, and tests
frontend/      Svelte web interface and frontend tests
docs/          Markdown sources for the in-app documentation
docker/        Codex agent container image
themis         Development and server management CLI
install.sh     Debian/Ubuntu installer
```

### Checks

Backend:

```bash
cd backend
uv run pytest
uv run ruff check .
```

Frontend:

```bash
cd frontend
npm run check
npm test
npm run build
```

Found a bug or have an idea? [Open an issue](https://github.com/RT-codes/ThemisForge/issues) with what you were trying to do, what happened, and any relevant logs. Remove credentials and private information before sharing logs.
