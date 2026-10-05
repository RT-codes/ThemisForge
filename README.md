# ThemisForge

- `backend/` - FastAPI (async) API, accounts and auth. Managed with [uv](https://docs.astral.sh/uv/).
- `frontend/` - Svelte 5 + TypeScript + Tailwind, shadcn-svelte and Svelte Flow. Built with Vite.

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
