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


async def test_registration_is_closed_after_the_administrator(client):
    assert (await client.get("/api/auth/setup")).json() == {"needs_admin": True}
    body = {"email": "a@b.co", "name": "Ada", "password": "password123"}
    first = await client.post("/api/auth/register", json=body)
    assert first.status_code == 201 and first.json()["is_admin"] is True

    assert (await client.get("/api/auth/setup")).json() == {"needs_admin": False}
    client.cookies.clear()
    again = await client.post("/api/auth/register", json={**body, "email": "c@d.co", "name": "Bob"})
    assert again.status_code == 403 and "invite" in again.json()["detail"].lower()
    assert (await client.get("/api/auth/me")).status_code == 401  # and no session was created
