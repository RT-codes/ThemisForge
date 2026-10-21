from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.agents.skills as store
import app.features.project_config.store as project_config
from app.errors import ApplicationError, invalid
from app.features.agents.skill_schemas import SkillDetail, SkillIn, SkillOut
from app.features.projects.access import require_project
from app.persistence.models import Agent, User


async def list_skills(project_id: int, session: AsyncSession, user: User) -> list[SkillOut]:
    await require_project(session, project_id, user)
    project_config.ensure_layout(project_id)  # also moves skills made before the config folder existed
    return [
        SkillOut(name=s.name, description=s.description, files=s.files) for s in store.list_skills(project_id)
    ]


async def get_skill(project_id: int, name: str, session: AsyncSession, user: User) -> SkillDetail:
    await require_project(session, project_id, user)
    try:
        content = store.read_skill(project_id, name)
    except store.SkillError as e:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, str(e)) from None
    info = next(s for s in store.list_skills(project_id) if s.name == name)
    return SkillDetail(name=name, description=info.description, files=info.files, content=content)


async def save_skill(
    project_id: int, name: str, body: SkillIn, session: AsyncSession, user: User
) -> SkillOut:
    """Creates the skill or replaces its SKILL.md."""
    await require_project(session, project_id, user)
    try:
        description = store.write_skill(project_id, name, body.content)
    except store.SkillError as e:
        raise invalid(str(e)) from None
    files = next(s.files for s in store.list_skills(project_id) if s.name == name)
    return SkillOut(name=name, description=description, files=files)


async def delete_skill(project_id: int, name: str, session: AsyncSession, user: User) -> None:
    """Removes the skill's folder, and the skill from the agents that had it."""
    await require_project(session, project_id, user)
    async with project_config.lock:
        try:
            store.delete_skill(project_id, name)
        except store.SkillError as e:
            raise ApplicationError(status.HTTP_404_NOT_FOUND, str(e)) from None
        changed = []
        for agent in await session.scalars(select(Agent).where(Agent.project_id == project_id)):
            if name in agent.skills:
                agent.skills = [n for n in agent.skills if n != name]
                changed.append(agent)
        await project_config.rewrite_agents(session, changed)  # their files list skills by name
        await session.commit()
