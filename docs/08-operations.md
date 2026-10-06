---
title: Install and operations
group: Running it
summary: Installing on a VM, the service, configuration, backups, updates and exposing it safely.
---

# Install and operations

## Installing on a server

On a fresh Debian or Ubuntu machine, as a normal user with `sudo`:

```bash
git clone https://github.com/RT-codes/ThemisForge.git
cd ThemisForge
./themis install
```

The installer is safe to run again at any time. It:

1. installs **Docker Engine** (with the official script) if it is missing, and adds your user to the `docker` group,
2. installs **uv** (Python tooling) and **Node.js** (to build the web interface) if they are missing,
3. builds the backend and the frontend,
4. writes `backend/.env` with a freshly generated **secret key** (and never overwrites an existing one),
5. registers a **systemd service** that starts on boot and restarts if it crashes,
6. waits until Themis answers, then runs `./themis doctor`.

### Options

| Option | Effect |
| --- | --- |
| `--host ADDRESS` | Address to listen on. Default `127.0.0.1` (this machine only). Use `0.0.0.0` for your network. |
| `--port N` | Port to listen on. Default `8000`. |
| `--https` | You serve Themis over HTTPS: enables secure session cookies. |
| `--skip-docker` | Do not install Docker (you use an existing one, or a remote Docker host). |
| `--no-service` | Build and configure only; do not create the systemd service. |
| `--dry-run` | Print everything the installer would do without changing anything. |

> [!TIP]
> Not sure what the installer will do on your machine? Run `./themis install --dry-run` first.

## Day to day

| Command | Does |
| --- | --- |
| `./themis service status` | Shows whether the service is running. |
| `./themis service logs` | Follows the server log. |
| `./themis service restart` | Restarts it (also `start` and `stop`). |
| `./themis doctor` | Checks Python, the secret key, the data folder, the database, the build and Docker. |

`./themis doctor` prints a tick, a warning or a cross for each check, and exits with an error when something needs
attention. It is the first thing to run when something seems off.

## Configuration

Operator settings live in `backend/.env`. The file is private to your user, and the installer creates it.

| Variable | Default | Meaning |
| --- | --- | --- |
| `THEMIS_SECRET_KEY` | generated | Signs sessions and encrypts stored keys. Keep it secret and stable. |
| `THEMIS_COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS. |
| `THEMIS_DATABASE_URL` | `backend/themisforge.db` | SQLite database location. |
| `THEMIS_DATA_DIR` | `data/` | Project workspaces and cell files. |
| `THEMIS_ACCESS_TOKEN_MINUTES` | `10080` | Session lifetime (7 days). |
| `THEMIS_SCHEDULER_ENABLED` | `true` | Turn the scheduler off, for example for a read-only copy. |
| `THEMIS_SCHEDULER_INTERVAL_SECONDS` | `3` | How often the scheduler looks for due tasks. |
| `THEMIS_CELL_BACKEND` | `docker` | `fake` simulates cells without Docker (development). |

Changes take effect after `./themis service restart`. Everything else (Docker host, cell defaults, time zone, keys) is
changed in the **Settings** page and needs no restart.

## What to back up

Three things hold all state:

- `backend/themisforge.db` (and its `-wal` file while the server runs): projects, tasks, history, accounts, keys,
- `data/`: project workspaces and per-attempt files,
- `backend/.env`: **without the secret key, stored keys cannot be decrypted.**

Before every upgrade that changes the database, Themis saves a copy in `backend/backups/` (the latest five are
kept), so a migration can never be the only copy of your data.

For a consistent copy of the database while the server runs, use `sqlite3 backend/themisforge.db ".backup backup.db"`,
or stop the service first.

## Updating

```bash
cd ThemisForge
git pull
./themis install
```

This rebuilds and restarts the service. Database migrations run automatically when the server starts, and databases
from before migrations existed are upgraded in place.

## Exposing Themis safely

By default Themis listens on `127.0.0.1`, so only the machine itself can reach it. To use it from elsewhere:

- **Best:** keep it on `127.0.0.1` and put a reverse proxy with HTTPS in front. With Caddy that is three lines:

  ```text
  themis.example.com {
      reverse_proxy 127.0.0.1:8000
  }
  ```

  Install with `--https` (or set `THEMIS_COOKIE_SECURE=true`) so session cookies are marked secure.
- **On a trusted private network only:** install with `--host 0.0.0.0` and restrict access with a firewall.

> [!WARNING]
> Membership of the `docker` group is equivalent to root on that machine. Themis needs it to start cells, so treat
> the server and its administrator account accordingly, and keep access invite only.

## Removing the service

```bash
sudo systemctl disable --now themisforge
sudo rm /etc/systemd/system/themisforge.service
```

Your data (`backend/themisforge.db`, `data/`) is left in place.

## Development setup

```bash
./themis start     # backend on 8000, frontend on 5173, both with hot reload
./themis stop
```

Run the checks with `cd backend && uv run pytest && uv run ruff check .` and `cd frontend && npm run check && npm test`.
