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

## Proposing a change

- **Bugs and ideas:** open an issue and describe what you saw or want. For a bug, the output of `./themis doctor --report`
  helps a lot (it has no keys or passwords, but look it over before you share it).
- **Small fixes** can go straight to a pull request. For anything bigger (a new feature, a change in how something works),
  please open an issue first so we can agree on the shape before you spend the time.
- **Keep a pull request to one thing**, with a clear title and a few lines on why. Add or update tests for what you changed,
  and update the matching page in `docs/` when something a user sees changes.
- **Match the code around you:** the same naming, comment style and structure. Reuse what exists before adding something
  new, and remove what a change makes obsolete. The checks above must pass; CI runs them on every pull request (see below).
- **Security problems** are not for public issues: see [SECURITY.md](SECURITY.md).

## How a change reaches `main`

There is one long-lived branch, `main`, and it is always in a state that could be released. Nobody pushes to it
directly, maintainers included. Every change takes the same road:

1. **Make a branch** from `main` named for what it does: `feat/...`, `fix/...`, `docs/...` or `ci/...`. If you are not
   a maintainer, fork the repository and do this in your fork.
2. **Open a pull request** into `main`.
3. **The checks must pass** and the branch must be up to date with `main`. Two are required: `Backend (ubuntu-latest)`
   (lint, format and tests) and `Web interface` (type check, tests and build). The release bundle build runs too, and
   checks that Themis installs and starts from nothing.
4. **Merge it.** No approval is required for the maintainers' own pull requests, but anyone is welcome to review. The
   branch is deleted when it is merged.

**Windows** is not supported yet, so its two jobs (the backend tests and the installer) do not run on pull requests: they
take most of the time and cannot block a merge. They run when something lands on `main`, and a maintainer can start
them by hand from the Actions tab (**CI**, **Run workflow**). If your change touches the installer, paths or anything
else that behaves differently on Windows, say so in the pull request.

**Releases are separate from merging.** What people install is a tagged release (`v0.3.0`), never whatever is on `main`:
`themis install` and `themis upgrade` download releases, and a tag is what builds one. So `main` can move on every day
without anyone's Themis changing. A risky release goes out first as a pre-release (`v0.4.0-beta.1`), which nobody gets
unless they ask for that channel. A maintainer makes a release with `scripts/bump_version.py`, writes
`release-notes/<version>.md` by hand and pushes the tag.

A large piece of work that needs many pull requests can use a temporary branch of its own (say `feat/big-thing`): small
pull requests go into it, and it is merged into `main` once, when it is whole. There is no permanent `dev` branch.

## License of your contribution

ThemisForge is under the [Apache License 2.0](LICENSE). By sending a contribution you agree that it is licensed under the
same terms (section 5 of the license), and that you have the right to share it. There is no separate agreement to sign.
