"""Splitters send a run down several branches that run side by side; Mergers wait for them and combine the results
and the working folders. Everything else about a run (one node at a time, in order) is covered in test_workflows."""

import asyncio
from datetime import datetime

from app.codex import save_auth
from tests.test_harness import fake_auth
from tests.test_workflows import by_id, edge, make_workflow, node, run, save, setup


def line(a: str, b: str, out: str | None = None, into: str | None = None) -> dict:
    e = edge(a, b, out)
    return {**e, "id": f"{a}-{out}-{b}-{into}", **({"targetHandle": into} if into else {})}


def task(id_: str, title: str, label: str = "", **config) -> dict:
    return node(id_, "task", label or title, action="create", title=title, status="ready", **config)


def span(n: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(n["started_at"]), datetime.fromisoformat(n["finished_at"])


def branches(*nodes: dict) -> tuple[list[dict], list[dict]]:
    """start -> splitter -> (o1 -> first, o2 -> second) -> merger (i1, i2) -> end, around the given two branch nodes."""
    a, b = nodes
    return (
        [node("s", "start"), node("sp", "split", "Split", branches="2"), a, b,
         node("m", "merge", "Merge", branches="2"), node("e", "end")],
        [line("s", "sp"), line("sp", a["id"], "o1"), line("sp", b["id"], "o2"),
         line(a["id"], "m", into="i1"), line(b["id"], "m", into="i2"), line("m", "e")],
    )  # fmt: skip


async def test_branches_run_at_the_same_time_and_the_merger_waits_for_both(client, runner, cells):
    _, pid = await setup(client)
    cells.duration = 0.4
    nodes, edges = branches(task("l", "Left"), task("r", "Right"))
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "succeeded", detail["outcome"]
    (l0, l1), (r0, r1), (m0, _) = span(n["l"]), span(n["r"]), span(n["m"])
    assert l0 < r1 and r0 < l1  # their cells overlapped: one did not wait for the other
    assert m0 >= max(l1, r1)  # and the merger only started once both were done
    assert "## Left" in n["m"]["result"] and "## Right" in n["m"]["result"]
    assert n["e"]["status"] == "succeeded"


async def test_without_a_splitter_lines_out_of_one_node_still_run_one_after_another(client, runner, cells):
    _, pid = await setup(client)
    cells.duration = 0.2
    detail = await run(
        client, pid,
        [node("s", "start"), task("a", "First"), task("b", "Second")],
        [line("s", "a"), line("s", "b")],
    )  # fmt: skip
    n = by_id(detail)
    assert detail["status"] == "succeeded"
    assert span(n["b"])[0] >= span(n["a"])[1]  # nothing about a plain fan-out changed


async def test_each_branch_works_on_its_own_copy_and_the_merger_puts_them_side_by_side(
    client, runner, cells, maker
):
    me, pid = await setup(client)
    async with maker() as s:
        await save_auth(s, me["id"], fake_auth(), fresh=True)
    cells.files = {
        "Seed": {"shared.txt": "seed", "docs/a.md": "doc"},
        "Left": {"left.txt": "l"},
        "Right": {"right.txt": "r"},
    }
    nodes = [
        node("s", "start"), task("seed", "Seed"), node("sp", "split", "Split", branches="2"),
        task("l", "Left", workdir="inherit"), task("r", "Right", workdir="inherit"),
        node("m", "merge", "Merge", branches="2"), node("after", "agent", "After", harness="codex", instructions="Review", workdir="inherit"),
    ]  # fmt: skip
    edges = [
        line("s", "seed"), line("seed", "sp"), line("sp", "l", "o1"), line("sp", "r", "o2"),
        line("l", "m", into="i1"), line("r", "m", into="i2"), line("m", "after"),
    ]  # fmt: skip
    detail = await run(client, pid, nodes, edges)
    assert detail["status"] == "succeeded", detail["outcome"]
    spec = {s.title: s for s in cells.specs}
    folders = {t: spec[t].workspace_dir for t in ("Seed", "Left", "Right", "After")}
    assert (
        len(set(folders.values())) == 4
    )  # the branches did not write into the seed's folder, or each other's
    assert (folders["Left"] / "shared.txt").is_file() and not (folders["Left"] / "right.txt").exists()
    assert (folders["Right"] / "shared.txt").is_file() and not (folders["Right"] / "left.txt").exists()
    after = folders["After"]  # named after the branches, so the next agent can tell whose work is whose
    assert (after / "left" / "left.txt").read_text() == "l" and (after / "left" / "shared.txt").is_file()
    assert (after / "right" / "right.txt").read_text() == "r" and not (after / "right" / "left.txt").exists()
    assert "left/" in by_id(detail)["m"]["result"] and "right/" in by_id(detail)["m"]["result"]
    # and the agent is told what the folder holds
    assert "Combined the work of Left (in left/), Right (in right/)" in spec["After"].prompt


async def test_a_branch_can_be_given_only_some_of_the_files(client, runner, cells):
    _, pid = await setup(client)
    cells.files = {"Seed": {"docs/a.md": "doc", "src/b.py": "code", "README.md": "hi"}}
    nodes = [
        node("s", "start"), task("seed", "Seed"),
        node("sp", "split", "Split", branches="2", files1="docs", files2="*.md"),
        task("l", "Docs", workdir="inherit"), task("r", "Readme", workdir="inherit"),
    ]  # fmt: skip
    edges = [line("s", "seed"), line("seed", "sp"), line("sp", "l", "o1"), line("sp", "r", "o2")]
    detail = await run(client, pid, nodes, edges)
    assert detail["status"] == "succeeded", detail["outcome"]
    spec = {s.title: s.workspace_dir for s in cells.specs}
    assert (spec["Docs"] / "docs" / "a.md").is_file() and not (spec["Docs"] / "src").exists()
    assert (spec["Readme"] / "README.md").is_file() and not (spec["Readme"] / "docs").exists()


async def test_a_branch_whose_rule_is_not_met_is_not_sent_anything_and_the_merger_does_not_wait(
    client, runner
):
    _, pid = await setup(client)
    nodes = [
        node("s", "start"), task("seed", "Seed"),
        node("sp", "split", "Split", branches="2", contains2="deploy"),
        task("l", "Left"), task("r", "Right"), node("m", "merge", "Merge", branches="2"),
    ]  # fmt: skip
    edges = [
        line("s", "seed"), line("seed", "sp"), line("sp", "l", "o1"), line("sp", "r", "o2"),
        line("l", "m", into="i1"), line("r", "m", into="i2"),
    ]  # fmt: skip
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "succeeded", detail["outcome"]
    assert n["r"]["status"] == "skipped" and n["m"]["status"] == "succeeded"
    assert "## Left" in n["m"]["result"] and "Right" not in n["m"]["result"]
    assert "does not contain 'deploy'" in n["sp"]["log"]


async def test_a_merger_behind_a_condition_does_not_wait_for_the_side_that_was_not_taken(client, runner):
    _, pid = await setup(client)
    nodes = [
        node("s", "start"), task("seed", "Seed"),
        node("c", "condition", source="result", operator="contains", value="finished"),
        task("y", "Yes side"), task("n", "No side"), node("m", "merge", "Merge", branches="2"),
        node("e", "end"),
    ]  # fmt: skip
    edges = [
        line("s", "seed"), line("seed", "c"), line("c", "y", "yes"), line("c", "n", "no"),
        line("y", "m", into="i1"), line("n", "m", into="i2"), line("m", "e"),
    ]  # fmt: skip
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "succeeded", detail["outcome"]
    assert (
        n["n"]["status"] == "skipped" and n["m"]["status"] == "succeeded" and n["e"]["status"] == "succeeded"
    )


async def test_a_merger_fails_with_the_reason_when_a_branch_failed(client, runner, cells):
    _, pid = await setup(client)
    nodes, edges = branches(task("l", "Left"), task("r", "will fail"))
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "failed"
    assert n["r"]["status"] == "failed" and n["l"]["status"] == "succeeded"  # the other branch was not undone
    assert n["m"]["status"] == "failed" and "'will fail' failed" in n["m"]["error"]
    assert "nothing to merge" in n["m"]["error"] and n["e"]["status"] == "skipped"
    failed = [x["node_id"] for x in detail["nodes"] if x["status"] == "failed"]
    assert failed[0] == "r"  # the first failure is the branch itself, which is what the ticket names


async def test_a_merger_can_carry_on_with_the_branches_that_worked(client, runner):
    _, pid = await setup(client)
    nodes, edges = branches(task("l", "Left"), task("r", "will fail"))
    nodes[4] = node("m", "merge", "Merge", branches="2", onFailure="continue")
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert n["m"]["status"] == "succeeded" and "## Left" in n["m"]["result"]
    assert "will fail: failed" in n["m"]["log"]
    assert detail["status"] == "failed"  # the failed step still counts: carrying on is only about the merge


async def test_a_failed_branch_stops_the_others_from_starting_anything_new(client, runner, cells):
    _, pid = await setup(client)
    cells.duration = 0.3
    nodes = [
        node("s", "start"), node("sp", "split", "Split", branches="2"),
        node("bad", "agent", "Bad", harness="codex"),  # no instructions: fails at once
        task("slow", "Slow"), task("later", "Later"),
    ]  # fmt: skip
    edges = [line("s", "sp"), line("sp", "bad", "o1"), line("sp", "slow", "o2"), line("slow", "later")]
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "failed" and n["bad"]["status"] == "failed"
    assert n["slow"]["status"] == "succeeded"  # what was already going finished
    assert n["later"]["status"] == "skipped" and "a branch failed" in n["later"]["error"]


async def test_cancelling_stops_every_branch(client, runner, cells, scheduler):
    _, pid = await setup(client)
    cells.duration = 30
    nodes, edges = branches(task("l", "Left"), task("r", "Right"))
    wid = await make_workflow(client, pid)
    await save(client, wid, nodes, edges)
    run_id = (await client.post(f"/api/workflows/{wid}/runs")).json()["id"]
    async with asyncio.timeout(10):
        while len(scheduler._live) < 2:
            await asyncio.sleep(0.02)
    r = await client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert by_id(r.json())["l"]["status"] == "cancelled" and by_id(r.json())["r"]["status"] == "cancelled"
    assert not scheduler._live


async def test_a_branch_waiting_for_a_cell_is_not_failed_for_the_time_it_waited(client, runner, cells):
    _, pid = await setup(client)
    runner.POLL_SECONDS = 0.01
    cells.duration = 0.1
    nodes, edges = branches(task("l", "Left"), task("r", "Right"))
    detail = await run(client, pid, nodes, edges)
    assert detail["status"] == "succeeded"


async def test_the_branch_points_of_a_splitter_and_merger_are_checked(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    base = [
        node("s", "start"),
        node("sp", "split", branches="2"),
        node("m", "merge", branches="2"),
        node("e", "end"),
    ]

    async def attempt(edges: list[dict]) -> int:
        r = await client.patch(f"/api/workflows/{wid}", json={"graph": {"nodes": base, "edges": edges}})
        return r.status_code

    assert await attempt([line("s", "sp"), line("sp", "e", "o1"), line("s", "m", into="i1")]) == 200
    assert await attempt([line("sp", "e")]) == 422  # a Splitter line has to leave from a branch point
    assert await attempt([line("s", "m")]) == 422  # and a Merger line has to arrive at one
    assert await attempt([line("sp", "e", "o9")]) == 422


async def test_splitters_and_mergers_can_be_nested(client, runner, cells):
    _, pid = await setup(client)
    cells.duration = 0.1
    nodes = [
        node("s", "start"), node("sp1", "split", "Outer split", branches="2"),
        node("sp2", "split", "Inner split", branches="2"),
        task("a", "Alpha"), task("b", "Beta"), node("m2", "merge", "Inner merge", branches="2"),
        task("c", "Gamma"), node("m1", "merge", "Outer merge", branches="2"), node("e", "end"),
    ]  # fmt: skip
    edges = [
        line("s", "sp1"), line("sp1", "sp2", "o1"), line("sp1", "c", "o2"),
        line("sp2", "a", "o1"), line("sp2", "b", "o2"),
        line("a", "m2", into="i1"), line("b", "m2", into="i2"),
        line("m2", "m1", into="i1"), line("c", "m1", into="i2"), line("m1", "e"),
    ]  # fmt: skip
    detail = await run(client, pid, nodes, edges)
    n = by_id(detail)
    assert detail["status"] == "succeeded", detail["outcome"]
    assert all(x["status"] == "succeeded" for x in detail["nodes"]) and len(detail["nodes"]) == 9
    assert span(n["m2"])[0] >= max(span(n["a"])[1], span(n["b"])[1])
    assert span(n["m1"])[0] >= max(span(n["m2"])[1], span(n["c"])[1])
    for name in ("Alpha", "Beta", "Gamma"):
        assert f"## {name}" in n["m1"]["result"] or name in n["m1"]["result"]
