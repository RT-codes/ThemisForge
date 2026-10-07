"""Is there a newer Themis (app/updates.py): one plain GET a day, shown to administrators, never installed from here."""

import httpx
import pytest

from app import updates
from app.app_settings import AppSettings
from app.main import app
from app.version import BuildInfo
from tests.conftest import login, register


def gh(*tags, pre=(), draft=()):
    """GitHub's list of releases, newest first as it sends them."""
    out = []
    for tag in tags:
        out.append(
            {
                "tag_name": tag,
                "prerelease": tag in pre,
                "draft": tag in draft,
                "html_url": f"https://github.com/RT-codes/ThemisForge/releases/tag/{tag}",
                "published_at": "2026-10-01T00:00:00Z",
            }
        )
    return out


def network(answer, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(status, json=answer)

    return httpx.MockTransport(handler)


@pytest.fixture
def release_install(monkeypatch):
    """This install is a 0.1.1 release (a git checkout never has an update offered, see below)."""
    monkeypatch.setattr(
        updates, "build_info", lambda: BuildInfo("0.1.1", "0.1.1", "abc", "2026-10-01T00:00:00Z", "release")
    )


# ----- which release is the newest -----


def test_the_newest_release_of_the_channel_is_picked_and_junk_is_ignored():
    listing = gh(
        "v0.3.0-beta.1",
        "v0.2.0",
        "v0.2.1",
        "v0.1.0",
        "nightly",
        "v0.2.2",
        pre=("v0.3.0-beta.1",),
        draft=("v0.2.2",),
    )
    assert (
        updates.pick_latest(listing).version == "0.2.1"
    )  # stable: no pre-release, no draft, no tag that is not a version
    assert updates.pick_latest(listing, "beta").version == "0.3.0-beta.1"
    assert updates.pick_latest(gh("v1.0.0-rc.1"), "stable") is None
    assert updates.pick_latest(gh("v0.1.0")).url.endswith("/releases/tag/v0.1.0")
    for damaged in (None, {}, "oops", [None, 5, {"tag_name": 7}]):
        assert updates.pick_latest(damaged) is None


# ----- asking -----


async def test_a_newer_release_is_reported_with_where_to_read_about_it(release_install):
    seen = []
    checker = updates.UpdateChecker(network(gh("v0.2.0", "v0.1.1"), seen=seen))
    await checker.check(AppSettings())
    info = checker.info(AppSettings())
    assert (info.latest, info.available, info.current, info.error) == ("0.2.0", True, "0.1.1", "")
    assert (
        info.url.endswith("/releases/tag/v0.2.0") and info.checked_at.endswith("Z") and info.kind == "release"
    )
    (request,) = seen
    assert request.method == "GET" and request.url.path.endswith("/releases")
    # nothing about the user, the projects or the machine is sent: no cookie, no body, no identifier in the headers
    assert (
        request.content == b"" and "cookie" not in request.headers and "authorization" not in request.headers
    )
    assert request.headers["user-agent"] == "Themis/0.1.1"


async def test_being_up_to_date_or_ahead_offers_nothing(release_install):
    for tags in (["v0.1.1"], ["v0.1.0"], ["v0.1.1", "v0.1.0"]):
        checker = updates.UpdateChecker(network(gh(*tags)))
        await checker.check(AppSettings())
        assert checker.info(AppSettings()).available is False


async def test_a_pre_release_is_only_offered_on_the_beta_channel(release_install):
    listing = gh("v0.2.0-beta.1", "v0.1.1", pre=("v0.2.0-beta.1",))
    stable = updates.UpdateChecker(network(listing))
    await stable.check(AppSettings())
    assert stable.info(AppSettings()).available is False
    beta = updates.UpdateChecker(network(listing))
    await beta.check(AppSettings(update_channel="beta"))
    assert beta.info(AppSettings(update_channel="beta")).latest == "0.2.0-beta.1"


async def test_a_git_checkout_is_never_told_to_upgrade(monkeypatch):
    monkeypatch.setattr(
        updates, "build_info", lambda: BuildInfo("0.1.1+dev.abc", "0.1.1", "abc", "", "checkout")
    )
    checker = updates.UpdateChecker(network(gh("v9.9.9")))
    await checker.check(AppSettings())
    info = checker.info(AppSettings())
    assert info.latest == "9.9.9" and info.available is False  # its developer is not "behind" a release


async def test_switched_off_means_no_request_at_all(release_install):
    seen = []
    checker = updates.UpdateChecker(network(gh("v0.2.0"), seen=seen))
    off = AppSettings(check_for_updates=False)
    await checker.check(off, force=True)
    assert seen == [] and checker.info(off).available is False and checker.info(off).enabled is False


async def test_a_failure_is_an_error_message_not_a_crash_and_a_later_success_clears_it(release_install):
    for transport in (
        network({}, status=403),
        network({}, status=500),
        network(httpx.ConnectError("no route")),
        network(httpx.ReadTimeout("slow")),
    ):
        checker = updates.UpdateChecker(transport)
        await checker.check(AppSettings())
        info = checker.info(AppSettings())
        assert (
            info.error.startswith("Could not check for updates")
            and info.available is False
            and info.checked_at == ""
        )
    checker = updates.UpdateChecker(network({"not": "a list"}))
    await checker.check(AppSettings())
    assert (
        checker.info(AppSettings()).latest == "" and checker.info(AppSettings()).error == ""
    )  # answered, with nothing usable
    checker._transport = network(gh("v0.2.0"))
    await checker.check(AppSettings(), force=True)
    assert checker.info(AppSettings()).error == "" and checker.info(AppSettings()).latest == "0.2.0"


async def test_asking_again_within_seconds_reuses_the_answer_unless_forced(release_install):
    seen = []
    checker = updates.UpdateChecker(network(gh("v0.2.0"), seen=seen))
    await checker.check(AppSettings())
    await checker.check(AppSettings())
    assert len(seen) == 1
    await checker.check(AppSettings(), force=True)
    assert len(seen) == 2


# ----- what administrators see -----


async def test_only_administrators_see_the_update_and_can_ask_for_one(client, release_install):
    await register(client)  # the administrator
    app.state.updates = updates.UpdateChecker(network(gh("v0.2.0")))
    try:
        r = await client.post("/api/system/update-check")
        assert r.status_code == 200 and r.json()["available"] is True and r.json()["latest"] == "0.2.0"
        status = (await client.get("/api/system/status")).json()
        assert status["update"]["latest"] == "0.2.0" and status["update"]["current"] == "0.1.1"
        await register(client, "b@c.de", "Bob")  # an ordinary user
        assert (await client.get("/api/system/status")).json()["update"] is None
        assert (await client.post("/api/system/update-check")).status_code == 403
        await login(client, "a@b.co")
    finally:
        app.state.updates = updates.UpdateChecker()


async def test_the_switch_and_the_channel_are_kept_in_the_settings(client):
    await register(client)
    saved = (await client.get("/api/settings")).json()
    assert (
        saved["check_for_updates"] is True and saved["update_channel"] == "stable"
    )  # on by default, and the safe channel
    r = await client.put(
        "/api/settings", json={**saved, "check_for_updates": False, "update_channel": "beta"}
    )
    assert (
        r.status_code == 200
        and r.json()["check_for_updates"] is False
        and r.json()["update_channel"] == "beta"
    )
    assert (await client.put("/api/settings", json={**saved, "update_channel": "nightly"})).status_code == 422
