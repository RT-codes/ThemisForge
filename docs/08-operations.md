---
title: Install and operations
group: Running it
summary: Installing on a VM, the service, configuration, backups, updates and exposing it safely.
---

# Install and operations

## Installing on a server

On a Linux machine you control, as a normal user (not root) with `sudo` rights, with an internet connection:

```bash
curl -fsSL https://github.com/RT-codes/ThemisForge/releases/latest/download/install.sh | sh
```

You do not need to clone anything, and nothing else has to be installed first (not Python, not Node). The script only
makes sure [uv](https://docs.astral.sh/uv/) is there, downloads the installer, and runs it. The installer is safe to run
again at any time. It:

1. downloads the newest **stable release**, checks it against its published checksum, and unpacks it,
2. checks **Docker** (see below) and, with your yes, installs it or adds your user to the `docker` group,
3. gets the agent image (a download of about 1 GB, or a build if the download is not possible),
4. writes the settings with a freshly generated **secret key** (and never replaces an existing one),
5. registers a **systemd service** that starts on boot and restarts if it crashes, and waits until it answers,
6. runs `themis doctor`.

Everything lives in one **home folder**, `~/.local/share/themis` (set another with `--home`):

| In the home folder | What it is |
| --- | --- |
| `releases/<version>/` | The code of each release, with its own Python environment. |
| `current` | A link to the release that runs. An upgrade swaps it, and a rollback swaps it back. |
| `db/`, `data/`, `logs/` | The database, the projects' files, the logs. An upgrade never touches these. |
| `backups/` | Database and settings copies taken before each upgrade. |
| `config.env` | Settings, including the secret key. Private to your user. |

### Options

Pass options after `--`: `curl ... | sh -s -- --port 8080`.

| Option | Effect |
| --- | --- |
| `--host ADDRESS` | Address to listen on. Default `127.0.0.1` (this machine only). Use `0.0.0.0` for your network. |
| `--port N` | Port to listen on. Default `8000`. |
| `--https` | You serve Themis over HTTPS: enables secure session cookies. |
| `--no-service` | Do not register a service; start it yourself with `themis run`. |
| `--channel beta` | Install the newest pre-release too, instead of the newest stable one. |
| `--version X.Y.Z` | Install that version. |
| `--yes` | Answer yes to every question (for scripts). |
| `--skip-image` | Do not pull or build the agent image (offline, or you provide your own). |
| `--home DIR` | Install somewhere else. |

## Installing on Windows

On Windows 10 or 11, open **PowerShell** (Start menu, type "PowerShell"; **not** "as administrator") and run:

```powershell
irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex
```

`irm` is a PowerShell command, so it does not work in Command Prompt (cmd). From Command Prompt use
`powershell -NoProfile -Command "irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex"`.
You do not need to change PowerShell's script policy: the installer does not run script files.

With options, which go to `themis install` (`-Port 8080`, `-Yes`, `-NoService`, `-Channel beta`, `-ThemisHome D:\Themis`):

```powershell
& ([scriptblock]::Create((irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1))) -Port 8080
```

It works like the Linux installer (everything above), with these differences:

- **Hardware virtualization** must be on in the computer's BIOS (UEFI), because Docker Desktop runs Linux containers inside a
  small virtual machine. Most PCs have it on; some desktops ship with it off. The installer checks first and, if it is off,
  stops before installing anything and says how to switch it on (see Troubleshooting).
- **Docker Desktop** with **Linux containers** (its default) is required. If it is missing, the installer offers to install it
  with `winget`; Windows asks for permission, and Docker Desktop may need a restart and a first start of its own, so the
  installer then stops and you run it again. If Docker Desktop is installed but not running, the installer starts it and waits.
- It installs **for your own account, without administrator rights**, into `%LOCALAPPDATA%\Themis` (set another with
  `-ThemisHome`). There is no `sudo` and no docker group.
- Instead of a system service it creates a **scheduled task** named `Themis` that starts Themis when **you log in** (in your
  own session, where Docker Desktop also runs) and starts it again a minute after a crash. It runs **without a window**:
  there is nothing to keep open (and nothing to close by accident). Stop it with `themis stop`, start it with `themis start`. If Docker Desktop is not ready yet
  when Themis starts, Themis shows "runs are paused" and carries on by itself once it is.
- The `themis` command is added to your `PATH`: open a new PowerShell window to use it. `themis logs` follows
  `logs\themis.log` in the home folder, and `logs\service.log` has the console output of the last start.
- **Folders on a drive** can be shared with agents (`C:\Users\you\notes`) under Settings, Mount roots. A whole drive, a
  network share (`\\server\share`) and any other colon are refused. Docker Desktop must be allowed to share the drive
  (its default for your user folder).

Everything else on this page (upgrading with a backup and a rollback, backups, the doctor) works the same.

## Day to day

The installer puts a `themis` command in `~/.local/bin` (add that folder to your `PATH` if the installer says so).

| Command | Does |
| --- | --- |
| `themis status` | What is installed, whether the service runs, and whether it answers. |
| `themis open` | Opens Themis in your browser. |
| `themis logs` | Follows the server log. |
| `themis restart` | Restarts the service (also `start` and `stop`). |
| `themis run` | Runs the server in the foreground (what the service runs). |
| `themis upgrade` | Upgrades to the newest version; see below. |
| `themis doctor` | Checks Python, the secret key, the data folder, the database, Docker and the cell image, then lists how the last few starts went. |
| `themis doctor --report` | The same, and writes `themis-report-<time>.txt` to attach to a bug report. |
| `themis backup` | Saves a copy of the database and settings in `backups/`. |
| `themis uninstall` | Removes the service and the code. Your data stays unless you add `--purge`. |

`themis doctor` prints a tick, a warning or a cross for each check, with a hint for how to fix it, and exits with an
error when something needs attention. It is the first thing to run when something seems off.

## Docker, and what happens when it is not working

Cells are Docker containers, so Themis needs **Docker Engine 24 or newer** (Docker Desktop on Windows) running **Linux
containers**. The same checks run at every start and again in the background (every few minutes, and every few seconds
while something is wrong), so nobody has to keep a machine the way it was at install time.

A problem never stops Themis from starting. While Docker cannot run cells:

- every page shows a banner, and administrators are told what is wrong and where to fix it (Settings, Docker),
- **tasks wait instead of failing**: they stay Ready and start by themselves as soon as Docker works again,
- everything else (browsing, editing, files) keeps working.

## When something goes wrong

Two files in the `logs/` folder next to the install (`THEMIS_LOG_DIR` moves it) keep a trail:

- `logs/runs.jsonl`: one line per event for each of the last 20 starts: how it started, what the checks found, and how it
  ended. A start with no "stopped" line ended without a clean shutdown (a crash, a kill or a power cut). `./themis doctor`
  shows the last few in plain words, including the error of one that failed to start.
- `logs/themis.log`: the application log, rotated (3 files of 2 MB).

Nothing secret is written to either. `./themis doctor --report` bundles the checks, the last runs and the end of the log
into one file for a bug report.

## Versions

Themis uses [semantic versions](https://semver.org): `MAJOR.MINOR.PATCH`, with a dash for a pre-release (`0.2.0-beta.1`).
The version is shown by `GET /api/version` (no sign-in needed), which also says whether this is a **release** or a **git
checkout** (a checkout reports `0.1.0+dev.<commit>`), and by the health check.

For maintainers: `scripts/bump_version.py 0.2.0` sets the version in every file that repeats it, then `uv lock` in
`backend/`, commit, and push the tag `v0.2.0`. The release workflow checks that the tag matches the `VERSION` file, runs
the tests, publishes the release bundle with its checksum, and publishes the cell image for Docker (amd64 and arm64).
`scripts/build_release.py` builds the same bundle on your own machine.

## Configuration

Operator settings live in `config.env` in the home folder (`backend/.env` in a development checkout). The file is private to your user, and the installer creates it.

| Variable | Default | Meaning |
| --- | --- | --- |
| `THEMIS_SECRET_KEY` | generated | Signs sessions and encrypts stored keys. Keep it secret and stable. |
| `THEMIS_COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS. |
| `THEMIS_HOME` | none | The install's home folder. When set, the database, data, logs and `config.env` live in it. The installer sets it. |
| `THEMIS_HOST`, `THEMIS_PORT` | `127.0.0.1`, `8000` | What `themis run` listens on. |
| `THEMIS_DATABASE_URL` | `<home>/db/themisforge.db` | SQLite database location. |
| `THEMIS_DATA_DIR` | `<home>/data/` | Project workspaces and cell files. |
| `THEMIS_ACCESS_TOKEN_MINUTES` | `10080` | Session lifetime (7 days). |
| `THEMIS_SCHEDULER_ENABLED` | `true` | Turn the scheduler off, for example for a read-only copy. |
| `THEMIS_SCHEDULER_INTERVAL_SECONDS` | `3` | How often the scheduler looks for due tasks. |
| `THEMIS_LOG_DIR` | `<home>/logs/` | Where the run trail and the application log are written. |
| `THEMIS_CELL_BACKEND` | `docker` | `fake` simulates cells without Docker (development). |

Changes take effect after `themis restart`. Everything else (Docker host, cell defaults, time zone, keys) is
changed in the **Settings** page and needs no restart.

## What to back up

Three things hold all state, all in the home folder:

- `db/themisforge.db` (and its `-wal` file while the server runs): projects, tasks, history, accounts, keys,
- `data/`: project workspaces and per-attempt files,
- `config.env`: **without the secret key, stored keys cannot be decrypted.**

`themis backup` saves a consistent copy of the database and `config.env` in `backups/` while the server runs. It does not
copy `data/`, which can be large: back that folder up the way you back up any folder. `themis upgrade` makes the same
backup before it changes anything, and Themis also saves a copy of the database in `db/backups/` before every migration
(the latest five are kept), so a migration can never be the only copy of your data.

To go back to a backup: `themis stop`, `themis restore ~/.local/share/themis/backups/<folder>`, `themis start`.

## Upgrading

```bash
themis upgrade --check     # only say whether a newer version exists
themis upgrade             # do it
```

Administrators are told in the app when a newer release exists (see [Settings](/docs/settings#updates)); `themis upgrade --check` asks from the command line.

`themis upgrade` looks for the newest **stable** release (or `--channel beta`, or `--version X.Y.Z`), and then:

1. downloads it, verifies its checksum and installs it next to the running one (the running Themis is not touched yet),
2. checks that Docker is still fine and gets the new agent image,
3. **backs up** the database and settings,
4. stops the service, switches `current` to the new release, starts it, and waits until the new version answers,
5. if it does not come up, **goes back by itself**: the previous release runs again and the database is restored from the
   backup, so a failed upgrade leaves you where you were. The two newest releases are kept on disk for this; older ones are removed.

Database migrations run when the new version starts. A Themis that finds a database from a **newer** version refuses to
touch it and says so, instead of damaging what it does not understand.

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
