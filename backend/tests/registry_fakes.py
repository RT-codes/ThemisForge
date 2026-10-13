"""Test doubles for the MCP registry and its catalog (see test_mcp_registry.py and test_mcp_catalog.py).

tests/fixtures/mcp_registry_sample.json holds real entries captured from registry.modelcontextprotocol.io, one for each
shape that matters. The registry is replaced by FakeRegistry: nothing here talks to the network. The fixtures are
registered as a plugin in conftest.py; a test module opts into the isolation with
`pytestmark = pytest.mark.usefixtures("fresh_caches")`.
"""

import copy
import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from app import mcp_catalog, mcp_registry
from app.config import settings

SAMPLE = json.loads(
    (Path(__file__).parent / "fixtures" / "mcp_registry_sample.json").read_text(encoding="utf-8")
)


def entry(name: str) -> dict:
    return copy.deepcopy(SAMPLE[name])


@pytest.fixture
def fresh_caches(tmp_path, monkeypatch):
    # the catalog is a file under the data folder: never the real one
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    mcp_registry._cache.clear()
    mcp_registry._runner_cache.clear()
    mcp_catalog.catalog.reset()
    yield
    mcp_catalog.catalog.reset()


class FakeRegistry:
    """Answers registry and npm addresses from tables and remembers what was asked."""

    def __init__(self, monkeypatch):
        self.asked: list[tuple[str, dict | None]] = []
        self.listing: list[dict] = []  # items of the registry's listing
        self.entries: dict[str, dict] = {}  # single entries by name
        self.downloads: dict[str, int] = {}  # npm package -> last month's downloads
        self.error: Exception | None = None
        self.npm_error: Exception | None = None
        monkeypatch.setattr(mcp_registry, "fetch_json", self.fetch)

    async def fetch(self, url, params=None, who="The MCP registry"):
        self.asked.append((url, params))
        if url.startswith(mcp_catalog.NPM_DOWNLOADS_URL):
            if self.npm_error:
                raise self.npm_error
            names = unquote(url.removeprefix(mcp_catalog.NPM_DOWNLOADS_URL)).split(",")
            figures = {
                n: {"downloads": self.downloads[n], "package": n} for n in names if n in self.downloads
            }
            if len(names) == 1:
                return figures.get(names[0])
            return {n: figures.get(n) for n in names}
        if self.error:
            raise self.error
        if params is not None:  # the listing
            items = sorted(self.listing, key=lambda i: i["server"]["name"])
            since = params.get("updated_since")
            if since:
                items = [i for i in items if (meta_of(i).get("updatedAt") or "") >= since]
            start = int(params.get("cursor") or 0)
            size = int(params["limit"])
            end = start + size
            return {
                "servers": items[start:end],
                "metadata": {
                    "nextCursor": str(end) if end < len(items) else None,
                    "count": len(items[start:end]),
                },
            }
        name = url.split("/servers/")[1].split("/versions/")[0].replace("%2F", "/")
        found = self.entries.get(name)
        return {"server": found, "_meta": {}} if found else None


def meta_of(it: dict) -> dict:
    return (it.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}


@pytest.fixture
def registry(monkeypatch):
    return FakeRegistry(monkeypatch)


def item(server: dict, status: str = "active", updated: str = "2026-10-01T00:00:00Z") -> dict:
    meta = {"status": status, "updatedAt": updated, "publishedAt": updated}
    return {"server": server, "_meta": {"io.modelcontextprotocol.registry/official": meta}}
