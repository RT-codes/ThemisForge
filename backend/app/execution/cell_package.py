"""The Themis package: what Themis puts into every Codex cell by itself, besides what the agent was given.

Two parts, each of which an administrator can read, edit or switch off in Settings (see CellPackage in
app_settings.py):

- the **rules**, a few lines in every prompt: what the container is, and to stop and say why in /cell/blocked.md instead
  of inventing a way around something that is missing. The agent cannot be left to decide to read these, so they are
  in the prompt itself.
- the **skill** `themis-cell`, a map of what the image has installed. Codex lists only its one-line description and
  reads the rest when it is needed, so it costs a few tokens until it is useful.

Empty text in the settings means the built-in text below, so a better built-in text still reaches an installation that
never edited it. The skill is staged once into a folder of Themis's own and mounted read only at the place Codex reads
administrator skills from, so it is the same for every agent and an agent cannot change it.
"""

import os
from pathlib import Path

from app.config import settings
from app.features.system.settings import CellPackage

SKILLS_MOUNT_AT = "/etc/codex/skills"

SKILL_NAME = "themis-cell"
# Where Codex looks for skills that apply to everyone (checked against the real CLI: it lists them as "admin" scope).

# Every agent gets these few lines, so it stops and says what is missing instead of inventing its own way around it
# (installing system packages, working around permissions, quietly doing a different job). Keep it short: it is in the
# context of every run. The file is the contract in app/execution/cells/manager.py, read back by harness.parse_blocked.
DEFAULT_RULES = (
    "This container has no root and no package manager access, only the tools already in it. If the task cannot be "
    "done because something is missing or unclear (a tool, a key, a folder, access, an instruction), do not invent a "
    "workaround: finish what does not depend on it, then write /cell/blocked.md as two lines, "
    "`Reason: <what is missing, one sentence>` and `Fix: <what the person should change>`, and stop."
)

# Describes the image in docker/cell, so change them together (a test checks the browser path).
DEFAULT_SKILL = """\
---
name: themis-cell
description: What this cell has installed (git, ripgrep, gh, node, uv, Chromium) and what it does not (root, apt). Read it before installing anything, running a browser or taking a screenshot.
---

# This cell

You run as a normal user in a throwaway container. There is no root, no sudo and no apt, so do not try to install
system packages or work around that. Work with what is here, and if something required is missing, stop and say so in
`/cell/blocked.md` (see the task's instructions).

## Installed

- git, ripgrep (`rg`), curl, GitHub CLI (`gh`, signed in only when the agent has a GitHub connection)
- Node 22 with `npm` and `npx`
- `uv` and `uvx`; Python is downloaded by uv the first time it is needed
- Chromium at `/usr/bin/chromium`

## What you can add without root

`npm install` in `/workspace`, `npx`, `uvx` and `uv pip` work. Anything outside `/workspace` and the shared folders is
gone when the run ends, and `HOME` is `/tmp`.

## Screenshots and browsers

Use the installed Chromium. Do not run `playwright install`: it downloads a second copy that this cell does not need.

One page, no code:

    chromium --headless=new --no-sandbox --disable-gpu --window-size=1280,800 \\
      --screenshot=/workspace/shot.png http://localhost:5173

Scripted, with Playwright (`npm install playwright` first, nothing else to download):

    const browser = await chromium.launch({
      executablePath: '/usr/bin/chromium',
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    })

Put screenshots in `/workspace`, or in a shared folder when another run needs them.
"""


def effective_rules(package: CellPackage) -> str:
    """The rules text for the prompt: the edited one, the built-in one, or nothing when they are switched off."""
    if not package.rules_enabled:
        return ""
    return package.rules.strip() or DEFAULT_RULES


def effective_skill(package: CellPackage) -> str:
    """The text of the themis-cell skill, or nothing when it is switched off."""
    if not package.skill_enabled:
        return ""
    edited = package.skill.strip()
    return f"{edited}\n" if edited else DEFAULT_SKILL


def skills_root() -> Path:
    """The host folder that is mounted at SKILLS_MOUNT_AT. One for the installation, not one per run: it holds nothing
    that differs between runs, and it lives outside every run's /cell so no agent can write to it."""
    return settings.data_dir / "cell-package" / "skills"


def write_skill(text: str, folder: Path) -> None:
    """Put the skill in `folder` (the run's own skills folder, see CellSpec.skills_bundle)."""
    (folder / SKILL_NAME).mkdir(parents=True, exist_ok=True)
    (folder / SKILL_NAME / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")


def stage_skill(text: str) -> None:
    """Make skills_root() hold exactly this skill. Replaced atomically, because cells may be reading it as it changes."""
    target = skills_root() / SKILL_NAME / "SKILL.md"
    if target.is_file() and target.read_text(encoding="utf-8") == text:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(f"SKILL.md.{os.getpid()}.tmp")
    scratch.write_text(text, encoding="utf-8", newline="\n")
    scratch.replace(target)
