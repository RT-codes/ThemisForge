import asyncio
import os
from dataclasses import dataclass, field, replace

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.budget import Cost
from app.execution.cell_package import effective_rules, effective_skill
from app.execution.cells.contract import CellSpec, Mount, workdir_path
from app.execution.harnesses.prompts import EarlierStep, agent_preamble, build_prompt, workdir_note
from app.execution.harnesses.service import plan_for
from app.execution.harnesses.types import HarnessPlan
from app.execution.profiles import Profile, resolve_profile
from app.features.agents.skills import MOUNTPOINT_DIRS
from app.features.agents.skills import missing as missing_skills
from app.features.connections.service import RunConnection, plan_for_run
from app.features.project_config.store import sync_project
from app.features.storage.volumes import MountError, plan_mounts
from app.features.system.settings import AppSettings
from app.features.tools.auth import ACTIVE, login_for
from app.features.tools.keys import unique_env_names
from app.features.tools.mcp import McpSpec, login_env_name
from app.persistence.models import (
    Agent,
    Attempt,
    AttemptStatus,
    Connection,
    McpServer,
    Project,
    Secret,
    Task,
)


@dataclass
class RunPlan:
    """Everything decided about one task before its cell starts."""

    task: Task
    project: Project
    agent: Agent | None
    profile: Profile
    harness: HarnessPlan | None
    mounts: list[Mount]
    error: str = ""  # why it cannot run at all
    skills: list[str] = field(default_factory=list)
    mcp: list[McpSpec] = field(default_factory=list)
    keys: dict[int, str] = field(
        default_factory=dict
    )  # key id -> variable name, for the keys the agent is given
    connections: list[RunConnection] = field(default_factory=list)  # see app/features/connections/service.py
    connection_env: dict[str, str] = field(
        default_factory=dict
    )  # plain settings the connections give the cell
    connection_notes: list[str] = field(default_factory=list)  # what they tell the agent
    # The earlier attempt whose working folder this run continues in (None = a fresh folder of its own), and what the
    # agent is told about that folder (or about why it could not be continued)
    workdir_id: int | None = None
    workdir_note: str = ""

    @property
    def cost(self) -> Cost:
        return Cost(self.profile.cpus, self.profile.memory_mb)

    @property
    def locks(self) -> frozenset[int]:
        return frozenset(m.volume_id for m in self.mounts if m.lock)


class RunPlanner:
    async def plans(self, s: AsyncSession, tasks: list[Task], cfg: AppSettings) -> list[RunPlan]:
        """For each task: its agent, the cell it gets and the folders it mounts."""
        if not tasks:
            return []
        projects = {
            p.id: p
            for p in await s.scalars(select(Project).where(Project.id.in_({t.project_id for t in tasks})))
        }
        agent_ids = {t.agent_id for t in tasks if t.agent_id}
        for project_id in {t.project_id for t in tasks if t.agent_id}:
            # a run is planned from what the agent's file says right now (it may have been edited since the last look)
            await sync_project(s, project_id)
        agents = (
            {a.id: a for a in await s.scalars(select(Agent).where(Agent.id.in_(agent_ids)))}
            if agent_ids
            else {}
        )
        plans = []
        for task in tasks:
            if (project := projects.get(task.project_id)) is not None:
                plans.append(await self._plan(s, task, project, agents.get(task.agent_id or 0), cfg))
        return plans

    @staticmethod
    async def _plan(
        s: AsyncSession, task: Task, project: Project, agent: Agent | None, cfg: AppSettings
    ) -> RunPlan:
        harness = agent.harness if agent else task.harness
        skills, mcp, keys, error = await RunPlanner._capabilities(s, project, agent)
        used = await plan_for_run(s, project.id, agent, project.owner_id, harness)
        error = error or used.error
        secret_envs = {env for c in used.connections for env in c.env_names} | {
            spec.login_env for spec in mcp if spec.login_env
        }
        if clash := secret_envs & set(keys.values()):
            error = error or (
                f"A key of this agent is called {min(clash)}, which a connection of the agent already provides. "
                "Rename the key."
            )
        extra = task.run_options or {}
        # a workflow step may override the agent's model and effort for its own run (see Workflows._run_options)
        hp = plan_for(
            harness,
            cfg,
            model=extra.get("model") or (agent.model if agent else ""),
            effort=extra.get("effort") or (agent.reasoning_effort if agent else ""),
            key_envs=sorted(secret_envs | set(keys.values())),
        )
        if hp is not None and harness == "claude":
            hp = await RunPlanner._claude_billing(s, hp, used.connections)
        profile = resolve_profile(
            cfg,
            hp.image if hp else cfg.cell_image,
            project.cell_profile,
            agent.cell_profile if agent else None,
            extra.get("profile"),
        )
        plan = RunPlan(
            task,
            project,
            agent,
            profile,
            hp,
            [],
            error=error,
            skills=skills,
            mcp=mcp,
            keys=keys,
            connections=used.connections,
            connection_env=used.env,
            connection_notes=used.notes,
        )
        if (
            harness != "workflow" and not plan.error
        ):  # a task that plays a workflow starts no cell, so it mounts nothing
            try:
                refs = [*(agent.mounts if agent else []), *extra.get("mounts", [])]
                plan.mounts = await plan_mounts(s, project.id, refs, cfg)
            except MountError as e:
                plan.error = str(e)
            if wanted := extra.get("workdir"):
                plan.workdir_id, plan.workdir_note = await RunPlanner._continued_workdir(
                    s, project.id, int(wanted), plan.mounts
                )
        return plan

    @staticmethod
    async def _claude_billing(s: AsyncSession, hp: HarnessPlan, used: list[RunConnection]) -> HarnessPlan:
        """A Claude run is billed to the plan or to an API key, depending on which login it signs in with."""
        login = next((c for c in used if c.provider == "claude"), None)
        conn = await s.get(Connection, login.connection_id) if login else None
        return replace(hp, billing="api") if conn is not None and conn.settings.get("kind") == "api" else hp

    @staticmethod
    async def _continued_workdir(
        s: AsyncSession, project_id: int, wanted: int, mounts: list[Mount]
    ) -> tuple[int | None, str]:
        """The working folder of an earlier attempt that this run was asked to continue in, and the note that tells
        the agent what is in it. Only a folder of this project that is still on disk can be continued; otherwise the
        run starts fresh and says so, rather than failing a job over files that were pruned."""
        rows = (
            await s.execute(
                select(Attempt, Task.title)
                .join(Task, Task.id == Attempt.task_id)
                .where(
                    Task.project_id == project_id,
                    Task.harness != "workflow",  # a task that plays workflows ran no cell of its own
                    Attempt.status != AttemptStatus.RUNNING,
                    or_(Attempt.id == wanted, Attempt.workdir_id == wanted),
                )
                .order_by(Attempt.id)
            )
        ).all()
        folder = workdir_path(project_id, wanted)
        if not rows or not folder.is_dir():
            return None, (
                "The working folder of the earlier steps of this job is gone (working folders are removed after a "
                "retention period), so /workspace starts empty."
            )
        skip = {m.name for m in mounts} | MOUNTPOINT_DIRS

        def top_level() -> list[str]:
            names = sorted(n for n in os.listdir(folder) if n not in skip)
            return [n + "/" if (folder / n).is_dir() else n for n in names[:40]]

        steps = [EarlierStep(title, a.status, a.changes, a.result) for a, title in rows]
        return wanted, workdir_note(steps, await asyncio.to_thread(top_level))

    @staticmethod
    async def _capabilities(
        s: AsyncSession, project: Project, agent: Agent | None
    ) -> tuple[list[str], list[McpSpec], dict[int, str], str]:
        """What an agent is given besides its words: skills, tool servers and keys. Anything that was deleted since
        the agent was set up stops the run with a reason, instead of running without it."""
        if agent is not None and agent.config_error:
            return [], [], {}, f"The agent's file in the config folder has a problem: {agent.config_error}"
        if agent is None or not (agent.skills or agent.mcp_servers or agent.secrets):
            return [], [], {}, ""
        if gone := missing_skills(project.id, agent.skills):
            return [], [], {}, f"The skill '{gone[0]}' no longer exists. Check the agent's Skills."
        rows = []
        if agent.mcp_servers:
            rows = list(
                await s.scalars(
                    select(McpServer).where(
                        McpServer.project_id == project.id, McpServer.id.in_(agent.mcp_servers)
                    )
                )
            )
            if len(rows) != len(set(agent.mcp_servers)):
                return [], [], {}, "A tool server this agent uses no longer exists. Check the agent's Tools."
        specs = []
        for r in rows:
            login_id, login_env = None, ""
            if r.auth:
                # A tool that signs in runs as the project's owner, like their connections do. It is checked here,
                # before a cell is started, so what the person sees is "sign in", not a tool that fails inside a run.
                login = await login_for(s, project.owner_id, r.url)
                if login is None or login.status != ACTIVE:
                    why = f" ({login.error})" if login is not None and login.error else ""
                    return (
                        [],
                        [],
                        {},
                        (
                            f"The tool '{r.name}' needs a sign in{why}. "
                            "Open the project's Settings, under Tools, and press Sign in."
                        ),
                    )
                login_id, login_env = login.id, login_env_name(r.name)
            specs.append(
                McpSpec(
                    name=r.name,
                    kind=r.kind,
                    command=r.command,
                    args=tuple(r.args),
                    url=r.url,
                    env=dict(r.env),
                    secret_env=dict(r.secret_env),
                    bearer_secret_id=r.bearer_secret_id,
                    login_id=login_id,
                    login_env=login_env,
                )
            )
        wanted = set(agent.secrets) | {spec.bearer_secret_id for spec in specs if spec.bearer_secret_id}
        every = wanted | {i for spec in specs for i in spec.key_ids}
        found = (
            {x.id: x for x in await s.scalars(select(Secret).where(Secret.id.in_(every)))} if every else {}
        )
        if gone_keys := every - set(found):
            return (
                [],
                [],
                {},
                f"A key this agent uses no longer exists (key {min(gone_keys)}). Check its Keys and Tools.",
            )
        names = unique_env_names([(i, found[i].name) for i in sorted(every)])
        return list(agent.skills), specs, {i: names[i] for i in sorted(wanted)}, ""

    @staticmethod
    def spec(attempt_id: int, plan: RunPlan, cfg: AppSettings) -> CellSpec:
        task, project, agent, hp, profile = plan.task, plan.project, plan.agent, plan.harness, plan.profile
        prompt = ""
        if hp:
            prompt = build_prompt(
                task.title,
                task.description,
                task.properties,
                preamble=agent_preamble(agent.name, agent.role, agent.instructions) if agent else "",
                folders=[(m.name, m.read_only) for m in plan.mounts],
                notes=[*([plan.workdir_note] if plan.workdir_note else []), *plan.connection_notes],
                continuing=plan.workdir_id is not None,
                rules=effective_rules(cfg.cell_package),
            )
        return CellSpec(
            attempt_id=attempt_id,
            task_id=task.id,
            project_id=project.id,
            title=task.title,
            description=task.description,
            properties=task.properties,
            owner_id=project.owner_id,
            harness=agent.harness if agent else task.harness,
            image=profile.image,
            script=hp.script if hp else None,
            writeback=hp.writeback if hp else (),
            prompt=prompt,
            cpus=profile.cpus,
            memory_mb=profile.memory_mb,
            timeout_seconds=profile.timeout_seconds,
            docker_host=cfg.docker_host,
            mounts=plan.mounts,
            workdir_id=plan.workdir_id or attempt_id,
            skills=plan.skills,
            keys=plan.keys,
            mcp=plan.mcp,
            connections=plan.connections,
            env=dict(plan.connection_env),
            package_skill=effective_skill(cfg.cell_package) if hp else "",
        )
