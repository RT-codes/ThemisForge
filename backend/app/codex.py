"""A user's Codex connection: sign in with ChatGPT once, so Codex usage is drawn from their plan (not API billing).

Safety rules this module keeps:
- The sign in runs in a throwaway CODEX_HOME in the system temp dir (never inside the repository) that is deleted
  afterwards, so a login can never end up in a commit.
- The resulting auth.json is encrypted (app/crypto.py) before it touches the database. Plaintext lives in memory only.
- Tokens are never logged and never returned by the API; the UI only gets a status.
- No file paths are involved in storing or handing out the login, so it behaves the same on Linux, macOS and Windows.
"""

import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import DEFAULT_SECRET_KEY, settings
from .crypto import decrypt, encrypt
from .models import CodexConnection, utcnow

log = logging.getLogger("themis.codex")

LOGIN_TIMEOUT_SECONDS = 15 * 60  # the one-time code expires after 15 minutes
CODE_WAIT_SECONDS = 20  # how long starting a sign in waits for Codex to print its code

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_URL = re.compile(r"https://\S+")
_CODE = re.compile(r"^[A-Za-z0-9-]{4,24}$")


class CodexError(Exception):
    """Something the user can act on (CLI missing, not connected, unusable login)."""


def codex_executable() -> str | None:
    return shutil.which(settings.codex_bin)


def key_is_secure() -> bool:
    return settings.secret_key != DEFAULT_SECRET_KEY


def parse_auth(text: str) -> dict:
    """The decoded auth.json, or CodexError when it is not a ChatGPT sign in."""
    try:
        data = json.loads(text)
    except ValueError:
        raise CodexError("The Codex login could not be read") from None
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if not isinstance(tokens, dict) or not tokens.get("refresh_token") or not tokens.get("access_token"):
        raise CodexError("That was not a ChatGPT sign in, so it would not use your plan's Codex usage")
    return data


def _account_label(auth: dict) -> str:
    """The email shown in the UI, read from the (unverified, display-only) id token."""
    try:
        payload = auth["tokens"]["id_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return str(claims.get("email") or "")[:320]
    except (KeyError, IndexError, AttributeError, ValueError):
        return ""


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def get_connection(session: AsyncSession, user_id: int) -> CodexConnection | None:
    return await session.scalar(select(CodexConnection).where(CodexConnection.user_id == user_id))


async def save_auth(
    session: AsyncSession, user_id: int, text: str, *, fresh: bool = False
) -> CodexConnection:
    """Encrypt and store a login. `fresh` marks a new sign in (as opposed to a token refresh written back)."""
    auth = parse_auth(text)
    conn = await get_connection(session, user_id)
    if conn is None:
        conn = CodexConnection(user_id=user_id)
        session.add(conn)
        fresh = True
    if fresh:
        conn.connected_at = utcnow()
    conn.auth_encrypted = encrypt(text)
    conn.account = _account_label(auth) or conn.account or ""
    conn.refreshed_at = _parse_time(auth.get("last_refresh")) or utcnow()
    await session.commit()
    return conn


# ----- using the login (cells) -----

_locks: dict[int, asyncio.Lock] = {}


class CodexLease:
    """The decrypted login, held exclusively. Write the refreshed login back with save_back()."""

    def __init__(self, maker: async_sessionmaker[AsyncSession], user_id: int, auth_json: str) -> None:
        self._maker = maker
        self._user_id = user_id
        self.auth_json = auth_json

    async def save_back(self, text: str) -> None:
        """Store a refreshed login. It must belong to the same ChatGPT account: a cell is not trusted to swap it."""
        old = parse_auth(self.auth_json)["tokens"].get("account_id")
        new = parse_auth(text)["tokens"].get("account_id")
        if old and old != new:
            raise CodexError("The refreshed login belongs to a different account, so it was not stored")
        async with self._maker() as session:
            await save_auth(session, self._user_id, text)
        self.auth_json = text


def lease_is_busy(user_id: int) -> bool:
    lock = _locks.get(user_id)
    return lock is not None and lock.locked()


@asynccontextmanager
async def lease_codex(maker: async_sessionmaker[AsyncSession], user_id: int) -> AsyncIterator[CodexLease]:
    """Exclusive use of one user's login. Codex rotates refresh tokens, so two cells refreshing the same
    login at once could invalidate each other: runs for one user take turns."""
    async with _locks.setdefault(user_id, asyncio.Lock()):
        async with maker() as session:
            conn = await get_connection(session, user_id)
            text = decrypt(conn.auth_encrypted) if conn else None
        if text is None:
            raise CodexError(
                "Codex is not connected for the project owner (or needs reconnecting). Connect it in Settings."
            )
        yield CodexLease(maker, user_id, text)


# ----- signing in -----


@dataclass
class LoginFlow:
    status: str = "starting"  # starting | waiting | connected | failed | cancelled
    verification_url: str = ""
    code: str = ""
    expires_at: datetime | None = None
    error: str = ""
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return self.status in ("starting", "waiting")


class CodexLogins:
    """Runs `codex login --device-auth` for users: they get a code and a link, sign in on any device, done.
    The server never needs a browser callback, which also makes it work behind a reverse proxy."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker
        self._flows: dict[int, LoginFlow] = {}

    def get(self, user_id: int) -> LoginFlow | None:
        return self._flows.get(user_id)

    async def start(self, user_id: int) -> LoginFlow:
        exe = codex_executable()
        if exe is None:
            raise CodexError(
                "The Codex CLI was not found on this machine. Install it, or set THEMIS_CODEX_BIN."
            )
        await self.cancel(user_id)
        flow = LoginFlow()
        self._flows[user_id] = flow
        flow.task = asyncio.create_task(self._run(user_id, flow, exe))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(flow.ready.wait(), CODE_WAIT_SECONDS)
        return flow

    async def cancel(self, user_id: int) -> None:
        flow = self._flows.get(user_id)
        if flow is None or not flow.active or flow.task is None:
            return
        flow.status = "cancelled"
        flow.task.cancel()
        await asyncio.gather(flow.task, return_exceptions=True)

    async def shutdown(self) -> None:
        for user_id in list(self._flows):
            await self.cancel(user_id)

    async def _run(self, user_id: int, flow: LoginFlow, exe: str) -> None:
        home = tempfile.mkdtemp(prefix="themis-codex-")  # private to this user and outside the repository
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "login", "-c", 'cli_auth_credentials_store="file"', "--device-auth",
                env={**os.environ, "CODEX_HOME": home},
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )  # fmt: skip
            async with asyncio.timeout(LOGIN_TIMEOUT_SECONDS):
                await self._read_prompt(proc, flow)
                exit_code = await proc.wait()
            auth_file = Path(home) / "auth.json"
            if exit_code != 0 or not auth_file.is_file():
                raise CodexError("The sign in did not finish. Start again to get a new code.")
            async with self._maker() as session:
                await save_auth(session, user_id, auth_file.read_text(encoding="utf-8"), fresh=True)
            flow.status = "connected"
        except asyncio.CancelledError:
            flow.status = "cancelled"
            raise
        except TimeoutError:
            flow.status, flow.error = "failed", "The code expired. Start again to get a new one."
        except CodexError as e:
            flow.status, flow.error = "failed", str(e)
        except Exception:
            log.exception("Codex sign in failed")  # the message can never contain the login itself
            flow.status, flow.error = "failed", "Could not complete the sign in"
        finally:
            flow.ready.set()
            if proc is not None and proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
            shutil.rmtree(home, ignore_errors=True)

    @staticmethod
    async def _read_prompt(proc: asyncio.subprocess.Process, flow: LoginFlow) -> None:
        """Read Codex's instructions (a link, then a one-time code) and keep draining until it exits."""
        assert proc.stdout is not None
        want_code = False
        while raw := await proc.stdout.readline():
            line = _ANSI.sub("", raw.decode(errors="replace")).strip()
            if not flow.verification_url and (url := _URL.search(line)):
                flow.verification_url = url.group(0)
            elif want_code and not flow.code and _CODE.match(line):
                flow.code = line
            if "one-time code" in line.lower():
                want_code = True
            if flow.status == "starting" and flow.verification_url and flow.code:
                flow.status = "waiting"
                flow.expires_at = utcnow() + timedelta(seconds=LOGIN_TIMEOUT_SECONDS)
                flow.ready.set()
