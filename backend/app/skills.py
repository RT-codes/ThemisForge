"""Skills: folders with a SKILL.md that an agent can be given.

A skill lives at data/projects/<project id>/config/skills/<name>/SKILL.md (in the project's config folder, which the
Files page shows). The folder may also hold scripts or reference files
(put there on disk); the app edits SKILL.md and carries the rest along. Each run copies the agent's skills into a
folder of their own that is mounted read only at /workspace/.agents/skills, where Codex looks for them, so an agent
only sees the skills it was given and cannot change them.
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import settings

SKILL_FILE = "SKILL.md"
MAX_SKILL_BYTES = 100_000
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MOUNT_AT = (
    "/workspace/.agents/skills"  # one of the places Codex looks for skills (checked against the real CLI)
)


class SkillError(Exception):
    """A skill cannot be saved or used. The message is meant for the person editing it."""


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    files: int  # how many files the folder holds, SKILL.md included


def skills_dir(project_id: int) -> Path:
    return settings.project_dir(project_id) / "config" / "skills"


def skill_dir(project_id: int, name: str) -> Path:
    if not NAME.match(name):
        raise SkillError(
            "A skill name uses lowercase letters, digits and dashes, and starts with a letter or digit"
        )
    return skills_dir(project_id) / name


def parse_frontmatter(text: str) -> dict[str, str]:
    """The `key: value` lines between the two --- lines at the top of a SKILL.md (a small subset of YAML: plain or
    quoted values, and a `>` or `|` block for a longer one)."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError(
            "The file must start with a --- line, then name and description, then another --- line"
        )
    out: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            value = value.strip()
            if value in {">", ">-", "|", "|-"}:
                block = []
                while i + 1 < len(lines) and (
                    lines[i + 1].startswith((" ", "\t")) or not lines[i + 1].strip()
                ):
                    i += 1
                    block.append(lines[i].strip())
                value = " ".join(b for b in block if b)
            elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            out[key.strip()] = value
        i += 1
    if i >= len(lines):
        raise SkillError("The first --- line is never closed: add a --- line after the description")
    return out


def validate(name: str, content: str) -> str:
    """Checks a SKILL.md for this skill name and returns its description."""
    if len(content.encode()) > MAX_SKILL_BYTES:
        raise SkillError(f"A skill can be at most {MAX_SKILL_BYTES // 1000} KB")
    meta = parse_frontmatter(content)
    if meta.get("name") != name:
        raise SkillError(f"The name in the file ({meta.get('name') or 'missing'}) must be {name}")
    if not meta.get("description"):
        raise SkillError("Add a description: it is how the agent decides when to use the skill")
    return meta["description"]


def list_skills(project_id: int) -> list[SkillInfo]:
    root = skills_dir(project_id)
    out = []
    for folder in sorted(root.iterdir()) if root.is_dir() else []:
        path = folder / SKILL_FILE
        if not folder.is_dir() or not NAME.match(folder.name) or not path.is_file():
            continue
        try:
            description = parse_frontmatter(path.read_text(errors="replace")).get("description", "")
        except SkillError:
            description = ""  # a broken file is still listed, so it can be opened and fixed
        out.append(SkillInfo(folder.name, description, sum(1 for f in folder.rglob("*") if f.is_file())))
    return out


def read_skill(project_id: int, name: str) -> str:
    path = skill_dir(project_id, name) / SKILL_FILE
    if not path.is_file():
        raise SkillError("That skill does not exist")
    return path.read_text(errors="replace")


def write_skill(project_id: int, name: str, content: str) -> str:
    description = validate(name, content)
    folder = skill_dir(project_id, name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SKILL_FILE).write_text(content)
    return description


def delete_skill(project_id: int, name: str) -> None:
    folder = skill_dir(project_id, name)
    if not (folder / SKILL_FILE).is_file():
        raise SkillError("That skill does not exist")
    shutil.rmtree(folder)  # name is a checked slug, so this cannot leave the skills folder


def missing(project_id: int, names: list[str]) -> list[str]:
    return [n for n in names if not NAME.match(n) or not (skills_dir(project_id) / n / SKILL_FILE).is_file()]


def stage(project_id: int, names: list[str], dest: Path) -> None:
    """Copies the named skills into dest, which a run mounts read only. Starts from an empty folder."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in names:
        shutil.copytree(skill_dir(project_id, name), dest / name, symlinks=False)
