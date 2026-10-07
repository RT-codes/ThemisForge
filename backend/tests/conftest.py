import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import db
from app.cells import FakeCellManager
from app.config import DEFAULT_SECRET_KEY, settings
from app.main import app
from app.scheduler import Scheduler


@pytest.fixture(autouse=True)
def default_secret_key(monkeypatch):
    """Tests must not depend on whether this machine has a backend/.env with a real key."""
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)


@pytest.fixture(autouse=True)
def fresh_codex_locks():
    """A lock that was contended in one test is bound to that test's event loop, so the next test must not reuse it."""
    import asyncio

    from app import codex, project_config

    codex._locks.clear()
    project_config.lock = asyncio.Lock()
    yield
    codex._locks.clear()


@pytest.fixture
async def maker(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def cells():
    return FakeCellManager(duration=0)


@pytest.fixture
def scheduler(maker, cells):
    """A scheduler that is driven by hand with tick(); the background loop is not started."""
    sched = Scheduler(maker, cells)
    app.state.scheduler = sched
    return sched


@pytest.fixture
async def client(maker, scheduler):
    async def get_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[db.get_session] = get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def drain(scheduler: Scheduler) -> None:
    """Wait until every running cell has finished and been recorded."""
    while scheduler._live:
        await asyncio.gather(*(live.task for live in list(scheduler._live.values())), return_exceptions=True)
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
