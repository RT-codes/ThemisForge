"""Is there a newer Themis? Asked once a day (and on request), shown to administrators.

The whole exchange is one plain GET of the public list of releases from GitHub, which carries no account, project or
machine details (GitHub sees the address it comes from and the program's name and version in the User-Agent, like any
download). It can be switched off in Settings. Nothing is ever installed from here: the notice says to run
`themis upgrade`, which is where a backup is taken and a failed upgrade is rolled back.
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from .app_settings import AppSettings, load_settings
from .config import settings
from .version import build_info, is_newer, sort_key

log = logging.getLogger(__name__)

FIRST_CHECK_SECONDS = 60  # a moment after start, so starting is never held up by the network
CHECK_EVERY_SECONDS = 24 * 3600
MIN_BETWEEN_MANUAL_SECONDS = 30  # "Check now" cannot be used to hammer GitHub
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Release:
    version: str  # 0.2.0
    url: str  # the release's page, with its notes
    prerelease: bool
    published: str


def pick_latest(releases: object, channel: str = "stable") -> Release | None:
    """The newest release of the channel from GitHub's list: stable skips pre-releases and drafts, beta takes them too.
    Anything that is not shaped like a release (a tag that is not a version, a damaged answer) is ignored."""
    if not isinstance(releases, list):
        return None
    best: Release | None = None
    for r in releases:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        tag = str(r.get("tag_name", "")).removeprefix("v")
        try:
            sort_key(tag)
        except ValueError:
            continue
        pre = bool(r.get("prerelease")) or "-" in tag
        if pre and channel != "beta":
            continue
        candidate = Release(tag, str(r.get("html_url", "")), pre, str(r.get("published_at", "")))
        if best is None or sort_key(candidate.version) > sort_key(best.version):
            best = candidate
    return best


@dataclass(frozen=True)
class UpdateInfo:
    enabled: bool  # the check is switched on in Settings
    current: str  # this install's release number
    latest: str  # the newest release of the channel, "" until a check has worked
    available: bool  # latest is newer than current (never for a git checkout: its own developer is ahead of any release)
    url: str  # the release notes
    checked_at: str  # when the last check worked, ISO time, "" if never
    error: str  # why the last check failed, in words, "" when it did not
    channel: str
    kind: str  # "release" | "checkout"

    def to_dict(self) -> dict:
        return asdict(self)


class UpdateChecker:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # tests stand in for the network here
        self.latest: Release | None = None
        self.checked_at: datetime | None = None
        self.error = ""
        self._last_attempt = float("-inf")
        self._wake = asyncio.Event()

    def info(self, cfg: AppSettings) -> UpdateInfo:
        build = build_info()
        # a result for the other channel is not shown: switching channels shows the right answer after the next check
        latest = self.latest.version if self.latest else ""
        available = (
            cfg.check_for_updates
            and build.kind == "release"
            and bool(latest)
            and is_newer(latest, build.release)
        )
        return UpdateInfo(
            enabled=cfg.check_for_updates,
            current=build.release,
            latest=latest,
            available=available,
            url=self.latest.url if self.latest else "",
            checked_at=self.checked_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.checked_at else "",
            error=self.error,
            channel=cfg.update_channel,
            kind=build.kind,
        )

    async def check(self, cfg: AppSettings, *, force: bool = False) -> None:
        """Looks once. Never raises: a network that is down or an answer that makes no sense is recorded as the error."""
        if not cfg.check_for_updates:
            return
        if not force and time.monotonic() - self._last_attempt < MIN_BETWEEN_MANUAL_SECONDS:
            return
        self._last_attempt = time.monotonic()
        url = f"{settings.release_api.rstrip('/')}/releases?per_page=30"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": f"Themis/{build_info().release}"}
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, headers=headers, transport=self._transport, follow_redirects=True
            ) as client:
                response = await client.get(url)
            if response.status_code != 200:
                raise ValueError(f"GitHub answered {response.status_code}")
            latest = pick_latest(response.json(), cfg.update_channel)
        except (httpx.HTTPError, ValueError, OSError) as e:
            self.error = f"Could not check for updates: {str(e)[:150] or type(e).__name__}"
            log.info("Update check failed: %s", self.error)
            return
        self.latest, self.error = latest, ""
        self.checked_at = datetime.now(UTC)

    def wake(self) -> None:
        """Look again now (the setting was switched on, or the channel changed)."""
        self._wake.set()

    async def watch(self, maker: async_sessionmaker) -> None:
        await asyncio.sleep(FIRST_CHECK_SECONDS)
        while True:
            try:
                async with maker() as session:
                    await self.check(await load_settings(session), force=True)
            except Exception:
                log.exception("The update check failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), CHECK_EVERY_SECONDS)
            self._wake.clear()
