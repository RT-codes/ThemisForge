# Contributing

ThemisForge has two parts:

- `backend/` is the API, the scheduler that starts agent runs, and accounts. It is Python (FastAPI) with a SQLite
  database and Alembic migrations, managed with [uv](https://docs.astral.sh/uv/).
- `frontend/` is the app you see in the browser: Svelte 5, TypeScript and Tailwind, built with Vite.

The documentation lives in [`docs/`](docs/) and is shown inside the app at `/docs`.

## Run it for development

You need [uv](https://docs.astral.sh/uv/), Node.js and Docker.

```bash
./themis start      # backend on :8000 and the frontend with hot reload on :5173
./themis stop
```

Open **http://localhost:5173** (hot reload) or **http://localhost:8000** (the built app). `./themis build-images`
prepares the Codex agent image. `COMMANDS.txt` lists every command.

Without the helper script:

```bash
# terminal 1
cd backend && uv sync && uv run uvicorn app.main:app --reload

# terminal 2
cd frontend && npm install && npm run dev
```

To run it as one server, build the frontend (`cd frontend && npm install && npm run build`) and start only the backend:
the API lives under `/api` and it also serves the built app.

Copy `backend/.env.example` to `backend/.env` and set `THEMIS_SECRET_KEY` to a long random value for anything beyond
local development. Without it, stored keys and sessions are not properly protected.

## Check your changes

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run check && npm test
```

If you change the frontend, run `npm run build` too: the server on port 8000 serves the built files.
