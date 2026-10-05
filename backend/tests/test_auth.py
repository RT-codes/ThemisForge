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


async def test_first_account_is_admin_second_is_not(client):
    first = await client.post(
        "/api/auth/register", json={"email": "a@b.co", "name": "Ada", "password": "password123"}
    )
    assert first.json()["is_admin"] is True
    client.cookies.clear()
    second = await client.post(
        "/api/auth/register", json={"email": "c@d.co", "name": "Bob", "password": "password123"}
    )
    assert second.json()["is_admin"] is False
