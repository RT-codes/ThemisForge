from pydantic import BaseModel, Field


class SkillOut(BaseModel):
    name: str
    description: str
    files: int  # in its folder, SKILL.md included


class SkillDetail(SkillOut):
    content: str


class SkillIn(BaseModel):
    content: str = Field(max_length=400_000)
