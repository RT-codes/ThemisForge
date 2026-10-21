"""Notifications out: Themis tells a project's owner that something happened, in a chat they already look at.

Two halves. The shared half is here: `notify()` is called where things happen (a task failed, a run waits for an
approval), looks up the project's targets that listen for that event, and sends. The adapter half is one small entry in
`KINDS` per service: the fields it needs, how to check them, and how to send one message. A new service is a new
entry, nothing else changes (the settings screen builds its form from `KINDS`).

Sending never holds anything up. `notify()` hands the work to a background task and returns at once, because the
scheduler must not wait for somebody's chat server. A message that cannot be sent is written on the target
(`last_error`) so the settings screen can say so, and is not retried: the next event is the retry.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crypto import decrypt, encrypt
from app.persistence.models import NotificationTarget, Project, utcnow

log = logging.getLogger("app.notifications")

# What a target can listen for. "attention" is anything that waits for a person: a task in review, a run at an
# approval gate.
EVENTS = {
    "failed": "A task failed",
    "attention": "Something waits for me (a review or an approval)",
    "done": "A task finished",
}
HEADLINES = {"failed": "Failed", "attention": "Needs your attention", "done": "Done", "test": "Test"}

TIMEOUT_SECONDS = 10  # a chat server that is slower than this is treated as down
MAX_TEXT = 1800  # characters of a message; Discord refuses more than 2000
# The same event for the same task on the same target is sent once in this time. A recurring task that fails every
# minute would otherwise bury the chat, and the first message already said it.
REPEAT_SECONDS = 300


class NotifyError(Exception):
    """A message could not be sent. The text is shown to the owner, so it never contains the secret address."""


@dataclass(frozen=True)
class Notice:
    event: str  # a key of EVENTS, or "test"
    title: str  # what it is about, e.g. the task's title
    body: str  # one or two lines more, may be empty
    project: str  # the project's name


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    placeholder: str = ""
    help: str = ""


@dataclass(frozen=True)
class Kind:
    label: str
    description: str
    fields: tuple[Field, ...]
    # "" when the fields are usable, else what is wrong with them
    check: Callable[[dict[str, str]], str]
    send: Callable[[dict[str, str], Notice], Awaitable[None]]


# the sending half


async def _post(url: str, payload: dict) -> None:
    # No redirects: the address was checked when it was saved, and a redirect could lead somewhere it was not.
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        # the exception text can carry the address, which is a secret: say only what kind of failure it was
        raise NotifyError(f"Could not reach it ({type(e).__name__})") from None
    if response.status_code >= 300:
        raise NotifyError(f"It answered with status {response.status_code}")


def _text(notice: Notice) -> str:
    lines = [f"**{HEADLINES[notice.event]}** · {notice.project}", notice.title, notice.body]
    return "\n".join(line for line in lines if line.strip())[:MAX_TEXT]


# Discord channel webhooks: https://discord.com/api/webhooks/<id>/<token>, optionally with ?thread_id=. Only Discord's
# own hosts are accepted, so this can never be used to make the server post to some other address.
_DISCORD = re.compile(
    r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/[\w-]+/?(?:\?[\w=&-]*)?$"
)


def _check_discord(config: dict[str, str]) -> str:
    if not _DISCORD.match(config.get("url", "")):
        return "That is not a Discord webhook address. It starts with https://discord.com/api/webhooks/"
    return ""


async def _send_discord(config: dict[str, str], notice: Notice) -> None:
    # allowed_mentions: a task title that says @everyone must not ping the whole server
    await _post(config["url"], {"content": _text(notice), "allowed_mentions": {"parse": []}})


KINDS: dict[str, Kind] = {
    "discord": Kind(
        label="Discord",
        description="Posts to a channel. Make a webhook in the channel's settings, under Integrations.",
        fields=(
            Field(
                "url",
                "Webhook address",
                "https://discord.com/api/webhooks/...",
                "Keep it private: anyone who has it can post in your channel.",
            ),
        ),
        check=_check_discord,
        send=_send_discord,
    ),
}


# what is stored


def pack(kind: str, config: dict[str, str]) -> tuple[str, str]:
    """The config as it is stored (encrypted) and a hint to tell targets apart. Raises ValueError when the kind is
    unknown or the config is not usable."""
    adapter = KINDS.get(kind)
    if adapter is None:
        raise ValueError(f"Unknown kind: {kind}")
    config = {f.name: config.get(f.name, "").strip() for f in adapter.fields}
    if problem := adapter.check(config):
        raise ValueError(problem)
    return encrypt(json.dumps(config)), "..." + next(iter(config.values()))[-6:]


def unpack(target: NotificationTarget) -> dict[str, str] | None:
    """The config in the clear, or None when it cannot be read (the secret key changed since it was stored)."""
    raw = decrypt(target.config_encrypted)
    return json.loads(raw) if raw is not None else None


# the shared half

_recent: dict[tuple[int, str, str], float] = {}  # (target, event, title) -> when it was last sent
pending: set[asyncio.Task] = set()  # background sends; held so they are not collected before they finish


def _repeated(target_id: int, notice: Notice) -> bool:
    """Count this message against the target. In memory, like the webhooks' rate limit: a restart forgetting it only
    means one extra message."""
    now = time.monotonic()
    for key in [k for k, at in _recent.items() if now - at > REPEAT_SECONDS]:
        del _recent[key]
    key = (target_id, notice.event, notice.title)
    if key in _recent:
        return True
    _recent[key] = now
    return False


async def deliver(target: NotificationTarget, notice: Notice) -> str:
    """Send one message to a target. Returns "" when it went through, else why it did not."""
    config = unpack(target)
    if config is None:
        return "The stored address could not be read. If THEMIS_SECRET_KEY changed, add it again."
    try:
        await KINDS[target.kind].send(config, notice)
    except NotifyError as e:
        return str(e)[:300]
    except KeyError:
        return f"Unknown kind: {target.kind}"
    return ""


async def _notify(
    maker: async_sessionmaker[AsyncSession], project_id: int, event: str, title: str, body: str
):
    # The session is closed before anything is sent: SQLite lets only one writer in, and a session held open across
    # somebody's slow chat server would make the scheduler wait for it.
    async with maker() as s:
        project = await s.get(Project, project_id)
        if project is None:
            return
        targets = list(
            await s.scalars(
                select(NotificationTarget).where(
                    NotificationTarget.project_id == project_id, NotificationTarget.enabled.is_(True)
                )
            )
        )
    notice = Notice(event, title, body, project.name)
    results = {
        t.id: await deliver(t, notice) for t in targets if event in t.events and not _repeated(t.id, notice)
    }
    if not results:
        return
    async with maker() as s:
        for target_id, error in results.items():
            if (target := await s.get(NotificationTarget, target_id)) is not None:
                target.last_error = error
                if not error:
                    target.last_sent_at = utcnow()
        await s.commit()


def notify(
    maker: async_sessionmaker[AsyncSession], project_id: int, event: str, title: str, body: str = ""
) -> None:
    """Tell the project's targets that listen for `event`. Returns at once; the sending happens in the background and
    never raises into the caller."""

    async def run() -> None:
        try:
            await _notify(maker, project_id, event, title.strip()[:200], body.strip()[:500])
        except Exception:
            log.exception("notification for project %s failed", project_id)

    task = asyncio.get_running_loop().create_task(run())
    pending.add(task)
    task.add_done_callback(pending.discard)
