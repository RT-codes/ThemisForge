import app.features.connections.service as connections
from app.features.connections.providers.claude import API_KEY_ENV, SUBSCRIPTION_ENV
from tests.conftest import API_KEY, SUBSCRIPTION, make_project, register


async def connect(client, token):
    return await client.post("/api/connections", json={"provider": "claude", "token": token})


async def test_claude_is_listed_as_the_login_of_its_harness(client, anthropic):
    await register(client)
    providers = {p["id"]: p for p in (await client.get("/api/connections")).json()["providers"]}
    assert providers["claude"]["category"] == "ai" and providers["claude"]["harness"] == "claude"
    assert providers["github"]["harness"] == ""


async def test_a_subscription_token_is_stored_and_exported_as_the_oauth_variable(client, anthropic):
    await register(client)
    r = await connect(client, SUBSCRIPTION)
    assert r.status_code == 201, r.text
    assert (r.json()["account"], r.json()["settings"]) == ("Claude subscription", {"kind": "subscription"})
    assert SUBSCRIPTION not in str((await client.get("/api/connections")).json())
    provider = connections.get_provider("claude")
    assert provider.env_names_for({"kind": "subscription"}) == (SUBSCRIPTION_ENV,)
    assert provider.secret_env(SUBSCRIPTION) == {SUBSCRIPTION_ENV: SUBSCRIPTION}


async def test_an_api_key_is_checked_with_anthropic_and_exported_as_the_key_variable(client, anthropic):
    await register(client)
    r = await connect(client, API_KEY)
    assert r.status_code == 201 and r.json()["settings"] == {"kind": "api"}
    assert connections.get_provider("claude").secret_env(API_KEY) == {API_KEY_ENV: API_KEY}
    rejected = await connect(client, "sk-ant-api03-wrong")
    assert rejected.status_code == 422 and "rejected" in rejected.json()["detail"]


async def test_something_that_is_not_a_claude_token_is_refused(client, anthropic):
    await register(client)
    r = await connect(client, "ghp_notclaude")
    assert r.status_code == 422 and "setup-token" in r.json()["detail"]


async def test_a_project_cannot_choose_a_harness_login(client, anthropic):
    await register(client)
    conn = (await connect(client, SUBSCRIPTION)).json()
    pid = (await make_project(client))["id"]
    r = await client.put(
        f"/api/projects/{pid}/connections/claude", json={"connection_id": conn["id"], "config": {}}
    )
    assert r.status_code == 422 and "Settings" in r.json()["detail"]


async def test_a_claude_run_needs_the_owners_connection(client, maker, anthropic):
    user = await register(client)
    pid = (await make_project(client))["id"]
    async with maker() as s:
        plan = await connections.plan_for_run(s, pid, None, user["id"], "claude")
    assert "not connected" in plan.error
    await connect(client, SUBSCRIPTION)
    async with maker() as s:
        plan = await connections.plan_for_run(s, pid, None, user["id"], "claude")
        assert not plan.error and plan.connections[0].env_names == (SUBSCRIPTION_ENV,)
        assert (await connections.plan_for_run(s, pid, None, user["id"], "codex")).connections == []
