# ThemisForge

ThemisForge is a self-hosted harness for agent projects. A **project** has a dashboard with a task board
(Kanban, list and a schedule timeline). **Tasks** can be manual, one-off or recurring (cron), and an always-on
scheduler runs them around the clock. Each task executes in a short-lived **cell** (a Docker container) that is
created for the task and removed afterwards.

- `backend/` - FastAPI (async) API, scheduler, cell manager, accounts and auth. SQLite with Alembic migrations.
  Managed with [uv](https://docs.astral.sh/uv/).
- `frontend/` - Svelte 5 + TypeScript + Tailwind, shadcn-svelte and Svelte Flow. Built with Vite.

Full documentation is in [`docs/`](docs/) and in the app itself at `/docs` (no login needed): getting started, tasks and
scheduling, cells, access, settings, operations, troubleshooting and the architecture.

## Install on a server (Debian/Ubuntu VM)

```bash
git clone <this repo> && cd ThemisForge
./themis install        # Docker, uv, Node, build, backend/.env, systemd service
```

Then open http://127.0.0.1:8000 and create the administrator account (the first account). ThemisForge is invite only after
that: people use "Request access" on the sign in screen, and the administrator approves them on the **Access** page, which
creates a one-time invite link (valid 7 days) to send them. There is no email sending yet, so the link is shared by hand. See
`./themis install --help` for `--host`, `--port` and `--https`. Docker, the cell defaults, the time zone and
provider keys are managed on the **Settings** page; `./themis doctor` checks the machine from the terminal.

How a task runs: the scheduler picks up Ready tasks that are due, starts a cell with the project workspace mounted
at `/workspace` and the task at `/cell/input.json`, streams its output into the task's History, stores
`/cell/result.md` as the result, and removes the cell. Recurring tasks go back to Ready for their next occurrence.
The cell currently runs a placeholder program; agent harnesses plug in here.

## Run (production-style, one server)

```bash
cd frontend && npm install && npm run build
cd ../backend && uv sync && uv run uvicorn app.main:app
```

Open http://localhost:8000 - the API lives under `/api` and also serves the built frontend.

## Develop (hot reload)

```bash
# terminal 1
cd backend && uv sync && uv run uvicorn app.main:app --reload

# terminal 2
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to port 8000).

## Checks

```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm run check
```

Copy `backend/.env.example` to `backend/.env` and set `THEMIS_SECRET_KEY` for anything beyond local dev.
