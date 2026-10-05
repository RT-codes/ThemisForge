import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app import db

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    monkeypatch.setattr(db, "engine", engine)
    app.dependency_overrides[db.get_session] = _override(async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def _override(maker):
    async def get_session():
        async with maker() as s:
            yield s

    return get_session


async def test_register_login_me_logout(client):
    r = await client.post(
        "/api/auth/register", json={"email": "A@b.co", "name": "Ada", "password": "password123"}
    )
    assert r.status_code == 201 and r.json()["email"] == "a@b.co"
    assert (await client.get("/api/auth/me")).json()["name"] == "Ada"

    await client.post("/api/auth/logout")
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post("/api/auth/login", json={"email": "a@b.co", "password": "wrong-pass"})
    assert bad.status_code == 401
    ok = await client.post("/api/auth/login", json={"email": "a@b.co", "password": "password123"})
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_duplicate_register(client):
    body = {"email": "a@b.co", "name": "Ada", "password": "password123"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 201
    assert (await client.post("/api/auth/register", json=body)).status_code == 409
