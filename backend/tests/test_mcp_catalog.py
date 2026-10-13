"""The local copy of the MCP registry's catalog (app/mcp_catalog.py) and the browse routes on top of it.

The registry is replaced by FakeRegistry (see test_mcp_registry.py): nothing here touches the network.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app import mcp_catalog, mcp_registry
from app.mcp_catalog import Row, catalog, icon_url, make_row
from app.mcp_registry import RegistryUnavailable
from tests.conftest import login, make_project, register
from tests.registry_fakes import entry, item

pytestmark = pytest.mark.usefixtures("fresh_caches")

NOW = datetime.now(UTC)


def when(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def npm(identifier: str) -> dict:
    return {
        "registryType": "npm",
        "identifier": identifier,
        "version": "1.0.0",
        "transport": {"type": "stdio"},
    }


REMOTE = {"type": "streamable-http", "url": "https://x.example/mcp"}
OCI = {
    "registryType": "oci",
    "identifier": "ghcr.io/x/y:1",
    "version": "1",
    "transport": {"type": "stdio"},
}


def tool(name, description="", *, packages=None, remotes=None, title="", repo="", icons=None, **meta) -> dict:
    server = {"name": name, "description": description, "version": "1.0.0", "title": title}
    if packages:
        server["packages"] = packages
    if remotes:
        server["remotes"] = remotes
    if repo:
        server["repository"] = {"url": repo, "source": "github"}
    if icons:
        server["icons"] = icons
    return item(server, **meta)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(mcp_catalog, "SCOPED_DELAY", 0)


@pytest.fixture
def small_pages(monkeypatch):
    monkeypatch.setattr(mcp_catalog, "PAGE", 2)


# ----- reading the registry -----


async def test_a_full_sync_reads_every_page_and_skips_what_is_not_active(registry, small_pages):
    registry.listing = [
        tool("a.b/one", remotes=[REMOTE]),
        tool("a.b/two", packages=[npm("two-mcp")]),
        tool("a.b/three", remotes=[REMOTE]),
        tool("a.b/old", remotes=[REMOTE], status="deprecated"),
        tool("a.b/five", remotes=[REMOTE]),
    ]
    await catalog.sync(full=True)
    assert sorted(catalog.rows) == ["a.b/five", "a.b/one", "a.b/three", "a.b/two"]
    assert catalog.state == "ready" and catalog.synced_at
    pages = [p for _, p in registry.asked if p and "limit" in p]
    assert len(pages) == 3 and pages[0].get("updated_since") is None and pages[0]["version"] == "latest"


async def test_the_catalog_is_kept_in_a_file_and_read_back(registry):
    registry.listing = [tool("a.b/one", "Does things", remotes=[REMOTE], repo="https://github.com/a/one")]
    await catalog.sync(full=True)
    assert mcp_catalog.Catalog.path().is_file()
    catalog.reset()
    await catalog.load()
    row = catalog.rows["a.b/one"]
    assert (row.description, row.repository) == ("Does things", "https://github.com/a/one")
    assert row.ways and catalog.state == "ready" and catalog.synced_at


async def test_a_file_that_cannot_be_used_is_the_same_as_no_file(registry):
    path = mcp_catalog.Catalog.path()
    path.parent.mkdir(parents=True)
    path.write_text('{"format": 999, "rows": []}', encoding="utf-8")
    await catalog.load()
    assert catalog.rows == {} and catalog.state == "empty"
    catalog.reset()
    path.write_text("not json at all", encoding="utf-8")
    await catalog.load()
    assert catalog.rows == {}


async def test_an_update_asks_only_for_what_changed_and_applies_it(registry):
    registry.listing = [
        tool("a.b/keep", "Stays", remotes=[REMOTE], updated=when(30)),
        tool("a.b/change", "Before", remotes=[REMOTE], updated=when(30)),
        tool("a.b/vanish", "Will go", remotes=[REMOTE], updated=when(30)),
    ]
    await catalog.sync(full=True)
    catalog.rows["a.b/change"].npm = ""  # (so the count below is about the update, not about npm)
    registry.asked.clear()
    registry.listing = [
        tool("a.b/keep", "Stays", remotes=[REMOTE], updated=when(30)),
        tool("a.b/change", "After", remotes=[REMOTE], updated=when(0)),
        tool("a.b/vanish", "Will go", remotes=[REMOTE], status="deprecated", updated=when(0)),
        tool("a.b/new", "Fresh", remotes=[REMOTE], updated=when(0)),
    ]
    await catalog.sync(full=False)
    since = [p["updated_since"] for _, p in registry.asked if p and "updated_since" in p]
    assert len(since) == 1 and since[0] < catalog.synced_at  # starts a little before the last sync did
    assert sorted(catalog.rows) == ["a.b/change", "a.b/keep", "a.b/new"]
    assert catalog.rows["a.b/change"].description == "After"
    assert catalog.rows["a.b/keep"].description == "Stays"


async def test_a_failed_first_sync_is_an_error_that_is_retried_later_not_at_once(registry, monkeypatch):
    monkeypatch.setattr(mcp_catalog.asyncio, "sleep", lambda _s: _noop())
    registry.error = RegistryUnavailable("The MCP registry did not answer within 10 seconds.")
    await catalog.sync(full=True)
    assert catalog.state == "error" and "did not answer" in catalog.error and catalog.rows == {}
    await catalog.ensure_current()
    assert catalog.task is None  # it just failed: not again at once
    catalog.failed_at -= mcp_catalog.RETRY_AFTER + 1
    registry.error = None
    registry.listing = [tool("a.b/one", remotes=[REMOTE])]
    await catalog.ensure_current()
    await catalog.task
    assert catalog.state == "ready" and list(catalog.rows) == ["a.b/one"]


async def _noop():
    return None


async def test_a_failed_update_keeps_the_copy_it_has(registry, monkeypatch):
    monkeypatch.setattr(mcp_catalog.asyncio, "sleep", lambda _s: _noop())
    registry.listing = [tool("a.b/one", remotes=[REMOTE])]
    await catalog.sync(full=True)
    registry.error = RegistryUnavailable("down")
    await catalog.sync(full=False)
    assert catalog.state == "ready" and list(catalog.rows) == ["a.b/one"] and catalog.error == "down"


async def test_browsing_starts_the_first_build_in_the_background_and_a_stale_copy_is_updated(registry):
    registry.listing = [tool("a.b/one", remotes=[REMOTE])]
    await catalog.ensure_current()
    assert catalog.task is not None
    await catalog.task
    assert list(catalog.rows) == ["a.b/one"]
    catalog.task = None
    await catalog.ensure_current()
    assert catalog.task is None  # fresh: nothing to do
    catalog.synced_at = when(2)
    await catalog.ensure_current()
    assert catalog.task is not None
    await catalog.task


# ----- looking things up -----


def many(registry):
    registry.listing = [
        tool(
            "com.notion/mcp",
            "Official Notion tools for pages and databases",
            remotes=[REMOTE],
            title="Notion",
        ),
        tool("io.github.a/slack-mcp", "Read and post Slack messages", packages=[npm("slack-mcp")]),
        tool("io.github.b/pg", "Query a PostgreSQL database", packages=[npm("pg-mcp")]),
        tool("io.github.c/sheet", "Works with a notion export", packages=[npm("sheet-mcp")]),
        tool("io.github.d/imagey", "Resize and edit images", remotes=[REMOTE]),
        tool("io.github.e/boxed", "Container only thing", packages=[OCI]),
    ]


async def test_a_search_needs_every_word_and_finds_names_and_descriptions(registry):
    many(registry)
    await catalog.sync(full=True)
    names = lambda page: [r.name for r, _ in page.rows]
    assert set(names(catalog.browse(q="notion"))) == {"com.notion/mcp", "io.github.c/sheet"}
    assert names(catalog.browse(q="SLACK"))[0] == "io.github.a/slack-mcp"
    assert names(catalog.browse(q="notion export")) == ["io.github.c/sheet"]
    assert catalog.browse(q="nothing like this").total == 0
    # what you typed being in the name puts it first
    assert names(catalog.browse(q="notion"))[0] == "com.notion/mcp"


async def test_tools_land_in_categories_with_counts_for_the_current_search(registry):
    many(registry)
    await catalog.sync(full=True)
    by_name = {r.name: r.category for r in catalog.rows.values()}
    assert by_name["com.notion/mcp"] == "productivity"
    assert by_name["io.github.a/slack-mcp"] == "comms"
    assert by_name["io.github.b/pg"] == "data"
    assert by_name["io.github.d/imagey"] == "media"
    assert by_name["io.github.e/boxed"] == "other"
    page = catalog.browse()
    counts = {i: n for i, _, n in page.categories}
    assert counts["comms"] == 1 and counts["other"] == 1 and sum(counts.values()) == page.total == 6
    only = catalog.browse(category="data")
    assert [r.name for r, _ in only.rows] == ["io.github.b/pg"]
    assert {i for i, _, _ in only.categories} == set(counts)  # the chips do not vanish when one is chosen
    assert [label for i, label, _ in page.categories if i == "data"] == ["Databases and data"]


async def test_editing_the_categories_file_takes_effect_without_a_restart(registry, tmp_path, monkeypatch):
    many(registry)
    file = tmp_path / "categories.yaml"
    file.write_text(
        "categories:\n  - id: chatty\n    label: Chatty\n    keywords: [slack]\n", encoding="utf-8"
    )
    monkeypatch.setattr(mcp_catalog, "CATEGORIES_FILE", file)
    await catalog.sync(full=True)
    assert catalog.rows["io.github.a/slack-mcp"].category == "chatty"
    assert catalog.rows["com.notion/mcp"].category == "other"
    file.write_text("categories:\n  - id: wiki\n    label: Wiki\n    keywords: [notion]\n", encoding="utf-8")
    import os

    os.utime(file, (NOW.timestamp() + 5, NOW.timestamp() + 5))
    page = catalog.browse()
    assert catalog.rows["com.notion/mcp"].category == "wiki"
    assert ("wiki", "Wiki", 2) in page.categories


async def test_a_broken_categories_file_leaves_everything_in_other(registry, tmp_path, monkeypatch):
    many(registry)
    file = tmp_path / "categories.yaml"
    file.write_text("categories: [unclosed", encoding="utf-8")
    monkeypatch.setattr(mcp_catalog, "CATEGORIES_FILE", file)
    await catalog.sync(full=True)
    assert {r.category for r in catalog.rows.values()} == {"other"}


async def test_sorting_by_name_by_update_and_by_downloads(registry):
    registry.listing = [
        tool("a.b/b", title="Bravo", remotes=[REMOTE], updated=when(40)),
        tool("a.b/a", title="Alpha", packages=[npm("alpha-mcp")], updated=when(400)),
        tool("a.b/c", title="Charlie", packages=[npm("charlie-mcp")], updated=when(3)),
    ]
    registry.downloads = {"alpha-mcp": 50, "charlie-mcp": 9000}
    await catalog.sync(full=True)
    order = lambda sort: [r.title for r, _ in catalog.browse(sort=sort).rows]
    assert order("name") == ["Alpha", "Bravo", "Charlie"]
    assert order("updated") == ["Charlie", "Bravo", "Alpha"]
    assert order("downloads") == ["Charlie", "Alpha", "Bravo"]  # what has no count comes last


async def test_recommended_puts_featured_first_and_ranks_runnable_real_looking_tools_up(registry):
    registry.listing = [
        tool(
            "com.vendor/real",
            "A proper description of what this tool does for you",
            remotes=[REMOTE],
            repo="https://github.com/vendor/real",
            updated=when(5),
        ),
        tool("io.github.bulk/x", "x", remotes=[REMOTE], updated=when(5)),
        tool(
            "io.github.z/boxed",
            "A proper description of what this tool does for you",
            packages=[OCI],
            updated=when(5),
        ),
        tool("io.github.me/favourite", "x", remotes=[REMOTE], updated=when(900)),
    ]
    # many tools from one publisher: bulk-publishing, ranked below the rest
    registry.listing += [
        tool(f"io.github.bulk/t{i}", "x", remotes=[REMOTE], updated=when(5)) for i in range(70)
    ]
    await catalog.sync(full=True)
    names = [r.name for r, _ in catalog.browse().rows]
    assert names[0] == "com.vendor/real"
    assert names.index("io.github.z/boxed") > names.index("com.vendor/real")
    featured = [r.name for r, _ in catalog.browse(featured=frozenset({"io.github.me/favourite"})).rows]
    assert featured[0] == "io.github.me/favourite"
    full = [r.name for r, _ in catalog.browse(limit=1000).rows]
    assert full[-1].startswith("io.github.bulk/") or full.index("io.github.bulk/x") > full.index(
        "io.github.z/boxed"
    )


async def test_what_the_image_cannot_start_is_filtered_or_marked_per_request(registry):
    many(registry)
    await catalog.sync(full=True)
    everything = catalog.browse(available=frozenset({"npx", "uvx"}))
    assert {w.reason for _, w in everything.rows} == {"", "container"}
    runnable = catalog.browse(supported_only=True, available=frozenset({"npx", "uvx"}))
    assert runnable.total == 5 and all(not w.reason for _, w in runnable.rows)
    no_npx = catalog.browse(available=frozenset({"uvx"}))
    reasons = {r.name: w.reason for r, w in no_npx.rows}
    assert reasons["io.github.a/slack-mcp"] == "image_command"
    assert reasons["com.notion/mcp"] == ""  # a hosted address needs nothing from the image


async def test_paging_goes_through_all_matches(registry):
    registry.listing = [tool(f"a.b/t{i:02}", remotes=[REMOTE]) for i in range(7)]
    await catalog.sync(full=True)
    first = catalog.browse(sort="name", limit=3)
    second = catalog.browse(sort="name", limit=3, offset=3)
    last = catalog.browse(sort="name", limit=3, offset=6)
    assert first.total == 7
    assert [r.name for r, _ in first.rows + second.rows + last.rows] == [f"a.b/t{i:02}" for i in range(7)]


# ----- icons -----


def row(**kw) -> Row:
    base = {
        "name": "io.github.owner/x",
        "title": "",
        "description": "",
        "version": "1",
        "repository": "",
        "icon": "",
        "updated": "",
        "ways": [],
    }
    return Row(**{**base, **kw})


def test_an_icon_is_the_one_declared_else_the_owners_github_avatar_else_nothing():
    assert icon_url(row(icon="https://cdn.example/logo.png")) == "https://cdn.example/logo.png"
    assert icon_url(row()) == "https://github.com/owner.png?size=80"  # from io.github.<owner>/
    assert icon_url(row(name="com.vendor/x", repository="https://github.com/vendorco/thing")) == (
        "https://github.com/vendorco.png?size=80"
    )
    assert icon_url(row(name="com.vendor/x")) == ""
    assert icon_url(row(name="com.vendor/x", repository="https://gitlab.com/a/b")) == ""


def test_only_secure_images_of_a_known_kind_are_taken_as_declared_icons():
    def declared(*icons):
        made = make_row(tool("a.b/x", icons=list(icons)))
        return made.icon if made else None

    assert declared({"src": "http://insecure.example/i.png"}) == ""
    assert declared({"src": "https://x.example/i.html", "mimeType": "text/html"}) == ""
    assert declared({"src": "javascript:alert(1)"}) == ""
    assert declared({"src": "http://a/i.png"}, {"src": "https://b/i.svg", "mimeType": "image/svg+xml"}) == (
        "https://b/i.svg"
    )


# ----- npm download counts -----


async def test_downloads_are_counted_once_for_each_npm_package_and_not_again_within_a_week(registry):
    registry.listing = [
        tool("a.b/plain", packages=[npm("plain-mcp")]),
        tool("a.b/scoped", packages=[npm("@scope/pkg")]),
        tool("a.b/hosted", remotes=[REMOTE]),
        tool("a.b/gone", packages=[npm("not-on-npm-mcp")]),
    ]
    registry.downloads = {"plain-mcp": 1200, "@scope/pkg": 30_000_000}
    await catalog.sync(full=True)
    assert catalog.rows["a.b/plain"].downloads == 1200
    assert catalog.rows["a.b/scoped"].downloads == 30_000_000
    assert catalog.rows["a.b/hosted"].downloads is None
    assert catalog.rows["a.b/gone"].downloads is None and catalog.rows["a.b/gone"].downloads_at
    asked = [u for u, _ in registry.asked if u.startswith(mcp_catalog.NPM_DOWNLOADS_URL)]
    assert any("plain-mcp" in u and "," in u for u in asked)  # unscoped ones go in one request
    assert any("%2F" not in u and "@scope/pkg" in u for u in asked)  # a scoped one is asked alone
    registry.asked.clear()
    await catalog.count_downloads()
    assert registry.asked == []  # counted this week already


async def test_scoped_packages_are_counted_slowly_newest_first_and_stop_when_npm_asks_for_a_rest(
    registry, monkeypatch
):
    monkeypatch.setattr(mcp_catalog, "SCOPED_PER_RUN", 2)
    registry.listing = [
        tool(f"a.b/s{i}", packages=[npm(f"@s/p{i}")], updated=when(i)) for i in range(5)
    ]  # s0 is the newest
    registry.downloads = {f"@s/p{i}": 100 + i for i in range(5)}
    await catalog.sync(full=True)
    counted = {n: r.downloads for n, r in catalog.rows.items() if r.downloads_at}
    assert counted == {"a.b/s0": 100, "a.b/s1": 101}  # a limited number, newest first
    # a later run goes on with the next ones
    catalog._counted_at = -1e9
    await catalog.count_downloads()
    assert {n for n, r in catalog.rows.items() if r.downloads_at} == {"a.b/s0", "a.b/s1", "a.b/s2", "a.b/s3"}
    # npm asking for a rest stops the run at once and keeps what it had
    registry.npm_error = RegistryUnavailable("npm answered with HTTP 429.")
    await catalog.count_downloads()
    assert {n for n, r in catalog.rows.items() if r.downloads_at} == {"a.b/s0", "a.b/s1", "a.b/s2", "a.b/s3"}


async def test_browsing_goes_on_counting_what_is_left_at_most_once_an_hour(registry, monkeypatch):
    monkeypatch.setattr(mcp_catalog, "SCOPED_PER_RUN", 1)
    registry.listing = [tool(f"a.b/s{i}", packages=[npm(f"@s/p{i}")], updated=when(i)) for i in range(3)]
    registry.downloads = {f"@s/p{i}": 10 for i in range(3)}
    await catalog.sync(full=True)
    assert sum(1 for r in catalog.rows.values() if r.downloads_at) == 1
    await catalog.ensure_current()
    assert catalog.task is None or catalog.task.done()  # asked a moment ago: not again yet
    catalog._counted_at -= mcp_catalog.DOWNLOADS_RETRY.total_seconds() + 1
    await catalog.ensure_current()
    await catalog.task
    assert sum(1 for r in catalog.rows.values() if r.downloads_at) == 2


async def test_an_npm_outage_does_not_break_the_catalog(registry):
    registry.listing = [tool("a.b/plain", packages=[npm("plain-mcp")])]
    registry.npm_error = RegistryUnavailable("npm could not be reached")
    await catalog.sync(full=True)
    assert catalog.state == "ready" and catalog.rows["a.b/plain"].downloads is None
    assert catalog.rows["a.b/plain"].downloads_at == ""  # so it is tried again next time
    assert not catalog.counting


async def test_an_update_does_not_forget_the_download_count(registry):
    registry.listing = [tool("a.b/plain", packages=[npm("plain-mcp")], updated=when(30))]
    registry.downloads = {"plain-mcp": 77}
    await catalog.sync(full=True)
    registry.listing = [tool("a.b/plain", "Now with words", packages=[npm("plain-mcp")], updated=when(0))]
    registry.downloads = {}
    await catalog.sync(full=False)
    assert catalog.rows["a.b/plain"].description == "Now with words"
    assert catalog.rows["a.b/plain"].downloads == 77


# ----- the routes -----


async def test_the_first_browse_builds_the_catalog_and_says_so(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    many(registry)
    first = (await client.get(f"/api/projects/{pid}/mcp-registry")).json()
    assert first["status"]["state"] in ("building", "ready")
    await catalog.task
    page = (await client.get(f"/api/projects/{pid}/mcp-registry", params={"sort": "name"})).json()
    assert page["status"]["state"] == "ready" and page["total"] == 6
    titles = [t["title"] for t in page["tools"]]
    assert len(titles) == 6 and titles == sorted(titles, key=str.lower)  # sorted by name, as asked
    assert {c["id"] for c in page["categories"]} >= {"comms", "data"}


async def test_the_browse_route_filters_sorts_and_shows_why_a_tool_is_greyed_out(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    many(registry)
    await client.get(f"/api/projects/{pid}/mcp-registry")
    await catalog.task
    slack = (await client.get(f"/api/projects/{pid}/mcp-registry", params={"q": "slack"})).json()
    (tool_,) = slack["tools"]
    assert tool_["name"] == "io.github.a/slack-mcp" and tool_["supported"]
    assert tool_["category"] == "comms" and tool_["icon"].startswith("https://github.com/a.png")
    boxed = (await client.get(f"/api/projects/{pid}/mcp-registry", params={"q": "container only"})).json()
    (grey,) = boxed["tools"]
    assert not grey["supported"] and grey["reason"] == "container" and grey["reason_text"]
    only = (await client.get(f"/api/projects/{pid}/mcp-registry", params={"supported_only": "true"})).json()
    assert only["total"] == 5
    bad = (
        await client.get(f"/api/projects/{pid}/mcp-registry", params={"sort": "nonsense", "limit": 999})
    ).json()
    assert len(bad["tools"]) == 6  # an unknown sort is the default one, and a huge page is cut to a sane size


async def test_a_tool_the_image_cannot_start_is_greyed_out_with_the_reason(client, registry, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]

    async def only_uvx(image, commands, docker_host=""):
        return {"npx": False, "uvx": True}

    monkeypatch.setattr(mcp_registry, "commands_in_image", only_uvx)
    registry.listing = [tool("a.b/npmtool", "x", packages=[npm("npm-mcp")])]
    await client.get(f"/api/projects/{pid}/mcp-registry")
    await catalog.task
    (t,) = (await client.get(f"/api/projects/{pid}/mcp-registry")).json()["tools"]
    assert (t["supported"], t["reason"]) == (False, "image_command")


async def test_one_tool_comes_with_what_it_needs_and_its_icon(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    registry.entries["io.github.microsoft/playwright-mcp"] = entry("playwright")
    registry.entries["a.b/needs-arg"] = entry("npm_required_arg")
    r = await client.get(f"/api/projects/{pid}/mcp-registry/entry", params={"name": "a.b/needs-arg"})
    assert r.status_code == 200, r.text
    tool_ = r.json()
    assert tool_["supported"] and [i for i in tool_["inputs"] if i["required"]]
    assert (
        await client.get(f"/api/projects/{pid}/mcp-registry/entry", params={"name": "a.b/none"})
    ).status_code == 404


async def test_a_refresh_reads_what_changed_now(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    registry.listing = [tool("a.b/one", remotes=[REMOTE], updated=when(30))]
    await client.get(f"/api/projects/{pid}/mcp-registry")
    await catalog.task
    registry.listing.append(tool("a.b/two", remotes=[REMOTE], updated=when(0)))
    r = await client.post(f"/api/projects/{pid}/mcp-registry/refresh")
    assert r.status_code == 200 and r.json()["state"] in ("updating", "ready")
    await catalog.task
    assert sorted(catalog.rows) == ["a.b/one", "a.b/two"]


async def test_only_an_administrator_can_use_the_new_routes(client, registry):
    await register(client)
    await register(client, "c@d.co", "Bob")
    pid = (await make_project(client, "Bobs"))["id"]
    assert (await client.post(f"/api/projects/{pid}/mcp-registry/refresh")).status_code == 403
    r = await client.get(f"/api/projects/{pid}/mcp-registry/entry", params={"name": "a.b/c"})
    assert r.status_code == 403
    assert registry.asked == []


def test_the_shipped_categories_are_valid():
    categories = mcp_catalog._load_categories()
    assert len(categories) >= 5
    assert len({c.id for c in categories}) == len(categories) and "other" not in {c.id for c in categories}
    assert all(c.words or c.phrases for c in categories)
    assert json.dumps([c.label for c in categories])


async def test_the_registry_can_be_browsed_from_settings_where_there_is_no_project(
    client, registry, monkeypatch
):
    await register(client)
    seen = []

    async def only_uvx(image, commands, docker_host=""):
        seen.append(image)
        return {"npx": False, "uvx": True}

    monkeypatch.setattr(mcp_registry, "commands_in_image", only_uvx)
    many(registry)
    registry.entries["a.b/needs-arg"] = entry("npm_required_arg")
    registry.entries["io.github.microsoft/playwright-mcp"] = entry("playwright")
    first = await client.get("/api/mcp-registry")
    assert first.status_code == 200, first.text
    await catalog.task
    page = (await client.get("/api/mcp-registry", params={"q": "slack"})).json()
    (slack,) = page["tools"]
    assert slack["name"] == "io.github.a/slack-mcp"
    assert (slack["supported"], slack["reason"]) == (False, "image_command")  # judged by the default image
    assert seen and all(image == seen[0] for image in seen)
    entry_ = await client.get("/api/mcp-registry/entry", params={"name": "a.b/needs-arg"})
    assert entry_.status_code == 200 and entry_.json()["reason"] == "image_command"  # npx is missing here too
    refreshed = await client.post("/api/mcp-registry/refresh")
    assert refreshed.status_code == 200
    await catalog.task
    r = await client.post("/api/mcp-registry/prefill", json={"name": "a.b/needs-arg", "values": {}})
    assert r.status_code == 422 and "npx" in r.json()["detail"]  # reached the same checks as a project's


async def test_the_registry_outside_a_project_is_for_administrators_and_ignores_other_peoples_projects(
    client, registry
):
    await register(client)
    others = (await make_project(client, "Admins"))["id"]
    await register(client, "c@d.co", "Bob")
    assert (await client.get("/api/mcp-registry")).status_code == 403
    assert (await client.get("/api/mcp-registry/featured")).status_code == 403
    assert (await client.post("/api/mcp-registry/prefill", json={"name": "a.b/c"})).status_code == 403
    await login(client, "a@b.co")
    # a project that is not yours is not found, whichever way it is named
    assert (await client.get("/api/mcp-registry", params={"project_id": others + 99})).status_code == 404
