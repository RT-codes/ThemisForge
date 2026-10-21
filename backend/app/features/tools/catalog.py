"""A local copy of the MCP registry's catalog, for browsing it.

Why a copy: the registry's own search takes 10 to 20 seconds a request (and sometimes more than a minute), it can only
list alphabetically, and it knows nothing of categories or popularity. Its plain listing is fast though (about half a
second for 100 tools), so Themis reads all of it once (about five minutes for some 40,000 tools), keeps it in one file
under the data folder, and afterwards asks only for what changed (`updated_since`). Search, categories, sorting and
counts are then instant and local.

The registry has no popularity figure. What is ranked on instead is stated in `_score`, and npm download counts (the
one public number there is, only for npm packages) are fetched from npm in the background and kept next to the rows.
"""

import asyncio
import contextlib
import json
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import yaml

import app.features.tools.registry as mcp_registry
from app.config import settings
from app.features.tools.registry import (
    RegistryTool,
    RegistryUnavailable,
    Way,
    display_title,
    pick_way,
    reason_text,
)

CATEGORIES_FILE = Path(__file__).with_name("registry_categories.yaml")
NPM_DOWNLOADS_URL = "https://api.npmjs.org/downloads/point/last-month/"

PAGE = 100  # the registry's largest page
SYNC_EVERY = timedelta(hours=24)
OVERLAP = timedelta(
    minutes=10
)  # an update starts a little before the last one began, so nothing slips between
RETRY_AFTER = 60  # seconds before a failed sync is tried again
DOWNLOADS_EVERY = timedelta(days=7)
DOWNLOAD_BATCH = 100  # npm answers up to 128 unscoped names in one request
# npm cannot count scoped packages in bulk, and it answers 429 after a handful of single requests a second. So they are
# asked slowly, a limited number at a time, most recently updated first, and the rest on later runs.
SCOPED_PER_RUN = 250
SCOPED_DELAY = 1.5  # seconds between two single requests
DOWNLOADS_RETRY = timedelta(hours=1)
BULK_NAMESPACE = 60  # a publisher with more tools than this is bulk-publishing and is ranked below the rest
FORMAT = 1  # of the file: a different one is read as no file, and the catalog is built again

SORTS = ("recommended", "downloads", "updated", "name")

_GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/")
_GITHUB_NAMESPACE = re.compile(r"^io\.github\.([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/")
_ICON_TYPES = {None, "", "image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp"}


@dataclass(slots=True)
class Row:
    """One tool of the registry, with what the browser needs and nothing else (a tool's inputs are read from the
    registry's entry when one is picked)."""

    name: str
    title: str
    description: str
    version: str
    repository: str
    icon: str  # the icon the publisher declared (https only), or ""
    updated: str  # ISO time
    ways: list[Way]
    npm: str = ""  # the npm package it would run, whose downloads are counted
    downloads: int | None = None
    downloads_at: str = ""  # ISO time of the count
    # worked out when the catalog is loaded, not stored
    category: str = "other"
    bulk: bool = False
    vendor: str = ""  # the domain a verified publisher owns ("notion" for com.notion/mcp), else ""
    display: str = ""  # what it is called in a list
    hay: str = ""
    name_hay: str = ""

    def stored(self) -> dict:
        return {
            "n": self.name,
            "t": self.title,
            "d": self.description,
            "v": self.version,
            "r": self.repository,
            "i": self.icon,
            "u": self.updated,
            "w": [list(w) for w in self.ways],
            "p": self.npm,
            "dl": self.downloads,
            "da": self.downloads_at,
        }

    @classmethod
    def from_stored(cls, d: dict) -> "Row":
        return cls(
            name=d["n"],
            title=d["t"],
            description=d["d"],
            version=d["v"],
            repository=d["r"],
            icon=d["i"],
            updated=d["u"],
            ways=[Way(*w) for w in d["w"]],
            npm=d.get("p", ""),
            downloads=d.get("dl"),
            downloads_at=d.get("da", ""),
        )


def _declared_icon(entry: dict) -> str:
    for icon in entry.get("icons") or []:
        src = icon.get("src") if isinstance(icon, dict) else None
        if isinstance(src, str) and src.startswith("https://") and icon.get("mimeType") in _ICON_TYPES:
            return src[:500]
    return ""


def icon_url(row: Row) -> str:
    """An image to show for a tool: the one its publisher declared, else the avatar of its GitHub owner, else "" (the
    app then draws the initials). GitHub is the one host this adds, and it is only ever asked by the browser."""
    if row.icon:
        return row.icon
    match = _GITHUB_REPO.match(row.repository) or _GITHUB_NAMESPACE.match(row.name)
    return f"https://github.com/{match.group(1)}.png?size=80" if match else ""


def make_row(item: dict) -> Row | None:
    """A catalog row for one item of the registry's listing (None when it is not an active tool)."""
    entry = item.get("server") if isinstance(item, dict) else None
    if not isinstance(entry, dict) or not mcp_registry.is_active(item) or not entry.get("name"):
        return None
    meta = (item.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
    name = str(entry["name"])
    return Row(
        name=name,
        title=str(entry.get("title") or ""),
        description=str(entry.get("description") or "")[:400],
        version=str(entry.get("version") or ""),
        repository=str((entry.get("repository") or {}).get("url") or "")[:300],
        icon=_declared_icon(entry),
        updated=str(meta.get("updatedAt") or meta.get("publishedAt") or ""),
        ways=mcp_registry.ways_of(entry),
        npm=mcp_registry.npm_identifier(entry),
    )


# ----- categories and ranking -----


@dataclass
class _Category:
    id: str
    label: str
    words: frozenset[str]
    phrases: tuple[str, ...]  # keywords of several words, matched inside the text


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _load_categories() -> list[_Category]:
    try:
        data = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    out = []
    for item in data.get("categories", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("label"):
            continue
        keywords = [_normal(str(k)) for k in item.get("keywords") or []]
        out.append(
            _Category(
                str(item["id"]),
                str(item["label"]),
                frozenset(k for k in keywords if k and " " not in k),
                tuple(k for k in keywords if " " in k),
            )
        )
    return out


def _category_of(row: Row, categories: list[_Category]) -> str:
    """The category whose keywords the tool matches most: three points for each in its name or title, one for each in
    its description. The first of equals wins, and a tool that matches nothing is "other"."""
    name_text = _normal(f"{row.name.rsplit('/', 1)[-1]} {row.title}")
    desc_text = _normal(row.description)
    name_words, desc_words = set(name_text.split()), set(desc_text.split())
    name_padded, desc_padded = f" {name_text} ", f" {desc_text} "
    best, best_score = "other", 0
    for c in categories:
        score = 3 * (len(name_words & c.words) + sum(1 for p in c.phrases if f" {p} " in name_padded)) + (
            len(desc_words & c.words) + sum(1 for p in c.phrases if f" {p} " in desc_padded)
        )
        if score > best_score:
            best, best_score = c.id, score
    return best


def _score(row: Row, available: frozenset[str] | None, now: datetime) -> float:
    """What "recommended" orders by. It is not popularity (the registry has none), it is how much a listing looks like a
    real, maintained tool you can use here: runnable, not bulk-published, a verified publisher, filled in, recent, and
    (for npm packages) downloaded."""
    score = 0.0
    if not pick_way(row.ways, available).reason:
        score += 20
    if row.bulk:
        score -= 40
    if row.vendor:
        score += 25  # a domain the publisher proved it owns
    elif row.repository:
        score += 5
    if row.icon:
        score += 8
    if row.repository:
        score += 5
    if len(row.description) >= 60:
        score += 5
    try:
        age = (now - datetime.fromisoformat(row.updated)).days
    except ValueError:
        age = 10_000
    score += 10 if age <= 30 else 5 if age <= 90 else -10 if age > 365 else 0
    if row.downloads:
        score += min(7 * math.log10(row.downloads + 1), 55)  # 1,000 is +21, 1,000,000 is +42
    return score


@dataclass
class Browse:
    """One page of a browse: the rows with the way each would run, how many matched, and the count per category."""

    rows: list[tuple[Row, Way]]
    total: int
    categories: list[tuple[str, str, int]]  # (id, label, how many of the matches)


# ----- the catalog -----


@dataclass
class Catalog:
    rows: dict[str, Row] = field(default_factory=dict)
    synced_at: str = ""  # ISO time the last complete sync started
    loaded: bool = False
    state: str = "empty"  # empty | building | updating | ready | error
    error: str = ""
    failed_at: float = 0.0
    task: asyncio.Task | None = None
    counting: bool = False  # npm downloads are being counted
    progress: int = 0  # tools read so far by a sync that is running
    _counted_at: float = -1e9  # when npm downloads were last counted (monotonic)
    _categories: list[_Category] = field(default_factory=list)
    _categories_stamp: float | None = None

    # -- the file --

    @staticmethod
    def path() -> Path:
        return settings.data_dir / "cache" / "mcp-registry.json"

    def _read(self) -> None:
        try:
            data = json.loads(self.path().read_text(encoding="utf-8"))
            if data.get("format") != FORMAT:
                return
            rows = [Row.from_stored(d) for d in data["rows"]]
        except (OSError, ValueError, KeyError, TypeError):
            return  # no file, or one that cannot be used: the catalog is built again
        self.rows = {r.name: r for r in rows}
        self.synced_at = str(data.get("synced_at") or "")

    def _write(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "format": FORMAT,
                    "synced_at": self.synced_at,
                    "rows": [r.stored() for r in self.rows.values()],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)  # a reader never sees half a file

    async def load(self) -> None:
        if self.loaded:
            return
        await asyncio.to_thread(self._read)
        self.loaded = True
        self._derive(self.rows)
        if self.rows:
            self.state = "ready"

    # -- what is worked out from the rows --

    def _derive(self, rows: dict[str, Row]) -> None:
        """Works out what is derived for `rows` (done before they are shown, so browsing never sees half of it)."""
        namespaces = Counter(r.name.split("/", 1)[0] for r in rows.values())
        self._categories = _load_categories()
        self._categories_stamp = self._stamp()
        for r in rows.values():
            namespace = r.name.split("/", 1)[0]
            r.bulk = namespaces[namespace] > BULK_NAMESPACE
            # "io.github." is on every one of these tools: leaving it in would make a search for "github" match them all
            handle = namespace.removeprefix("io.github.")
            parts = namespace.split(".")
            r.vendor = parts[1].lower() if not namespace.startswith("io.github.") and len(parts) > 1 else ""
            r.display = display_title(r.name, r.title)
            r.name_hay = f"{handle} {r.name.split('/', 1)[-1]} {r.title}".lower()
            r.hay = f"{r.name_hay} {r.description}".lower()
            r.category = _category_of(r, self._categories)

    @staticmethod
    def _stamp() -> float | None:
        try:
            return CATEGORIES_FILE.stat().st_mtime
        except OSError:
            return None

    # -- keeping it current --

    def status(self) -> dict:
        return {
            "state": self.state,
            "count": self.progress if self.state == "building" else len(self.rows),
            "synced_at": self.synced_at,
            "error": self.error,
            "counting": self.counting,
        }

    async def ensure_current(self) -> None:
        """Starts reading the registry in the background when there is no catalog yet, or it is a day old. A failed
        attempt is tried again after a minute, when somebody next browses."""
        await self.load()
        if self.task and not self.task.done():
            return
        if self.state == "error" and time.monotonic() - self.failed_at < RETRY_AFTER:
            return
        if not self.rows:
            self.task = asyncio.create_task(self.sync(full=True))
        elif self._stale():
            self.task = asyncio.create_task(self.sync(full=False))
        elif time.monotonic() - self._counted_at > DOWNLOADS_RETRY.total_seconds() and self._uncounted():
            self.task = asyncio.create_task(self.count_downloads())

    def _stale(self) -> bool:
        try:
            return datetime.now(UTC) - datetime.fromisoformat(self.synced_at) > SYNC_EVERY
        except ValueError:
            return True

    async def sync(self, *, full: bool) -> None:
        """Reads the registry's listing (all of it, or what changed since the last sync) into the catalog."""
        started = datetime.now(UTC)
        since = ""
        if not full and self.synced_at:
            since = (datetime.fromisoformat(self.synced_at) - OVERLAP).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.state = "updating" if self.rows else "building"
        self.error = ""
        fresh: dict[str, Row] = {} if (full or not self.rows) else dict(self.rows)
        gone: set[str] = set()
        cursor = ""
        try:
            while True:
                params = {"version": "latest", "limit": str(PAGE)}
                if cursor:
                    params["cursor"] = cursor
                if since:
                    params["updated_since"] = since
                body = await self._listing(params)
                for item in body.get("servers") or []:
                    row = make_row(item)
                    if row:
                        old = fresh.get(row.name)
                        if old and old.npm == row.npm:  # an update does not forget what npm said
                            row.downloads, row.downloads_at = old.downloads, old.downloads_at
                        fresh[row.name] = row
                    elif isinstance(item, dict) and isinstance(item.get("server"), dict):
                        gone.add(str(item["server"].get("name")))
                self.progress = len(fresh)
                cursor = str((body.get("metadata") or {}).get("nextCursor") or "")
                if not cursor:
                    break
        except RegistryUnavailable as e:
            self.state, self.error, self.failed_at = "error", str(e), time.monotonic()
            if not full and self.rows:
                self.state = "ready"  # the copy it has is still good
            return
        for name in gone:
            fresh.pop(name, None)
        await asyncio.to_thread(self._derive, fresh)
        self.rows = fresh
        self.progress = 0
        self.synced_at = started.strftime("%Y-%m-%dT%H:%M:%SZ")
        await asyncio.to_thread(self._write)
        self.state = "ready"
        await self.count_downloads()

    async def _listing(self, params: dict[str, str]) -> dict:
        """One page of the registry's listing, tried again a few times: a sync is long and the registry is slow."""
        for attempt in range(4):
            try:
                body = await mcp_registry.fetch_json(mcp_registry.REGISTRY_URL, params)
            except RegistryUnavailable:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if not isinstance(body, dict):
                raise RegistryUnavailable("The MCP registry sent something unexpected.")
            return body
        raise RegistryUnavailable("The MCP registry could not be read.")  # not reached

    # -- npm download counts --

    def _uncounted(self) -> list[Row]:
        cutoff = (datetime.now(UTC) - DOWNLOADS_EVERY).strftime("%Y-%m-%dT%H:%M:%SZ")
        return [r for r in self.rows.values() if r.npm and not r.bulk and r.downloads_at < cutoff]

    async def count_downloads(self) -> None:
        """Fetches the last month's npm downloads of packages that have no recent count: all the unscoped ones, and
        the most recently updated of the scoped ones (see SCOPED_PER_RUN). A failure just leaves the rest for next
        time; this is a nicety, never a reason for the catalog not to work."""
        todo = self._uncounted()
        if not todo:
            return
        self.counting = True
        self._counted_at = time.monotonic()
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            unscoped = [r for r in todo if not r.npm.startswith("@")]
            failures = 0
            for i in range(0, len(unscoped), DOWNLOAD_BATCH):
                batch = unscoped[i : i + DOWNLOAD_BATCH]
                names = [r.npm for r in batch]
                try:
                    body = await mcp_registry.fetch_json(NPM_DOWNLOADS_URL + ",".join(names), who="npm")
                except RegistryUnavailable:
                    failures += 1
                    if failures > 3:
                        return
                    continue
                for r in batch:
                    # one name is answered as that package's own figures, several as {name: figures}
                    figures = body if len(names) == 1 else (body or {}).get(r.npm)
                    r.downloads = (figures or {}).get("downloads") if isinstance(figures, dict) else None
                    r.downloads_at = now
            scoped = sorted((r for r in todo if r.npm.startswith("@")), key=lambda r: r.updated, reverse=True)
            for r in scoped[:SCOPED_PER_RUN]:
                try:
                    body = await mcp_registry.fetch_json(
                        NPM_DOWNLOADS_URL + quote(r.npm, safe="@/"), who="npm"
                    )
                except RegistryUnavailable:
                    return  # npm is asking for a rest: the others are counted another time
                r.downloads = body.get("downloads") if isinstance(body, dict) else None
                r.downloads_at = now
                await asyncio.sleep(SCOPED_DELAY)
        finally:
            self.counting = False
            await asyncio.to_thread(self._write)

    # -- browsing --

    def browse(
        self,
        *,
        q: str = "",
        category: str = "",
        sort: str = "recommended",
        supported_only: bool = False,
        offset: int = 0,
        limit: int = 30,
        available: frozenset[str] | None = None,
        featured: frozenset[str] = frozenset(),
    ) -> Browse:
        if self._stamp() != self._categories_stamp:  # the categories file was edited
            self._derive(self.rows)
        tokens = [t for t in q.lower().split() if t][:6]
        matches: list[tuple[Row, Way]] = []
        for row in self.rows.values():
            if tokens and not all(t in row.hay for t in tokens):
                continue
            way = pick_way(row.ways, available)
            if supported_only and way.reason:
                continue
            matches.append((row, way))
        counts = Counter(row.category for row, _ in matches)
        if category:
            matches = [(r, w) for r, w in matches if r.category == category]
        now = datetime.now(UTC)
        if sort == "downloads":
            matches.sort(key=lambda m: (m[0].downloads is None, -(m[0].downloads or 0), m[0].name))
        elif sort == "updated":
            matches.sort(key=lambda m: m[0].name)
            matches.sort(key=lambda m: m[0].updated, reverse=True)  # stable: equal times stay by name
        elif sort == "name":
            matches.sort(key=lambda m: m[0].display.lower())
        else:

            def rank(m: tuple[Row, Way]) -> tuple[float, str]:
                row, _ = m
                score = _score(row, available, now)
                if row.name in featured:
                    score += 1000
                score += 200 * sum(1 for t in tokens if t in row.name_hay)  # what you typed is in its name
                if row.vendor and row.vendor in tokens:
                    score += 150  # what you typed is who published it, and they proved they own that domain
                return (-score, row.name)

            matches.sort(key=rank)
        labels = {c.id: c.label for c in self._categories} | {"other": "Other"}
        order = [c.id for c in self._categories] + ["other"]
        facets = [(c, labels[c], counts[c]) for c in order if counts.get(c)]
        return Browse(rows=matches[offset : offset + limit], total=len(matches), categories=facets)

    @staticmethod
    def as_tool(row: Row, way: Way, note: str = "") -> RegistryTool:
        return RegistryTool(
            name=row.name,
            title=row.display or display_title(row.name, row.title),
            description=row.description,
            version=row.version,
            repository=row.repository,
            source=way.source,
            runs=way.runs,
            command=way.command,
            supported=not way.reason,
            reason=way.reason,
            reason_text=reason_text(way.reason, way.command),
            note=note,
            icon=icon_url(row),
            category=row.category,
            downloads=row.downloads,
            updated=row.updated,
        )

    def reset(self) -> None:
        """Forgets everything held in memory (for tests; the file is left alone)."""
        if self.task:
            with contextlib.suppress(Exception):
                self.task.cancel()
        self.__dict__.update(Catalog().__dict__)


catalog = Catalog()
