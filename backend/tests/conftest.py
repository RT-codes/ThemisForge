import asyncio

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.features.connections.service as connections
from app.config import DEFAULT_SECRET_KEY, settings
from app.execution.cells.fake import FakeCellManager
from app.execution.scheduler import Scheduler
from app.features.tools.auth import McpLogins
from app.features.workflows.runner import WorkflowRunner
from app.main import app
from app.persistence import db

# shared test doubles for the MCP registry (fixtures: registry, fresh_caches)
pytest_plugins = ["tests.registry_fakes"]


@pytest.fixture(autouse=True)
def default_secret_key(monkeypatch):
    """Tests must not depend on whether this machine has a backend/.env with a real key."""
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)


@pytest.fixture(autouse=True)
def no_start_cooldown(monkeypatch):
    """Tests tick right after creating a task; the cooldown has its own test."""
    import app.features.system.settings as app_settings

    monkeypatch.setattr(app_settings, "DEFAULT_START_COOLDOWN_SECONDS", 0)


@pytest.fixture(autouse=True)
def fresh_codex_locks():
    """A login gate that was contended in one test holds futures bound to that test's event loop, so the next test must not reuse it."""
    import asyncio

    import app.features.project_config.store as project_config
    from app.features.connections import codex

    codex._gates.clear()
    project_config.lock = asyncio.Lock()
    yield
    codex._gates.clear()


@pytest.fixture
async def maker(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    # Notifications run after attempts finish and use their own sessions. Finish
    # those reads/writes before disposing this test's database and event loop.
    from app.features.notifications.delivery import pending

    while pending:
        await asyncio.gather(*pending, return_exceptions=True)
    await engine.dispose()


@pytest.fixture
def cells():
    return FakeCellManager(duration=0)


@pytest.fixture
async def scheduler(maker, cells):
    """A scheduler that is driven by hand with tick(); the background loop is not started."""
    sched = Scheduler(maker, cells)
    sched.mcp_logins = McpLogins(maker)
    app.state.scheduler = sched
    app.state.mcp_logins = sched.mcp_logins
    yield sched
    # Admission/error policy tests also install entries with no real task.
    for attempt_id, live in list(sched.runs.live.items()):
        if live.task is None:
            del sched.runs.live[attempt_id]
    await sched.stop()


@pytest.fixture
async def client(maker, scheduler):
    async def get_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[db.get_session] = get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def runner(maker, scheduler):
    """The workflow engine, with a background pump standing in for the scheduler loop."""
    r = WorkflowRunner(maker, lambda: app.state.scheduler)
    r.POLL_SECONDS = 0.02
    app.state.workflows = r
    scheduler.workflows = r

    async def pump():
        while True:
            await scheduler.tick()
            await asyncio.sleep(0.02)

    pumper = asyncio.create_task(pump())
    yield r
    pumper.cancel()
    await asyncio.gather(pumper, return_exceptions=True)
    await r.shutdown()


async def drain(scheduler: Scheduler) -> None:
    """Wait until every running cell has finished and been recorded."""
    while scheduler.runs.live:
        await asyncio.gather(
            *(live.task for live in list(scheduler.runs.live.values())), return_exceptions=True
        )
        await asyncio.sleep(0)


async def register(client: AsyncClient, email: str = "a@b.co", name: str = "Ada") -> dict:
    """Sign up and end up logged in as that user. The first user becomes the administrator; every
    later one joins through an invite created by the administrator who is currently logged in."""
    if (await client.get("/api/auth/setup")).json()["needs_admin"]:
        r = await client.post(
            "/api/auth/register", json={"email": email, "name": name, "password": "password123"}
        )
    else:
        invite = await client.post("/api/invites", json={"email": email})
        assert invite.status_code == 201, invite.text
        client.cookies.clear()
        r = await client.post(
            f"/api/invites/by-token/{invite.json()['token']}/accept",
            json={"name": name, "password": "password123"},
        )
    assert r.status_code == 201, r.text
    return r.json()


async def login(client: AsyncClient, email: str) -> None:
    client.cookies.clear()
    r = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text


async def make_project(client: AsyncClient, name: str = "Alpha") -> dict:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def make_task(client: AsyncClient, project_id: int, **body) -> dict:
    body.setdefault("title", "Do the thing")
    r = await client.post(f"/api/projects/{project_id}/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(autouse=True)
def fresh_webhook_limits():
    """The per-minute count of messages is kept in memory; every test starts a new minute."""
    import app.features.webhooks.receiver as webhooks

    webhooks._hits.clear()


@pytest.fixture(autouse=True)
def fresh_notification_repeats():
    """A message is not sent twice for the same thing within minutes; every test starts a new window."""
    import app.features.notifications.delivery as notifications

    notifications._recent.clear()


SUBSCRIPTION = "sk-ant-oat01-subscription-token-0123456789"
API_KEY = "sk-ant-api03-key-0123456789"


@pytest.fixture
def anthropic(monkeypatch):
    """Stands in for api.anthropic.com (only API_KEY is accepted) and gives the app a real secret key, so a Claude
    connection can be stored."""

    def handle(request: httpx.Request) -> httpx.Response:
        ok = request.url.path == "/v1/models" and request.headers.get("x-api-key") == API_KEY
        return httpx.Response(200, json={"data": []}) if ok else httpx.Response(401)

    monkeypatch.setattr(
        connections, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-tests-0123456789")
