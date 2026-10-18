"""The tools of the MCP control plane (see app/control.py): what an outside agent can read, and the actions it may take.

Each tool is a thin wrapper around the REST handler the web interface already uses, called as the token's user, so
what an agent sees is exactly what that person sees, under the same rules. Two things are added here, for every tool:

- **Reach.** A token for one project may only touch that project. A tool takes `project_id` for the project it means; a
  connection for all projects must name it, a connection for one project can leave it out. An id of anything else (a
  task, an agent, a folder...) is checked against the same reach once the thing is found, and when it is out of reach
  the answer is the one for a thing that does not exist.
- **Size.** Lists are cut to a limit, logs and files to a number of characters, so one call cannot flood an agent.

A handler is called as a plain function, so the checks FastAPI would run for the route as dependencies (who is logged
in, whether they are an administrator) do not run. The user and the session are supplied here; a handler that needs
more (an `AdminUser`) must have that check made by hand. tests/test_control.py fails when one is missed.

Reading tools work for every token. The actions (`write_tool`) change things and so need a token made with the `write`
scope; control.py refuses them for the others before they run. They are the day-to-day controls of a project (tasks,
runs, workflows, approvals, halting) and nothing that destroys or reconfigures: no deleting, no settings, no files.
"""

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from . import overview
from .app_settings import AppSettings
from .deps import require_admin
from .models import Board, Webhook, WorkflowNodeRun, WorkflowRun
from .routers import (
    agents,
    connections,
    notifications,
    projects,
    skills,
    system,
    tools,
    volumes,
    webhooks,
    workflows,
)
from .routers import workspaces as workspaces_router
from .routers.agents import AgentOut, HarnessOut
from .routers.connections import BindingOut
from .routers.skills import SkillDetail, SkillOut
from .routers.system import SystemStatus
from .routers.tools import KeyOut, McpOut
from .routers.volumes import FileEntry, VolumeOut
from .routers.workflows import ApprovalOut, RunDetail, RunSummary, WorkflowOut, WorkflowSummary
from .schemas import (
    AttemptDetail,
    AttemptOut,
    BoardOut,
    DeliveryOut,
    MoveIn,
    NotificationOut,
    ProjectEventOut,
    ProjectOut,
    ProjectSummary,
    ScheduledRun,
    TaskIn,
    TaskOut,
    TaskPatch,
    UsageRow,
    WebhookOut,
    WorkspaceOut,
)
from .volumes import FileError, list_dir, safe_path

if TYPE_CHECKING:
    from .control import Caller, ControlPlane

NOT_FOUND = "Not found"

ProjectId = Annotated[
    int | None,
    Field(
        description="The project. Leave out on a connection made for one project; list_projects has the ids."
    ),
]


class BoardView(BaseModel):
    """A board as the web interface shows it: its columns and the tasks in them."""

    workspace: str
    board: BoardOut
    tasks: list[TaskOut]


class Folder(BaseModel):
    path: str
    entries: list[FileEntry]
    writable: bool


class FileContent(BaseModel):
    path: str
    size: int  # bytes on disk
    truncated: bool  # the text is cut at max_chars
    text: str


def pinned(caller: "Caller", project_id: int) -> None:
    """Refuse a project a connection for one project does not reach, as if it did not exist."""
    if caller.project_id is not None and project_id != caller.project_id:
        raise ToolError(NOT_FOUND)


def project_of(caller: "Caller", project_id: int | None) -> int:
    """The project a tool works on: the one asked for, or the connection's own."""
    if project_id is None:
        if caller.project_id is None:
            raise ToolError(
                "Say which project: project_id is needed on a connection for all projects. list_projects has them."
            )
        return caller.project_id
    pinned(caller, project_id)
    return project_id


def account_only(caller: "Caller") -> None:
    if caller.project_id is not None:
        raise ToolError("Global settings need a connection made for all projects, not for one project.")


def register(plane: "ControlPlane") -> None:
    """Add every tool to the plane's server."""
    tool, write_tool, acting = plane.tool, plane.write_tool, plane.acting

    def web_request() -> SimpleNamespace:
        """The handlers of actions reach the scheduler and the workflow engine through `request.app.state`, so the app
        stands in for the web request they expect (as it does for get_system_status)."""
        return SimpleNamespace(app=plane.app())

    # projects

    @tool
    async def list_projects() -> list[ProjectSummary]:
        """The projects this connection can see, with the number of tasks per status and when the next one starts."""
        async with acting() as (s, owner, caller):
            found = await projects.list_projects(s, owner)
            return [p for p in found if caller.project_id in (None, p.id)]

    @tool
    async def get_project_overview(project_id: ProjectId = None) -> overview.ProjectOverview:
        """A project at a glance, the one call to start with: tasks per status, the boards, what is running now, what
        needs a person (failed, blocked or in review, and workflow approvals), what is coming in the next day, the
        latest events and what the last week used. Lists are cut short; the other tools give the rest."""
        async with acting() as (s, owner, caller):
            return await overview.project_overview(s, owner, project_of(caller, project_id))

    @tool
    async def get_project(project_id: ProjectId = None) -> ProjectOut:
        """A project's name, purpose, description and the custom properties its tasks can have."""
        async with acting() as (s, owner, caller):
            found = await projects.get_project(project_of(caller, project_id), s, owner)
            return ProjectOut.model_validate(found)

    @tool
    async def get_history(
        project_id: ProjectId = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 30,
        board_id: int | None = None,
        task_id: int | None = None,
    ) -> list[ProjectEventOut]:
        """What was done in the project, newest first: tasks made, moved, run, finished or failed. Optionally only
        what concerns one board or one task."""
        async with acting() as (s, owner, caller):
            events = await projects.project_history(
                project_of(caller, project_id), s, owner, limit=limit, board_id=board_id, task_id=task_id
            )
            return [ProjectEventOut.model_validate(e) for e in events]

    @tool
    async def list_upcoming_runs(
        project_id: ProjectId = None, hours: Annotated[int, Field(ge=1, le=336)] = 24
    ) -> list[ScheduledRun]:
        """What is going to run in the next hours: one-off tasks and each occurrence of recurring ones."""
        async with acting() as (s, owner, caller):
            return await projects.upcoming_runs(project_of(caller, project_id), s, owner, hours=hours)

    @tool
    async def get_usage(
        project_id: ProjectId = None, days: Annotated[int, Field(ge=1, le=365)] = 7
    ) -> list[UsageRow]:
        """What the project's runs used over the last days, per harness and model. Tokens are as the harness reported
        them; cached input is part of input and reasoning part of output."""
        async with acting() as (s, owner, caller):
            return await projects.project_usage(project_of(caller, project_id), s, owner, days=days)

    # boards and tasks

    @tool
    async def list_boards(project_id: ProjectId = None) -> list[WorkspaceOut]:
        """The project's workspaces, each with its boards, their columns (statuses) and the number of tasks in each.
        A task's board_id and status refer to these."""
        async with acting() as (s, owner, caller):
            return await workspaces_router.list_workspaces(project_of(caller, project_id), s, owner)

    @tool
    async def get_board(board_id: int) -> BoardView:
        """One board with all of its tasks, the way the web interface shows it: its columns and what is in them."""
        async with acting() as (s, owner, caller):
            board = await s.get(Board, board_id)
            if board is None:
                raise ToolError(NOT_FOUND)
            pinned(caller, board.project_id)
            for workspace in await workspaces_router.list_workspaces(board.project_id, s, owner):
                for b in workspace.boards:
                    if b.id == board_id:
                        tasks = await projects.list_tasks(
                            board.project_id, s, owner, board_id=board_id, include_steps=False
                        )
                        return BoardView(workspace=workspace.name, board=b, tasks=tasks)
            raise ToolError(NOT_FOUND)

    @tool
    async def list_tasks(
        project_id: ProjectId = None,
        board_id: int | None = None,
        status: Annotated[
            str | None, Field(description="A status key such as ready, running, review, done, failed")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[TaskOut]:
        """Tasks of a project in board order, optionally only one board's or one status's. Steps made by workflow runs
        are left out."""
        async with acting() as (s, owner, caller):
            found = await projects.list_tasks(
                project_of(caller, project_id), s, owner, board_id=board_id, include_steps=False
            )
            return [t for t in found if status is None or t.status == status][:limit]

    async def task_in_reach(s, owner, caller, task_id: int) -> TaskOut:
        task = await projects.get_task(task_id, s, owner)
        pinned(caller, task.project_id)
        return task

    @tool
    async def get_task(task_id: int) -> TaskOut:
        """One task: description, properties, schedule, the status of its latest run and its workflow stages."""
        async with acting() as (s, owner, caller):
            return await task_in_reach(s, owner, caller, task_id)

    @tool
    async def list_attempts(
        task_id: int, limit: Annotated[int, Field(ge=1, le=100)] = 10
    ) -> list[AttemptOut]:
        """The newest runs (attempts) of a task, with how each ended and what it used. get_attempt has the log."""
        async with acting() as (s, owner, caller):
            await task_in_reach(s, owner, caller, task_id)
            found = await projects.list_attempts(task_id, s, owner, limit=limit)
            return [AttemptOut.model_validate(a) for a in found]

    @tool
    async def get_attempt(
        attempt_id: int,
        log_chars: Annotated[
            int, Field(ge=0, le=50_000, description="How much of the end of the log to return")
        ] = 4000,
    ) -> AttemptDetail:
        """One run: how it ended, why it failed if it did, its result, what it used and the end of its log."""
        async with acting() as (s, owner, caller):
            attempt = await projects.get_attempt(attempt_id, s, owner)
            await task_in_reach(s, owner, caller, attempt.task_id)
            return attempt.model_copy(update={"log": attempt.log[-log_chars:] if log_chars else ""})

    # how a project is set up

    @tool
    async def list_agents(project_id: ProjectId = None) -> list[AgentOut]:
        """The project's agents: name, role, instructions, harness, model, reasoning effort, cell size, folders,
        skills, tools, keys and connections each is given."""
        async with acting() as (s, owner, caller):
            found = await agents.list_agents(project_of(caller, project_id), s, owner)
            return [AgentOut.model_validate(a) for a in found]

    @tool
    async def get_agent(agent_id: int) -> AgentOut:
        """One agent with its full configuration."""
        async with acting() as (s, owner, caller):
            agent = AgentOut.model_validate(await agents.get_agent(agent_id, s, owner))
            pinned(caller, agent.project_id)
            return agent

    @tool
    async def list_workflows(project_id: ProjectId = None) -> list[WorkflowSummary]:
        """The project's workflows with how many runs they had, the last run and what starts each by itself."""
        async with acting() as (s, owner, caller):
            return await workflows.list_workflows(project_of(caller, project_id), s, owner)

    async def workflow_in_reach(s, owner, caller, workflow_id: int) -> WorkflowOut:
        workflow = await workflows.get_workflow(workflow_id, s, owner)
        pinned(caller, workflow.project_id)
        return workflow

    @tool
    async def get_workflow(workflow_id: int) -> WorkflowOut:
        """One workflow with its whole graph: the nodes, their settings and how they are joined."""
        async with acting() as (s, owner, caller):
            return await workflow_in_reach(s, owner, caller, workflow_id)

    @tool
    async def list_workflow_runs(
        workflow_id: int, limit: Annotated[int, Field(ge=1, le=200)] = 20
    ) -> list[RunSummary]:
        """The newest runs of a workflow and how far each got."""
        async with acting() as (s, owner, caller):
            await workflow_in_reach(s, owner, caller, workflow_id)
            return await workflows.list_runs(workflow_id, s, owner, limit=limit)

    @tool
    async def get_workflow_run(run_id: int) -> RunDetail:
        """One workflow run with the result and log of every node."""
        async with acting() as (s, owner, caller):
            run = await workflows.get_run(run_id, s, owner)
            pinned(caller, run.project_id)
            return run

    @tool
    async def list_approvals(project_id: ProjectId = None) -> list[ApprovalOut]:
        """Workflow steps that wait for a person to approve or reject, oldest first. Without project_id on a
        connection for all projects: those of every project."""
        async with acting() as (s, owner, caller):
            wanted = project_of(caller, project_id) if project_id or caller.project_id else None
            return [a for a in await workflows.list_approvals(s, owner) if wanted in (None, a.project_id)]

    @tool
    async def list_skills(project_id: ProjectId = None) -> list[SkillOut]:
        """The project's skills (instructions agents can be given), by name."""
        async with acting() as (s, owner, caller):
            return await skills.list_skills(project_of(caller, project_id), s, owner)

    @tool
    async def get_skill(name: str, project_id: ProjectId = None) -> SkillDetail:
        """One skill with its full SKILL.md text."""
        async with acting() as (s, owner, caller):
            return await skills.get_skill(project_of(caller, project_id), name, s, owner)

    @tool
    async def list_tool_servers(project_id: ProjectId = None) -> list[McpOut]:
        """The tool servers (MCP) the project's agents can be given: how each starts or where it is, and whether its
        last connection test worked. Secret values are never part of it, only which key is used."""
        async with acting() as (s, owner, caller):
            return await tools.list_servers(project_of(caller, project_id), s, owner)

    @tool
    async def list_webhooks(project_id: ProjectId = None) -> list[WebhookOut]:
        """The project's webhooks: where messages from outside land as tasks and how. The address itself is secret and
        not included, only its last characters."""
        async with acting() as (s, owner, caller):
            return await webhooks.list_webhooks(project_of(caller, project_id), s, owner)

    @tool
    async def list_webhook_deliveries(
        webhook_id: int, limit: Annotated[int, Field(ge=1, le=100)] = 20
    ) -> list[DeliveryOut]:
        """The latest messages a webhook received, and what became of each."""
        async with acting() as (s, owner, caller):
            hook = await s.get(Webhook, webhook_id)
            if hook is None:
                raise ToolError(NOT_FOUND)
            pinned(caller, hook.project_id)
            found = await webhooks.list_deliveries(webhook_id, s, owner)
            return [DeliveryOut.model_validate(d) for d in found][:limit]

    @tool
    async def list_notifications(project_id: ProjectId = None) -> list[NotificationOut]:
        """Where the project sends messages when work fails or waits, and what each target hears about."""
        async with acting() as (s, owner, caller):
            found = await notifications.list_notifications(project_of(caller, project_id), s, owner)
            return [NotificationOut.model_validate(n) for n in found]

    @tool
    async def list_project_connections(project_id: ProjectId = None) -> list[BindingOut]:
        """The connections (GitHub...) the project uses, and as which account."""
        async with acting() as (s, owner, caller):
            return await connections.project_connections(project_of(caller, project_id), s, owner)

    # folders

    @tool
    async def list_folders(project_id: ProjectId = None) -> list[VolumeOut]:
        """The project's folders: the shared folders agents work in, and its config folder (agents, skills and tools as
        files). list_files and read_file take a folder's id."""
        async with acting() as (s, owner, caller):
            return await volumes.list_volumes(project_of(caller, project_id), s, owner, include_config=True)

    @tool
    async def list_files(folder_id: int, path: str = "") -> Folder:
        """The files and folders inside a folder, at a path ('' is the top, 'notes/2026' goes into notes)."""
        async with acting() as (s, owner, caller):
            root, writable, volume = await volumes.volume_root(s, folder_id, owner)
            pinned(caller, volume.project_id)
            try:
                folder = safe_path(root, path)
            except FileError as e:
                raise ToolError(str(e)) from None
            if not folder.is_dir():
                raise ToolError(NOT_FOUND)
            entries = await asyncio.to_thread(list_dir, folder)
            return Folder(
                path="/".join(p for p in path.split("/") if p),
                entries=[FileEntry(**vars(e)) for e in entries],
                writable=writable and volume.mode == "rw",
            )

    @tool
    async def read_file(
        folder_id: int,
        path: str,
        max_chars: Annotated[int, Field(ge=1, le=200_000)] = 20_000,
    ) -> FileContent:
        """The text of one file in a folder. Binary files are refused, long ones are cut at max_chars."""
        async with acting() as (s, owner, caller):
            root, _, volume = await volumes.volume_root(s, folder_id, owner)
            pinned(caller, volume.project_id)
            try:
                target = safe_path(root, path)
            except FileError as e:
                raise ToolError(str(e)) from None
            if not target.is_file():
                raise ToolError(NOT_FOUND)

            def read() -> tuple[int, bytes]:
                with target.open("rb") as f:
                    return target.stat().st_size, f.read(max_chars * 4)  # a character is up to four bytes

            size, data = await asyncio.to_thread(read)
            if b"\0" in data:
                raise ToolError("That is a binary file, not text")
            text = data.decode("utf-8", errors="replace")
            return FileContent(
                path=path,
                size=size,
                truncated=size > len(data) or len(text) > max_chars,
                text=text[:max_chars],
            )

    # global: the installation itself, for a connection made for all projects

    @tool
    async def get_settings() -> AppSettings:
        """Themis's global settings: cell defaults and size, the resource budget, Codex defaults, time zone, retry
        waits. Only for an administrator's connection."""
        async with acting() as (s, owner, caller):
            account_only(caller)
            await require_admin(owner)  # the route's own check is a dependency, which a direct call skips
            return await system.get_settings(s, owner)

    @tool
    async def get_system_status() -> SystemStatus:
        """How Themis is doing: the scheduler, whether cells can run, the version and, for an administrator, the
        problems it found."""
        async with acting() as (s, owner, caller):
            account_only(caller)
            # the handler only reads `request.app.state`, so the app stands in for the web request it expects
            return await system.system_status(SimpleNamespace(app=plane.app()), s, owner)

    @tool
    async def list_harnesses() -> list[HarnessOut]:
        """The agent engines Themis can run (Codex...) with the models and reasoning efforts each offers."""
        async with acting() as (s, owner, caller):
            account_only(caller)
            return await agents.list_harnesses(s, owner)

    @tool
    async def list_keys() -> list[KeyOut]:
        """The names of the stored keys and how an agent sees each one. Never their values."""
        async with acting() as (s, owner, caller):
            account_only(caller)
            return await tools.available_keys(s, owner)

    # actions: they change things, so they need a connection with permission to (see ControlPlane.write_tool)

    @write_tool
    async def create_task(task: TaskIn, project_id: ProjectId = None) -> TaskOut:
        """Make a task. Without a board_id it goes on the project's first board; the default status is Backlog, where
        nothing starts by itself, so give status 'ready' (or call run_task afterwards) to have it run."""
        async with acting() as (s, owner, caller):
            return await projects.create_task(project_of(caller, project_id), task, web_request(), s, owner)

    @write_tool
    async def update_task(task_id: int, changes: TaskPatch) -> TaskOut:
        """Change a task: only the fields given in `changes` are touched. A running task cannot be changed; cancel it
        first."""
        async with acting() as (s, owner, caller):
            await task_in_reach(s, owner, caller, task_id)
            return await projects.update_task(task_id, changes, web_request(), s, owner)

    @write_tool
    async def move_task(
        task_id: int,
        board_id: int,
        status: Annotated[
            str | None, Field(description="A status key of that board; left out: the same one, else Backlog")
        ] = None,
        position: float | None = None,
    ) -> TaskOut:
        """Send a task to a board of its project, and a status on it (moving it to 'ready' makes it run). The task is
        the same one, with its history."""
        async with acting() as (s, owner, caller):
            await task_in_reach(s, owner, caller, task_id)
            move = MoveIn(board_id=board_id, status=status, position=position)
            return await workspaces_router.move_task(task_id, move, web_request(), s, owner)

    @write_tool
    async def run_task(task_id: int) -> TaskOut:
        """Run a task now instead of waiting for its schedule. It is queued as ready and starts when the resource
        budget allows. Refused while the project or board is halted."""
        async with acting() as (s, owner, caller):
            await task_in_reach(s, owner, caller, task_id)
            return await projects.run_task_now(task_id, web_request(), s, owner)

    @write_tool
    async def cancel_task(task_id: int) -> TaskOut:
        """Stop a task that is running now."""
        async with acting() as (s, owner, caller):
            await task_in_reach(s, owner, caller, task_id)
            return await projects.cancel_task(task_id, web_request(), s, owner)

    @write_tool
    async def start_workflow_run(workflow_id: int) -> RunDetail:
        """Run a saved workflow now, from its Start nodes. get_workflow_run follows how far it gets."""
        async with acting() as (s, owner, caller):
            await workflow_in_reach(s, owner, caller, workflow_id)
            return await workflows.start_run(workflow_id, web_request(), s, owner)

    @write_tool
    async def cancel_workflow_run(run_id: int) -> RunDetail:
        """Stop a workflow run that is going."""
        async with acting() as (s, owner, caller):
            run = await workflows.get_run(run_id, s, owner)
            pinned(caller, run.project_id)
            return await workflows.cancel_run(run_id, web_request(), s, owner)

    @write_tool
    async def decide_approval(
        approval_id: int,
        approved: bool,
        note: Annotated[str, Field(max_length=2000, description="Why, shown with the answer")] = "",
    ) -> RunDetail:
        """Approve or reject a workflow step that waits for a person (list_approvals has them). The first answer
        stands and the run carries on, or the step fails, at once."""
        async with acting() as (s, owner, caller):
            node = await s.get(WorkflowNodeRun, approval_id)
            run = await s.get(WorkflowRun, node.run_id) if node else None
            if run is None:
                raise ToolError(NOT_FOUND)
            pinned(caller, run.project_id)
            await workflows.decide_approval(
                approval_id, workflows.DecisionIn(approved=approved, note=note), web_request(), s, owner
            )
            await s.commit()  # look again at what the engine wrote while carrying on
            return await workflows.get_run(run.id, s, owner)

    @write_tool
    async def halt_project(
        project_id: ProjectId = None,
        stop_running: Annotated[
            bool, Field(description="Also stop what is running now; false lets it finish")
        ] = True,
    ) -> ProjectOut:
        """Hold back everything in a project until resume_project. By default what is running is stopped too."""
        async with acting() as (s, owner, caller):
            found = await projects.halt_project(
                project_of(caller, project_id),
                projects.HaltIn(stop_running=stop_running),
                web_request(),
                s,
                owner,
            )
            return ProjectOut.model_validate(found)

    @write_tool
    async def resume_project(project_id: ProjectId = None) -> ProjectOut:
        """Let a halted project start work again."""
        async with acting() as (s, owner, caller):
            found = await projects.resume_project(project_of(caller, project_id), web_request(), s, owner)
            return ProjectOut.model_validate(found)

    async def board_in_reach(s, caller, board_id: int) -> None:
        board = await s.get(Board, board_id)
        if board is None:
            raise ToolError(NOT_FOUND)
        pinned(caller, board.project_id)

    @write_tool
    async def halt_board(
        board_id: int,
        stop_running: Annotated[
            bool, Field(description="Also stop what is running on it now; false lets it finish")
        ] = True,
    ) -> BoardOut:
        """Hold back everything on one board until resume_board. By default what is running on it is stopped too."""
        async with acting() as (s, owner, caller):
            await board_in_reach(s, caller, board_id)
            return await workspaces_router.halt_board(
                board_id, projects.HaltIn(stop_running=stop_running), web_request(), s, owner
            )

    @write_tool
    async def resume_board(board_id: int) -> BoardOut:
        """Let a halted board start work again."""
        async with acting() as (s, owner, caller):
            await board_in_reach(s, caller, board_id)
            return await workspaces_router.resume_board(board_id, web_request(), s, owner)
