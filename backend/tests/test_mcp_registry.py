"""Adding tools from the official MCP registry (app/mcp_registry.py and its routes).

The doubles (FakeRegistry, the captured entries) are in registry_fakes.py. Nothing here talks to the network.
"""

import json

import pytest

from app import mcp_registry
from app.mcp_registry import MissingInput, build_tool, display_title, to_tool, tool_name
from tests.conftest import make_project, register
from tests.registry_fakes import entry

pytestmark = pytest.mark.usefixtures("fresh_caches")


# ----- what can and cannot be run -----


@pytest.mark.parametrize(
    "sample, runs",
    [
        ("npm_plain", "npx @smartmemory/compose-mcp@0.7.2"),
        ("playwright", "npx @playwright/mcp@0.0.82"),
        ("pypi_uvx", "uvx medium-ops@0.1.2"),
        ("remote_open", "https://time.b77.ai/mcp"),
        ("remote_both_transports", "https://waystation.ai/postgres/mcp"),  # the SSE one is not picked
        (
            "github",
            "https://api.githubcopilot.com/mcp/",
        ),  # its container image is passed over for the hosted one
    ],
)
def test_entries_that_can_run_say_what_would_run(sample, runs):
    tool = to_tool(entry(sample))
    assert tool.supported and tool.reason == "" and tool.runs == runs


@pytest.mark.parametrize(
    "sample, reason",
    [
        ("oci_only", "container"),
        ("nuget_only", "dotnet"),
        ("mcpb_only", "bundle"),
        ("remote_sse_only", "sse"),
        ("remote_custom_header", "headers"),
        ("package_http_server", "server_package"),
        ("pypi_python", "runtime"),
        ("empty", "empty"),
    ],
)
def test_entries_that_cannot_run_give_one_bucketed_reason(sample, reason):
    tool = to_tool(entry(sample))
    assert not tool.supported
    assert tool.reason == reason
    assert tool.reason_text == mcp_registry.REASONS[reason]
    assert tool.inputs == []


def test_an_entry_with_several_ways_prefers_a_package_that_runs_in_the_cell():
    azure = to_tool(entry("many_packages"))  # nuget, npm, pypi and bundles
    assert azure.supported and azure.source == "package" and azure.command == "npx"
    context7 = to_tool(entry("context7"))  # an npm package and a hosted address
    assert context7.source == "package"


def test_a_program_the_image_lacks_is_reported_and_another_way_is_used_when_there_is_one():
    no_npx = frozenset({"uvx"})
    tool = to_tool(entry("npm_plain"), no_npx)
    assert not tool.supported and tool.reason == "image_command" and "'npx'" in tool.reason_text
    assert to_tool(entry("pypi_uvx"), no_npx).supported
    # context7 also has a hosted address, which needs nothing from the image
    fallback = to_tool(entry("context7"), no_npx)
    assert fallback.supported and fallback.source == "remote"
    assert to_tool(entry("npm_plain"), None).supported  # unknown image: nothing is held against the tool


def test_a_package_from_another_package_registry_is_refused_rather_than_run_under_the_same_name():
    e = entry("npm_plain")
    e["packages"][0]["registryBaseUrl"] = "https://registry.evil.example"
    tool = to_tool(e)
    assert not tool.supported and tool.reason == "other"


@pytest.mark.parametrize(
    "field, value",
    [
        ("identifier", "--package=evil"),  # would become a flag of npx
        ("identifier", "name with spaces"),
        ("version", "1.0 --yes"),
    ],
)
def test_metadata_that_would_become_a_flag_is_refused(field, value):
    e = entry("npm_plain")
    e["packages"][0][field] = value
    assert to_tool(e).reason == "other"


def test_a_secret_cannot_become_a_command_line_argument():
    e = entry("npm_required_arg")
    e["packages"][0]["packageArguments"][1]["isSecret"] = True
    assert to_tool(e).reason == "needs_setup"


def test_values_built_from_other_values_are_not_understood_yet():
    e = entry("npm_plain")
    e["packages"][0]["environmentVariables"] = [{"name": "HOME_DIR", "value": "{base}/x"}]
    assert to_tool(e).reason == "needs_setup"


# ----- building the tool -----


def test_a_package_becomes_an_npx_command_pinned_to_its_version():
    tool = build_tool(entry("playwright"), {})
    assert (tool.kind, tool.command, tool.args) == ("stdio", "npx", ["-y", "@playwright/mcp@0.0.82"])
    assert tool.name == "playwright-mcp"
    assert tool.description == "Playwright Tools for MCP"


def test_a_python_package_runs_with_uvx_and_keeps_its_fixed_arguments():
    tool = build_tool(entry("pypi_uvx"), {})
    assert tool.command == "uvx"
    assert tool.args == ["medium-ops@0.1.2", "mcp", "serve"]


def test_what_a_package_asks_for_is_listed_and_required_ones_must_be_given():
    e = entry("npm_required_arg")
    tool = to_tool(e)
    (needed,) = [i for i in tool.inputs if i.required]
    assert needed.id.startswith("arg:") and not needed.secret
    with pytest.raises(MissingInput, match="Fill in"):
        build_tool(e, {})
    built = build_tool(e, {needed.id: "/workspace/bundle.json"})
    assert built.args[-1] == "/workspace/bundle.json"
    assert built.args[:2] == ["-y", "@ai-native-design-framework/kit@0.2.1"]
    assert "mcp" in built.args  # the argument it always has


def test_a_secret_input_is_a_stored_key_and_goes_into_the_tools_keys():
    e = entry("npm_secret_env")
    (secret,) = [i for i in to_tool(e).inputs if i.secret]
    assert secret.required
    built = build_tool(e, {secret.id: "12"})
    assert built.secret_env == {"CLAWFETCH_PRIVATE_KEY": 12}
    assert "12" not in json.dumps(built.args) and built.env == {}
    with pytest.raises(ValueError, match="stored key"):
        build_tool(e, {secret.id: "sk-pasted-secret"})  # a value typed in is never accepted as a secret


def test_optional_settings_are_only_set_when_given():
    e = entry("npm_literal_arg")
    plain = build_tool(e, {})
    assert plain.env == {}
    ids = {i.label: i.id for i in to_tool(e).inputs}
    set_one = build_tool(e, {ids["LOG_LEVEL"]: "debug"})
    assert set_one.env == {"LOG_LEVEL": "debug"}


def test_a_hosted_tool_gets_its_address_and_a_bearer_key():
    tool = build_tool(entry("github"), {"bearer:token": "5"})
    assert (tool.kind, tool.url, tool.bearer_secret_id) == ("http", "https://api.githubcopilot.com/mcp/", 5)
    assert build_tool(entry("github"), {}).bearer_secret_id is None
    with pytest.raises(MissingInput):  # this one's header is required
        build_tool(entry("remote_bearer"), {})


def test_an_address_with_variables_is_filled_in_and_optional_headers_are_left_out():
    e = entry("azure_devops")
    tool = to_tool(e)
    assert tool.supported
    (org,) = tool.inputs
    assert org.id == "var:organization" and org.required
    assert build_tool(e, {org.id: "contoso"}).url == "https://mcp.dev.azure.com/contoso"
    with pytest.raises(MissingInput):
        build_tool(e, {})


def test_a_choice_must_be_one_of_the_choices():
    e = entry("azure_devops")
    e["remotes"][0]["variables"]["organization"]["choices"] = ["a", "b"]
    with pytest.raises(ValueError, match="one of"):
        build_tool(e, {"var:organization": "c"})
    assert build_tool(e, {"var:organization": "a"}).url.endswith("/a")


def test_an_entry_that_cannot_run_cannot_be_built():
    with pytest.raises(ValueError, match="container"):
        build_tool(entry("oci_only"), {})


def test_a_tools_name_is_the_last_part_of_the_registry_name_as_a_slug():
    assert tool_name("io.github.github/github-mcp-server") == "github-mcp-server"
    assert tool_name("ai.smithery/Hint_Services obsidian") == "hint-services-obsidian"
    assert tool_name("a.b/" + "x" * 80) == "x" * 40
    assert tool_name("a.b/---") == "tool"


# ----- talking to the registry -----


async def test_one_entry_is_looked_up_by_its_name_and_a_bad_name_never_reaches_the_registry(registry):
    registry.entries["io.github.github/github-mcp-server"] = entry("github")
    found = await mcp_registry.get_entry("io.github.github/github-mcp-server")
    assert found["name"] == "io.github.github/github-mcp-server"
    assert "io.github.github%2Fgithub-mcp-server/versions/latest" in registry.asked[0][0]
    assert await mcp_registry.get_entry("../../etc/passwd") is None
    assert await mcp_registry.get_entry("nope/missing") is None
    assert len(registry.asked) == 2  # the bad name was not asked


def test_the_featured_list_is_read_from_its_file_and_a_broken_file_is_just_empty(tmp_path, monkeypatch):
    file = tmp_path / "featured.yaml"
    file.write_text(
        "featured:\n  - name: a.b/one\n    note: First\n  - a.b/two\n  - name: not a name\n  - 7\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_registry, "FEATURED_FILE", file)
    assert mcp_registry.featured_names() == [("a.b/one", "First"), ("a.b/two", "")]
    file.write_text("featured: [unclosed", encoding="utf-8")
    assert mcp_registry.featured_names() == []
    monkeypatch.setattr(mcp_registry, "FEATURED_FILE", tmp_path / "missing.yaml")
    assert mcp_registry.featured_names() == []


def test_the_shipped_featured_list_has_valid_names():
    names = mcp_registry.featured_names()
    assert names and all(mcp_registry.REGISTRY_NAME.match(n) for n, _ in names)


async def test_featured_tools_the_registry_no_longer_has_are_skipped(registry, tmp_path, monkeypatch):
    file = tmp_path / "featured.yaml"
    file.write_text(
        "- name: io.github.github/github-mcp-server\n  note: hi\n- name: gone.x/y\n", encoding="utf-8"
    )
    monkeypatch.setattr(mcp_registry, "FEATURED_FILE", file)
    registry.entries["io.github.github/github-mcp-server"] = entry("github")
    found = await mcp_registry.featured()
    assert [(e["name"], note) for e, note in found] == [("io.github.github/github-mcp-server", "hi")]


async def test_what_an_image_can_start_is_remembered_and_unknown_when_it_cannot_be_looked_up(monkeypatch):
    calls = []

    async def fake(image, commands, docker_host=""):
        calls.append(image)
        return {"npx": True, "uvx": False}

    monkeypatch.setattr(mcp_registry, "commands_in_image", fake)
    assert await mcp_registry.available_runners("img:1") == frozenset({"npx"})
    assert await mcp_registry.available_runners("img:1") == frozenset({"npx"})
    assert calls == ["img:1"]

    async def unknown(image, commands, docker_host=""):
        return None

    monkeypatch.setattr(mcp_registry, "commands_in_image", unknown)
    assert await mcp_registry.available_runners("img:2") is None


# ----- the routes -----


async def test_only_an_administrator_can_browse_the_registry(client, registry):
    await register(client)
    await register(client, "c@d.co", "Bob")
    pid = (await make_project(client, "Bobs"))["id"]
    assert (await client.get(f"/api/projects/{pid}/mcp-registry")).status_code == 403
    assert (await client.get(f"/api/projects/{pid}/mcp-registry/featured")).status_code == 403
    r = await client.post(f"/api/projects/{pid}/mcp-registry/prefill", json={"name": "a.b/c"})
    assert r.status_code == 403
    assert registry.asked == []


async def test_featured_tools_come_with_their_notes(client, registry, tmp_path, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    file = tmp_path / "featured.yaml"
    file.write_text("- name: io.github.github/github-mcp-server\n  note: Issues and pull requests\n")
    monkeypatch.setattr(mcp_registry, "FEATURED_FILE", file)
    registry.entries["io.github.github/github-mcp-server"] = entry("github")
    r = await client.get(f"/api/projects/{pid}/mcp-registry/featured")
    assert r.status_code == 200, r.text
    (tool,) = r.json()
    assert tool["note"] == "Issues and pull requests" and tool["supported"]


async def test_the_registry_being_down_is_a_clear_error_and_the_manual_form_still_works(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    registry.error = mcp_registry.RegistryUnavailable("The MCP registry did not answer within 10 seconds.")
    r = await client.get(f"/api/projects/{pid}/mcp-registry/featured")
    assert r.status_code == 502
    assert "did not answer" in r.json()["detail"] and "by hand" in r.json()["detail"]
    manual = await client.post(
        f"/api/projects/{pid}/mcp-servers", json={"name": "files", "command": "npx -y some-server"}
    )
    assert manual.status_code == 201


async def test_prefill_builds_the_tool_from_the_registrys_entry_not_from_what_the_browser_sends(
    client, registry
):
    await register(client)
    pid = (await make_project(client))["id"]
    registry.entries["io.github.microsoft/playwright-mcp"] = entry("playwright")
    r = await client.post(
        f"/api/projects/{pid}/mcp-registry/prefill",
        json={"name": "io.github.microsoft/playwright-mcp", "values": {}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["command"] == "npx"
    assert r.json()["args"] == ["-y", "@playwright/mcp@0.0.82"]
    # prefilling saves nothing
    assert (await client.get(f"/api/projects/{pid}/mcp-servers")).json() == []


async def test_prefill_reports_missing_answers_and_unknown_tools_and_unusable_ones(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    url = f"/api/projects/{pid}/mcp-registry/prefill"
    registry.entries["a.b/needs-arg"] = entry("npm_required_arg")
    registry.entries["a.b/container"] = entry("oci_only")
    missing = await client.post(url, json={"name": "a.b/needs-arg"})
    assert missing.status_code == 422 and "Fill in" in missing.json()["detail"]
    assert (await client.post(url, json={"name": "a.b/container"})).status_code == 422
    assert (await client.post(url, json={"name": "a.b/nothing"})).status_code == 404


async def test_prefill_checks_that_the_chosen_key_exists(client, registry):
    await register(client)
    pid = (await make_project(client))["id"]
    registry.entries["io.github.github/github-mcp-server"] = entry("github")
    url = f"/api/projects/{pid}/mcp-registry/prefill"
    body = {"name": "io.github.github/github-mcp-server", "values": {"bearer:token": "9999"}}
    assert (await client.post(url, json=body)).status_code == 422
    key = await client.post("/api/secrets", json={"name": "GitHub token", "kind": "github", "value": "ghp_x"})
    body["values"]["bearer:token"] = str(key.json()["id"])
    r = await client.post(url, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["bearer_secret_id"] == key.json()["id"]


def test_a_tool_without_a_title_is_called_by_its_name_made_readable():
    assert display_title("io.github.x/y", "Given Title") == "Given Title"
    assert display_title("io.github.awkoy/notion-mcp-server") == "Notion MCP Server"
    assert display_title("io.github.microsoft/playwright-mcp") == "Playwright MCP"
    assert display_title("io.github.a/better_notion") == "Better Notion"
    assert display_title("com.notion/mcp") == "Notion"  # a generic last part is the publisher's name instead
    assert display_title("io.github.zed-industries/server") == "Zed Industries"
    assert display_title("ai.smithery/smithery-notion") == "Smithery Notion"
