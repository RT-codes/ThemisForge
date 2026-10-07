#!/usr/bin/env python3
"""themis: install, upgrade and look after a Themis on this machine.

    themis install [--channel stable|beta] [--version X.Y.Z] [--host A] [--port N] [--https] [--no-service] [--yes]
    themis upgrade [--check] [--channel stable|beta] [--version X.Y.Z] [--yes]
    themis start | stop | restart | status | logs
    themis run                 the server in the foreground (what the service runs)
    themis doctor [--report]   what is wrong, and how the last starts went
    themis backup | restore DIR
    themis version | uninstall [--purge]

One file with only the standard library, so it can run before anything is installed: `install.sh` fetches it and runs it
with uv's Python. Every release ships this same file (scripts/themisctl.py), and the `themis` command on the PATH runs
the copy in the current release.

The layout (the home folder; where it is: see default_home):

    releases/<version>/   the code of each release, each with its own virtualenv
    current               a link to the release that runs: an upgrade swaps it, and a rollback swaps it back
    db/ data/ logs/       the database, the projects' files, the logs: never touched by an upgrade
    backups/              database and settings copies taken before an upgrade
    config.env            settings, with the secret key (private to the user)
    install.json          what is installed and where it came from
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "RT-codes/ThemisForge"
API = os.environ.get("THEMIS_RELEASE_API", f"https://api.github.com/repos/{REPO}").rstrip("/")
IMAGE = "ghcr.io/rt-codes/themis-cell-codex"  # published by the release workflow, one tag per version
LOCAL_IMAGE = "themisforge/cell-codex:latest"  # the name the app uses by default, so no setting has to change
UNIT = "themis.service"
UNIT_PATH = f"/etc/systemd/system/{UNIT}"
KEEP_RELEASES = 2  # the one that runs and the one before it, for a quick rollback
MIN_FREE_MB = 1500

WINDOWS = sys.platform == "win32"


class CtlError(Exception):
    """Something to tell the person, in plain words. The message is printed and the exit code is 1."""


# ----- versions (the same rule as backend/app/version.py; a test checks that they agree) -----

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def sort_key(version: str) -> tuple:
    m = SEMVER.match(version.strip().removeprefix("v"))
    if not m:
        raise ValueError(f"Not a version: {version!r}")
    major, minor, patch, pre = m.groups()
    if pre is None:
        return (int(major), int(minor), int(patch), 1, ())
    return (
        int(major),
        int(minor),
        int(patch),
        0,
        tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")),
    )


def is_prerelease(version: str) -> bool:
    return "-" in version


# ----- where things are -----


def default_home() -> Path:
    if env := os.environ.get("THEMIS_HOME", "").strip():
        return Path(env).expanduser()
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Themis"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "themis"


class Home:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.releases = self.root / "releases"
        self.current = self.root / "current"
        self.backups = self.root / "backups"
        self.logs = self.root / "logs"
        self.tmp = self.root / "tmp"
        self.config_env = self.root / "config.env"
        self.state_file = self.root / "install.json"
        self.db = self.root / "db" / "themisforge.db"

    def release_dir(self, version: str) -> Path:
        return self.releases / version

    def python(self, release: Path | None = None) -> Path:
        venv = (release or self.current) / "backend" / ".venv"
        return venv / ("Scripts/python.exe" if WINDOWS else "bin/python")

    def ctl(self, release: Path | None = None) -> Path:
        return (release or self.current) / "scripts" / "themisctl.py"

    def make_dirs(self) -> None:
        for d in (self.releases, self.backups, self.logs, self.tmp, self.db.parent, self.root / "data"):
            d.mkdir(parents=True, exist_ok=True)

    def env(self) -> dict[str, str]:
        """The environment the app runs in: its home, so it finds config.env, the database and the data."""
        return {**os.environ, "THEMIS_HOME": str(self.root)}

    # -- what is installed --

    def state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def save_state(self, **changes: object) -> None:
        state = {**self.state(), **changes}
        self.state_file.write_text(json.dumps(state, indent=2) + "\n")

    def current_version(self) -> str | None:
        """The release `current` points at, or None when nothing is installed."""
        try:
            return Path(os.path.realpath(self.current)).name if self.current.exists() else None
        except OSError:
            return None

    def installed(self) -> list[str]:
        found = (
            [
                p.name
                for p in self.releases.iterdir()
                if SEMVER.match(p.name) and not p.name.endswith(".partial")
            ]
            if self.releases.is_dir()
            else []
        )
        return sorted(found, key=sort_key)


# ----- talking to the person -----

_log_file: Path | None = None


def _log(line: str) -> None:
    if _log_file is not None:
        with contextlib.suppress(OSError), _log_file.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now(datetime.UTC):%Y-%m-%dT%H:%M:%SZ} {line}\n")


def say(text: str) -> None:
    print(
        f"\n==> {text}", flush=True
    )  # flushed: output piped through `curl | sh` must keep its order with the programs it runs
    _log(f"== {text}")


def info(text: str) -> None:
    print(f"    {text}", flush=True)
    _log(f"   {text}")


def ask(question: str, *, yes: bool = False, default: bool = False) -> bool:
    """A yes/no question. `--yes` answers yes; with nobody to ask (a script) the answer is the default, which for anything
    that changes the machine is no."""
    if yes:
        return True
    prompt = f"    {question} [{'Y/n' if default else 'y/N'}] "
    try:
        if sys.stdin.isatty():
            answer = input(prompt)
        else:  # `curl ... | sh` has used stdin for the script: ask on the terminal itself if there is one
            with open("/dev/tty") as tty:
                print(prompt, end="", flush=True)
                answer = tty.readline()
    except (OSError, EOFError):
        return default
    return default if not answer.strip() else answer.strip().lower().startswith("y")


# ----- running programs -----


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    """Every program goes through here, so it is logged, and a test can stand in for the machine."""
    _log(f"$ {shlex.join(cmd)}")
    done = subprocess.run(
        cmd, check=False, text=True, capture_output=capture, env=env, cwd=cwd, input=input_text
    )
    if check and done.returncode != 0:
        tail = (done.stderr or done.stdout or "").strip().splitlines()[-3:] if capture else []
        raise CtlError(
            f"`{shlex.join(cmd[:3])}...` failed ({done.returncode})"
            + (": " + " / ".join(tail) if tail else "")
        )
    return done


def sudo_prefix() -> list[str]:
    return [] if WINDOWS or os.geteuid() == 0 else ["sudo"]


def find_uv() -> str:
    for candidate in (
        os.environ.get("UV"),
        shutil.which("uv"),
        str(Path.home() / ".local" / "bin" / "uv"),
        str(Path.home() / ".cargo" / "bin" / "uv"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    raise CtlError(
        "uv was not found. Install it from https://docs.astral.sh/uv/ (install.sh does this for you)."
    )


# ----- releases: finding, downloading, verifying, unpacking -----


def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    headers = {"User-Agent": "themisctl", "Accept": accept}
    if token := os.environ.get("THEMIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"  # only needed while the repository is private
    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str) -> object:
    try:
        with urllib.request.urlopen(_request(url), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise CtlError(
            f"{url} answered {e.code}"
            + (" (is the repository private? set THEMIS_GITHUB_TOKEN)" if e.code in (401, 403, 404) else "")
        ) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise CtlError(
            f"Could not reach {url}: {getattr(e, 'reason', e)}. Check the internet connection."
        ) from None


def list_releases() -> list[dict]:
    data = fetch_json(f"{API}/releases?per_page=50")
    if not isinstance(data, list):
        raise CtlError("The releases list was not what was expected.")
    return data


def pick_release(releases: list[dict], *, channel: str = "stable", version: str | None = None) -> dict:
    """The release to install: that exact version, or the newest one of the channel (stable skips pre-releases)."""
    usable = []
    for r in releases:
        tag = str(r.get("tag_name", "")).removeprefix("v")
        if r.get("draft") or not SEMVER.match(tag):
            continue
        usable.append((tag, r))
    if version:
        wanted = version.removeprefix("v")
        for tag, r in usable:
            if tag == wanted:
                return {**r, "version": tag}
        raise CtlError(f"There is no release {wanted}.")
    if channel == "stable":
        usable = [(t, r) for t, r in usable if not is_prerelease(t) and not r.get("prerelease")]
    if not usable:
        raise CtlError(f"There is no {channel} release yet.")
    tag, release = max(usable, key=lambda item: sort_key(item[0]))
    return {**release, "version": tag}


def asset(release: dict, name: str) -> dict:
    for a in release.get("assets", []):
        if a.get("name") == name:
            return a
    raise CtlError(
        f"Release {release['version']} has no {name}: it may not be fully published yet. Try again in a few minutes."
    )


def download(a: dict, dest: Path) -> None:
    """Saves a release file. With a token the API address is used (a private repository), otherwise the public one."""
    token = os.environ.get("THEMIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    url, accept = (
        (a["url"], "application/octet-stream")
        if token and a.get("url")
        else (a["browser_download_url"], "application/octet-stream")
    )
    try:
        with urllib.request.urlopen(_request(url, accept), timeout=60) as response, dest.open("wb") as out:
            shutil.copyfileobj(response, out)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CtlError(f"Could not download {a['name']}: {getattr(e, 'reason', e)}") from None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, sums_text: str, name: str) -> None:
    """The bundle must be exactly what the release published: a damaged or swapped download is never installed."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            if parts[0].lower() != sha256_of(path):
                raise CtlError(
                    f"The download of {name} does not match its checksum, so it was thrown away. Try again."
                )
            return
    raise CtlError(f"SHA256SUMS does not list {name}, so it cannot be checked.")


def safe_extract(bundle: Path, dest: Path) -> None:
    """Unpacks a release bundle (one top folder, themisforge-<version>/) into `dest` without that folder, refusing anything
    that would land outside it."""
    dest.mkdir(parents=True)
    root = dest.resolve()
    with tarfile.open(bundle) as tar:
        members = tar.getmembers()
        tops = {m.name.split("/")[0] for m in members}
        if len(tops) != 1:
            raise CtlError("The bundle is not shaped like a release (it should have one top folder).")
        top = tops.pop()
        for m in members:
            if not (m.isfile() or m.isdir()):
                raise CtlError(
                    f"The bundle holds something that is not a plain file or folder ({m.name}), so it was not unpacked."
                )
            relative = Path(m.name).relative_to(top)
            target = (root / relative).resolve()
            if root != target and root not in target.parents:
                raise CtlError(
                    f"The bundle tries to write outside its folder ({m.name}), so it was not unpacked."
                )
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(m)
                assert source is not None
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                target.chmod(m.mode & 0o777 or 0o644)


def stage_release(
    home: Home, release: dict | None = None, *, bundle: Path | None = None, version: str | None = None
) -> Path:
    """Gets a release onto this machine, ready to run but not running: downloaded, verified, unpacked into
    releases/<version>, with its dependencies installed. Safe to repeat: a release that is already there is reused."""
    home.make_dirs()
    if bundle is None:
        assert release is not None
        version = release["version"]
        name = f"themisforge-{version}.tar.gz"
        target = home.release_dir(version)
        if (target / "backend" / ".venv").is_dir() and (target / "VERSION").is_file():
            info(f"Themis {version} is already on this machine.")
            return target
        bundle = home.tmp / name
        info(f"downloading Themis {version}")
        download(asset(release, name), bundle)
        sums = home.tmp / "SHA256SUMS"
        download(asset(release, "SHA256SUMS"), sums)
        verify_checksum(bundle, sums.read_text(), name)
    else:
        version = version or bundle.name.removeprefix("themisforge-").removesuffix(".tar.gz")
        target = home.release_dir(version)
    free_mb = shutil.disk_usage(home.root).free // 2**20
    if free_mb < MIN_FREE_MB:
        raise CtlError(
            f"Only {free_mb} MB are free here and Themis needs about {MIN_FREE_MB} MB. Free some space and run this again."
        )
    partial = target.with_name(target.name + ".partial")
    for leftover in (partial, target):
        shutil.rmtree(leftover, ignore_errors=True)
    safe_extract(bundle, partial)
    info("installing its dependencies (this takes a minute the first time)")
    clean = {
        k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"
    }  # another environment must not leak into this one
    run(
        [find_uv(), "sync", "--frozen", "--no-dev", "--python", "3.13"],
        cwd=partial / "backend",
        env=clean,
        capture=True,
    )
    partial.rename(target)
    return target


# ----- the link that says which release runs -----


def link_current(home: Home, version: str) -> None:
    """Points `current` at a release in one step, so the service never sees it half changed."""
    if WINDOWS:
        raise CtlError("Windows support is not ready yet.")
    target = home.release_dir(version)
    if not target.is_dir():
        raise CtlError(f"Release {version} is not on this machine.")
    staging = home.root / "current.new"
    with contextlib.suppress(FileNotFoundError):
        staging.unlink()
    staging.symlink_to(target)
    os.replace(staging, home.current)


def prune(home: Home, keep: int = KEEP_RELEASES) -> list[str]:
    """Removes old releases, keeping the running one and the newest others (a rollback needs the one before)."""
    current = home.current_version()
    old = [v for v in home.installed() if v != current]
    gone = old[: max(0, len(old) - (keep - 1))] if keep > 1 else old
    for v in gone:
        shutil.rmtree(home.release_dir(v), ignore_errors=True)
    return gone


# ----- settings (config.env) -----


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def write_config_env(home: Home, *, host: str, port: int, https: bool) -> bool:
    """Writes config.env, keeping what is there: an existing secret key is NEVER replaced (stored keys could no longer be
    decrypted). Returns True when a new secret key was made."""
    values = read_env_file(home.config_env)
    new_key = not values.get("THEMIS_SECRET_KEY") or "change-me" in values["THEMIS_SECRET_KEY"]
    if new_key:
        values["THEMIS_SECRET_KEY"] = secrets.token_hex(32)
    values["THEMIS_HOST"], values["THEMIS_PORT"] = host, str(port)
    if https:
        values["THEMIS_COOKIE_SECURE"] = "true"
    body = "# Written by `themis install`. Keep this file private: the secret key protects sessions and stored keys.\n"
    body += "".join(f"{k}={v}\n" for k, v in values.items())
    home.config_env.write_text(body)
    with contextlib.suppress(OSError):
        home.config_env.chmod(0o600)
    return new_key


# ----- the service (Linux, systemd) -----


def render_unit(home: Home, user: str, groups: list[str]) -> str:
    """The systemd unit. It runs as the person who installed (so files are theirs), with the docker group added to the
    service itself, which works the moment it is installed instead of after the next login."""
    extra = f"SupplementaryGroups={' '.join(groups)}\n" if groups else ""
    return f"""[Unit]
Description=Themis
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
User={user}
{extra}Environment=THEMIS_HOME={home.root}
WorkingDirectory={home.current}/backend
ExecStart={home.current}/backend/.venv/bin/python -m app.run
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run([*sudo_prefix(), "systemctl", *args], check=check)


def service_installed() -> bool:
    return Path(UNIT_PATH).exists()


def service_active() -> bool:
    return run(["systemctl", "is-active", "--quiet", UNIT], check=False).returncode == 0


def install_service(home: Home) -> None:
    user = os.environ.get("USER") or Path.home().name
    groups = (
        ["docker"]
        if shutil.which("getent")
        and run(["getent", "group", "docker"], check=False, capture=True).returncode == 0
        else []
    )
    with tempfile.NamedTemporaryFile("w", suffix=".service", delete=False) as f:
        f.write(render_unit(home, user, groups))
    try:
        run([*sudo_prefix(), "install", "-m", "644", f.name, UNIT_PATH])
    finally:
        os.unlink(f.name)
    systemctl("daemon-reload")
    systemctl("enable", UNIT)


# ----- the app answering -----


def health(port: int, host: str = "127.0.0.1") -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=3) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def configured_port(home: Home) -> int:
    try:
        return int(read_env_file(home.config_env).get("THEMIS_PORT", "8000"))
    except ValueError:
        return 8000


def wait_until_up(port: int, version: str, seconds: int = 45) -> bool:
    """True once the server answers and says it is this version (a leftover old process cannot pass for the new one)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        answer = health(port)
        if answer and str(answer.get("version", "")).split("+")[0] == version:
            return True
        time.sleep(1)
    return False


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ----- Docker -----


def doctor_json(home: Home, release: Path | None = None) -> dict:
    """What the app's own checks say (python -m app.doctor --json in that release), so there is one list of checks."""
    done = run(
        [str(home.python(release)), "-m", "app.doctor", "--json"],
        check=False,
        capture=True,
        env=home.env(),
        cwd=(release or home.current) / "backend",
    )
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise CtlError(
            "The checks could not run: "
            + ((done.stderr or done.stdout).strip().splitlines() or ["no output"])[-1]
        ) from None


def docker_problem(report: dict) -> dict | None:
    return next((c for c in report.get("checks", []) if c["id"] == "docker" and c["level"] == "fail"), None)


def in_docker_group() -> bool:
    return run(["id", "-nG"], check=False, capture=True).stdout.split().count("docker") > 0


def ensure_docker(home: Home, release: Path, *, yes: bool) -> None:
    """Docker is not optional: Themis runs agents in containers. This checks it, and with the person's yes fixes what it can
    (install it, add them to the docker group); anything else is explained, with where to read more, and stops here."""
    report = doctor_json(home, release)
    problem = docker_problem(report)
    docker = report.get("docker") or {}
    if problem is None:
        info(f"Docker {docker.get('version', '')} is ready")
        return
    if not docker.get("installed", True):
        info("Docker is not installed. Themis needs it: agents run inside Docker containers.")
        if not ask(
            "Install Docker Engine now, with Docker's official script (https://get.docker.com)? It uses sudo.",
            yes=yes,
        ):
            raise CtlError(f"Install Docker, then run this again. {problem.get('hint', '')}")
        run(["sh", "-c", "curl -fsSL https://get.docker.com | " + " ".join([*sudo_prefix(), "sh"])])
        run([*sudo_prefix(), "systemctl", "enable", "--now", "docker"], check=False)
        report = doctor_json(home, release)
        problem = docker_problem(report)
    if problem and "permission denied" in (problem.get("message", "") + problem.get("hint", "")).lower():
        info("Docker is installed, but this user cannot use it yet.")
        if not in_docker_group():
            if not ask(
                "Add this user to the docker group? (Members of it can control Docker, which is root-equivalent on this machine.)",
                yes=yes,
            ):
                raise CtlError(
                    "Docker needs to be usable by this user. Add them to the docker group, log out and in, and run this again."
                )
            run([*sudo_prefix(), "usermod", "-aG", "docker", os.environ.get("USER") or Path.home().name])
        info("The service gets the group by itself; this terminal only after you log out and in.")
        return  # the service is given the group, so the check will pass once it runs
    if problem:
        raise CtlError(f"Docker is not usable: {problem['message']}\n    {problem.get('hint', '')}")
    info(f"Docker {(report.get('docker') or {}).get('version', '')} is ready")


def docker_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """`docker ...`, from inside the docker group when this terminal does not have it yet."""
    plain = run(["docker", *args], check=False, capture=True)
    if plain.returncode == 0 or "permission denied" not in (plain.stderr or "").lower():
        if check and plain.returncode != 0:
            raise CtlError(f"docker {args[0]} failed: {(plain.stderr or '').strip().splitlines()[-1:]}")
        return plain
    return run(["sg", "docker", "-c", shlex.join(["docker", *args])], check=check, capture=True)


def get_cell_image(home: Home, release: Path, version: str) -> None:
    """The box agents run in: pulled from the registry (seconds), or built from the release's Dockerfile (minutes) when the
    registry cannot be reached. It is tagged with the name the app uses by default, so no setting has to change."""
    remote = f"{IMAGE}:{version}"
    info(f"getting the agent image {remote}")
    if docker_run(["pull", remote], check=False).returncode == 0:
        docker_run(["tag", remote, LOCAL_IMAGE])
        return
    info("it could not be pulled, so it is built here instead (a few minutes)")
    docker_run(["build", "-t", LOCAL_IMAGE, str(release / "docker" / "cell-codex")])


# ----- backups -----


def backup(home: Home, label: str) -> Path:
    """A consistent copy of the database and of config.env. The projects' files are not copied: they are not touched by an
    upgrade, and can be large (see the operations guide for backing those up)."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    folder = home.backups / f"{label}-{stamp}"
    folder.mkdir(parents=True)
    if home.db.is_file():
        source = sqlite3.connect(home.db)
        target = sqlite3.connect(folder / home.db.name)
        with target:
            source.backup(target)  # consistent even while the app is writing
        source.close()
        target.close()
    if home.config_env.is_file():
        shutil.copy2(home.config_env, folder / "config.env")
    return folder


def restore(home: Home, folder: Path) -> None:
    """Puts a backup back. The caller has stopped the service."""
    saved = folder / home.db.name
    if saved.is_file():
        for suffix in ("-wal", "-shm"):
            with contextlib.suppress(FileNotFoundError):
                Path(str(home.db) + suffix).unlink()
        shutil.copy2(saved, home.db)
    if (folder / "config.env").is_file():
        shutil.copy2(folder / "config.env", home.config_env)


# ----- the commands -----


def need_installed(home: Home) -> str:
    version = home.current_version()
    if version is None:
        raise CtlError(f"Nothing is installed in {home.root}. Run: themis install")
    return version


def restart_service(home: Home) -> None:
    if service_installed():
        systemctl("restart", UNIT)
    else:
        info("There is no service, so start it yourself with: themis run")


def make_shim(home: Home) -> Path:
    """The `themis` command: runs the control file of the current release, whichever that is after an upgrade."""
    if WINDOWS:
        raise CtlError("Windows support is not ready yet.")
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "themis"
    shim.write_text(f"""#!/bin/sh
# Written by `themis install`: runs the control file of the release that is current.
export THEMIS_HOME={shlex.quote(str(home.root))}
exec "{home.current}/backend/.venv/bin/python" "{home.current}/scripts/themisctl.py" "$@"
""")
    shim.chmod(0o755)
    return shim


def check_platform() -> None:
    if WINDOWS:
        raise CtlError(
            "Windows support is on its way and is not ready yet. See the README for where it stands."
        )
    if sys.platform != "linux":
        raise CtlError(
            f"{platform.system()} is not supported yet: Themis runs on Linux today, and Windows is next."
        )
    if platform.machine().lower() not in ("x86_64", "amd64", "aarch64", "arm64"):
        raise CtlError(
            f"The processor type {platform.machine()} is not supported (Intel/AMD or ARM 64-bit are)."
        )
    if os.geteuid() == 0:
        raise CtlError(
            "Run this as your normal user, not root: the service runs as you, and sudo is used only where needed."
        )


def cmd_install(args: argparse.Namespace, home: Home) -> None:
    check_platform()
    home.make_dirs()
    port = args.port
    if port_in_use(port) and not (home.current_version() and health(port)):
        raise CtlError(f"Port {port} is already used by something else. Choose another with --port.")
    say("Getting Themis")
    if args.bundle:
        release_dir = stage_release(home, bundle=Path(args.bundle).resolve())
        version = release_dir.name
        release = None
    else:
        release = pick_release(list_releases(), channel=args.channel or "stable", version=args.version)
        version = release["version"]
        release_dir = stage_release(home, release)
    say("Docker")
    ensure_docker(home, release_dir, yes=args.yes)
    if not args.skip_image:
        get_cell_image(home, release_dir, version)
    say("Settings")
    made = write_config_env(home, host=args.host, port=port, https=args.https)
    info("wrote a new secret key to config.env" if made else "kept the secret key you already have")
    link_current(home, version)
    home.save_state(
        version=version,
        channel=args.channel or "stable",
        installed_at=datetime.datetime.now(datetime.UTC).isoformat(),
        source=API,
    )
    shim = make_shim(home)
    if str(shim.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        info(f"add {shim.parent} to your PATH to use the `themis` command (or run {shim} directly)")
    if args.no_service:
        say("Service skipped (--no-service)")
        info("start it by hand with: themis run")
    else:
        say("Service")
        install_service(home)
        systemctl("restart", UNIT)
        info("waiting for Themis to come up")
        if not wait_until_up(port, version):
            raise CtlError(f"Themis did not start. See: journalctl -u {UNIT} -n 50   or   themis doctor")
    say("Checking the installation")
    run([str(home.python()), "-m", "app.doctor"], check=False, env=home.env(), cwd=home.current / "backend")
    say("Done")
    shown = "127.0.0.1" if args.host == "127.0.0.1" else args.host
    info(f"Open http://{shown}:{port} and create your account. The first account is the administrator.")
    if args.host == "127.0.0.1":
        info(
            "It only listens on this machine. To reach it from elsewhere, put a reverse proxy with HTTPS in front (see the operations guide)."
        )
    info("Look after it with: themis status | logs | restart | upgrade | doctor")


def cmd_upgrade(args: argparse.Namespace, home: Home) -> None:
    check_platform()
    current = need_installed(home)
    say(f"Themis {current} is installed. Looking for a newer one")
    release = pick_release(
        list_releases(), channel=args.channel or home.state().get("channel", "stable"), version=args.version
    )
    target = release["version"]
    newer = sort_key(target) > sort_key(current)
    if args.check:
        print(
            f"{target} is available (you have {current})"
            if newer
            else f"You have the newest {args.channel or 'stable'} version ({current})."
        )
        return
    if not newer and not args.version:
        info(f"You already have the newest version ({current}).")
        return
    if target == current:
        info(f"{current} is already installed.")
        return
    if sort_key(target) < sort_key(current) and not ask(
        f"{target} is OLDER than {current}. Newer versions may have changed the database in ways {target} cannot read. Go back anyway?",
        yes=args.yes,
    ):
        return
    if not ask(f"Upgrade {current} to {target}?", yes=args.yes, default=True):
        return
    port = configured_port(home)
    new_dir = stage_release(home, release)
    previous = home.current_version()
    say("Checking Docker")
    ensure_docker(home, new_dir, yes=args.yes)
    say("Backing up")
    saved = backup(home, f"pre-{current}-to-{target}")
    info(f"saved the database and settings in {saved}")
    say("Switching")
    try:
        if not args.skip_image:
            get_cell_image(home, new_dir, target)
        if service_installed():
            systemctl("stop", UNIT)
        link_current(home, target)
        restart_service(home)
        if service_installed() and not wait_until_up(port, target):
            raise CtlError(f"Themis {target} did not come up")
    except (CtlError, OSError) as e:
        say(f"That went wrong ({e}). Going back to {previous}")
        rollback(home, previous, saved, port)
        if target != previous:
            shutil.rmtree(
                new_dir, ignore_errors=True
            )  # a release that did not work is not kept (the log says what happened)
        raise CtlError(
            f"The upgrade to {target} failed and Themis {previous} is running again, as before. Details: themis logs, or {home.logs / 'ctl.log'}"
        ) from None
    home.save_state(
        version=target, previous=previous, upgraded_at=datetime.datetime.now(datetime.UTC).isoformat()
    )
    gone = prune(home)
    if gone:
        info(f"removed old releases: {', '.join(gone)}")
    say("Done")
    info(f"Themis {target} is running. The backup of {current} is in {saved}.")


def rollback(home: Home, previous: str, saved: Path, port: int) -> None:
    """Back to the release that worked, with the database as it was: the new one may have changed it."""
    if service_installed():
        systemctl("stop", UNIT, check=False)
    link_current(home, previous)
    restore(home, saved)
    restart_service(home)
    if service_installed() and not wait_until_up(port, previous):
        info(f"Themis {previous} did not come back either. Run: themis doctor")


def cmd_status(args: argparse.Namespace, home: Home) -> None:
    version = need_installed(home)
    port = configured_port(home)
    answer = health(port)
    print(f"Themis {version} in {home.root}")
    print(
        f"  service: {'running' if service_installed() and service_active() else 'not running' if service_installed() else 'none (start it with: themis run)'}"
    )
    print(
        f"  address: http://127.0.0.1:{port}  ({'answering, version ' + str(answer.get('version')) if answer else 'not answering'})"
    )
    others = [v for v in home.installed() if v != version]
    if others:
        print(f"  also on disk (for a rollback): {', '.join(others)}")


def cmd_service(action: str, home: Home) -> None:
    need_installed(home)
    if not service_installed():
        raise CtlError("There is no service. Run it in the foreground with: themis run")
    if action == "logs":
        os.execvp("journalctl", ["journalctl", "-u", UNIT, "-f", "-n", "50"])
    systemctl(action)


def cmd_run(home: Home) -> None:
    need_installed(home)
    os.chdir(home.current / "backend")
    os.execve(str(home.python()), [str(home.python()), "-m", "app.run"], home.env())


def cmd_doctor(rest: list[str], home: Home) -> None:
    need_installed(home)
    os.chdir(home.current / "backend")
    os.execve(str(home.python()), [str(home.python()), "-m", "app.doctor", *rest], home.env())


def cmd_uninstall(args: argparse.Namespace, home: Home) -> None:
    if service_installed():
        systemctl("disable", "--now", UNIT, check=False)
        run([*sudo_prefix(), "rm", "-f", UNIT_PATH])
        systemctl("daemon-reload", check=False)
    shim = Path.home() / ".local" / "bin" / "themis"
    with contextlib.suppress(FileNotFoundError):
        shim.unlink()
    if args.purge:
        if not ask(
            f"Delete EVERYTHING in {home.root}: the database, all projects' files and the secret key? This cannot be undone.",
            yes=args.yes,
        ):
            return
        shutil.rmtree(home.root, ignore_errors=True)
        print("Themis and all its data are gone.")
    else:
        for name in ("current",):
            with contextlib.suppress(OSError):
                (home.root / name).unlink()
        shutil.rmtree(home.releases, ignore_errors=True)
        print(
            f"Themis is removed. Your data is kept in {home.root} (db/, data/, backups/, config.env); delete that folder to remove it too."
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="themis", description="Install, upgrade and look after Themis.")
    p.add_argument("--home", help=f"where Themis lives (default {default_home()})")
    sub = p.add_subparsers(dest="command", required=True)
    # --home is accepted before the command (`themis --home X install`) and after it (`install.sh --home X`, which is how
    # the one-line installer passes options on). SUPPRESS: when it is not given after the command, the first one stays.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", default=argparse.SUPPRESS, help="where Themis lives")

    def add_source(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--channel", choices=["stable", "beta"], help="stable (default) or beta (pre-releases too)"
        )
        sp.add_argument("--version", help="a specific version, such as 0.2.0")
        sp.add_argument("--yes", "-y", action="store_true", help="answer yes to questions")

    i = sub.add_parser("install", parents=[common], help="install Themis (safe to run again)")
    add_source(i)
    i.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to listen on (127.0.0.1: this machine only; 0.0.0.0: your network)",
    )
    i.add_argument("--port", type=int, default=8000)
    i.add_argument("--https", action="store_true", help="you serve it over HTTPS (secure cookies)")
    i.add_argument("--no-service", action="store_true", help="do not register a service")
    i.add_argument("--bundle", help="install from this bundle file instead of downloading (testing, offline)")
    i.add_argument(
        "--skip-image",
        action="store_true",
        help="do not pull or build the agent image (offline, or you provide your own)",
    )
    u = sub.add_parser(
        "upgrade",
        parents=[common],
        help="upgrade to the newest version, with a backup and a rollback if it fails",
    )
    add_source(u)
    u.add_argument("--check", action="store_true", help="only say whether a newer version exists")
    u.add_argument("--skip-image", action="store_true", help="do not pull or build the agent image")
    for name in ("start", "stop", "restart", "logs"):
        sub.add_parser(name, parents=[common], help=f"{name} the service")
    sub.add_parser("status", parents=[common], help="what is installed and whether it is running")
    sub.add_parser("run", parents=[common], help="run the server in the foreground")
    d = sub.add_parser("doctor", help="check this machine and show how the last starts went", add_help=False)
    d.add_argument("rest", nargs=argparse.REMAINDER)
    sub.add_parser("backup", parents=[common], help="save a copy of the database and settings")
    r = sub.add_parser("restore", parents=[common], help="put a backup back (stop the service first)")
    r.add_argument("folder")
    sub.add_parser("version", parents=[common], help="the installed version")
    x = sub.add_parser("uninstall", parents=[common], help="remove Themis (your data is kept unless --purge)")
    x.add_argument("--purge", action="store_true")
    x.add_argument("--yes", "-y", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    global _log_file
    args = build_parser().parse_args(argv)
    home = Home(args.home or default_home())
    if home.root.exists() or args.command == "install":
        home.logs.mkdir(parents=True, exist_ok=True)
        _log_file = home.logs / "ctl.log"
    try:
        match args.command:
            case "install":
                cmd_install(args, home)
            case "upgrade":
                cmd_upgrade(args, home)
            case "status":
                cmd_status(args, home)
            case "start" | "stop" | "restart" | "logs":
                cmd_service(args.command, home)
            case "run":
                cmd_run(home)
            case "doctor":
                cmd_doctor(args.rest, home)
            case "backup":
                need_installed(home)
                print(backup(home, "manual"))
            case "restore":
                if service_installed() and service_active():
                    raise CtlError("Stop Themis first: themis stop")
                restore(home, Path(args.folder))
                print("Restored. Start Themis again with: themis start")
            case "version":
                print(need_installed(home))
            case "uninstall":
                cmd_uninstall(args, home)
    except CtlError as e:
        print(f"\nError: {e}", file=sys.stderr)
        _log(f"ERROR {e}")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
