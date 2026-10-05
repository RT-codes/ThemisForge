from datetime import timedelta

from sqlalchemy import select

from app.models import AccessRequest, Invite, utcnow
from tests.conftest import login, register

ASK = {"name": "Grace", "email": "Grace@Example.com", "reason": "I would like to collaborate on project X"}


async def test_request_then_approve_then_join(client):
    await register(client, "admin@b.co", "Admin")
    client.cookies.clear()

    assert (await client.post("/api/access-requests", json=ASK)).status_code == 201
    await login(client, "admin@b.co")
    pending = (await client.get("/api/access-requests")).json()
    assert (
        len(pending) == 1 and pending[0]["email"] == "grace@example.com" and pending[0]["status"] == "pending"
    )
    assert (await client.get("/api/system/status")).json()["pending_access_requests"] == 1

    invite = (await client.post(f"/api/access-requests/{pending[0]['id']}/approve")).json()
    assert invite["email"] == "grace@example.com" and invite["token"]
    assert (await client.get("/api/system/status")).json()["pending_access_requests"] == 0
    assert (await client.get("/api/access-requests")).json()[0]["status"] == "approved"
    assert len((await client.get("/api/invites")).json()) == 1

    client.cookies.clear()
    token = invite["token"]
    assert (await client.get(f"/api/invites/by-token/{token}")).json() == {"email": "grace@example.com"}
    joined = await client.post(
        f"/api/invites/by-token/{token}/accept", json={"name": "Grace", "password": "password123"}
    )
    assert joined.status_code == 201 and joined.json()["is_admin"] is False
    assert (await client.get("/api/auth/me")).json()["email"] == "grace@example.com"  # logged in right away

    # single use
    client.cookies.clear()
    assert (await client.get(f"/api/invites/by-token/{token}")).status_code == 404
    reuse = await client.post(
        f"/api/invites/by-token/{token}/accept", json={"name": "X", "password": "password123"}
    )
    assert reuse.status_code == 404


async def test_access_management_is_admin_only(client):
    await register(client, "admin@b.co", "Admin")
    await register(client, "bob@b.co", "Bob")  # a normal user
    for call in (
        client.get("/api/access-requests"),
        client.get("/api/invites"),
        client.post("/api/invites", json={"email": "x@y.co"}),
        client.post("/api/access-requests/1/approve"),
        client.post("/api/access-requests/1/deny"),
        client.delete("/api/invites/1"),
    ):
        assert (await call).status_code == 403
    assert (await client.get("/api/system/status")).json()["pending_access_requests"] == 0


async def test_request_form_does_not_reveal_accounts_or_flood(client, maker):
    await register(client, "admin@b.co", "Admin")
    client.cookies.clear()

    # an address that already has an account gets the same answer and nothing is stored
    exists = await client.post("/api/access-requests", json={**ASK, "email": "admin@b.co"})
    assert exists.status_code == 201 and exists.json() == {"status": "received"}
    # asking twice keeps one pending request
    await client.post("/api/access-requests", json=ASK)
    await client.post("/api/access-requests", json=ASK)
    async with maker() as s:
        assert len((await s.scalars(select(AccessRequest))).all()) == 1

    for bad in ({**ASK, "email": "nope"}, {**ASK, "reason": "   "}, {**ASK, "name": ""}):
        assert (await client.post("/api/access-requests", json=bad)).status_code == 422


async def test_deny(client):
    await register(client, "admin@b.co", "Admin")
    await client.post("/api/access-requests", json=ASK)
    rid = (await client.get("/api/access-requests")).json()[0]["id"]
    assert (await client.post(f"/api/access-requests/{rid}/deny")).json()["status"] == "denied"
    assert (await client.post(f"/api/access-requests/{rid}/deny")).status_code == 409
    assert (await client.post(f"/api/access-requests/{rid}/approve")).status_code == 409
    assert (await client.get("/api/system/status")).json()["pending_access_requests"] == 0


async def test_direct_invite_revoke_and_replace(client, maker):
    await register(client, "admin@b.co", "Admin")
    first = (await client.post("/api/invites", json={"email": "new@b.co"})).json()
    second = (await client.post("/api/invites", json={"email": "NEW@b.co"})).json()
    assert len((await client.get("/api/invites")).json()) == 1  # the newer link replaces the older one

    client.cookies.clear()
    assert (await client.get(f"/api/invites/by-token/{first['token']}")).status_code == 404
    await login(client, "admin@b.co")
    assert (await client.delete(f"/api/invites/{second['id']}")).status_code == 204
    client.cookies.clear()
    assert (await client.get(f"/api/invites/by-token/{second['token']}")).status_code == 404

    await login(client, "admin@b.co")
    assert (
        await client.post("/api/invites", json={"email": "admin@b.co"})
    ).status_code == 409  # has an account


async def test_invite_expires_and_token_is_stored_hashed(client, maker):
    await register(client, "admin@b.co", "Admin")
    invite = (await client.post("/api/invites", json={"email": "late@b.co"})).json()
    async with maker() as s:
        row = (await s.scalars(select(Invite))).one()
        assert row.token_hash != invite["token"] and invite["token"] not in row.token_hash
        row.expires_at = utcnow() - timedelta(minutes=1)
        await s.commit()
    client.cookies.clear()
    assert (await client.get(f"/api/invites/by-token/{invite['token']}")).status_code == 404
    gone = await client.post(
        f"/api/invites/by-token/{invite['token']}/accept", json={"name": "L", "password": "password123"}
    )
    assert gone.status_code == 404
    assert (await client.get("/api/invites")).status_code == 401
