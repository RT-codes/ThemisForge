from app.routers.workflows import MAX_NODE_PRESETS
from tests.conftest import make_project
from tests.test_workflows import setup


async def save_preset(client, pid: int, **body):
    return await client.post(f"/api/projects/{pid}/node-presets", json=body)


async def test_saved_nodes_are_kept_per_project_and_can_be_removed(client):
    _, pid = await setup(client)
    other = (await make_project(client, "Beta"))["id"]
    r = await save_preset(
        client, pid, kind="agent", label=" Reviewer ", config={"agentId": "3", "instructions": "Review it"}
    )
    assert r.status_code == 201, r.text
    saved = r.json()
    assert (saved["kind"], saved["label"]) == ("agent", "Reviewer")  # the label is trimmed
    assert saved["config"] == {"agentId": "3", "instructions": "Review it"}

    assert [p["id"] for p in (await client.get(f"/api/projects/{pid}/node-presets")).json()] == [saved["id"]]
    assert (await client.get(f"/api/projects/{other}/node-presets")).json() == []  # not shared

    assert (await client.delete(f"/api/node-presets/{saved['id']}")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}/node-presets")).json() == []
    assert (await client.delete(f"/api/node-presets/{saved['id']}")).status_code == 404


async def test_a_saved_node_must_be_a_known_kind_with_text_settings(client):
    _, pid = await setup(client)
    assert (await save_preset(client, pid, kind="wizard", label="x")).status_code == 422
    assert (await save_preset(client, pid, kind="task", config={"title": 5})).status_code == 422


async def test_a_project_keeps_a_limited_number_of_saved_nodes(client):
    _, pid = await setup(client)
    for i in range(MAX_NODE_PRESETS):
        assert (await save_preset(client, pid, kind="end", label=f"End {i}")).status_code == 201
    assert (await save_preset(client, pid, kind="end", label="One too many")).status_code == 409
