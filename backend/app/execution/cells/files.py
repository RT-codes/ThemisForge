import json
import os
from pathlib import Path

import app.execution.cell_package as package
import app.features.agents.skills as skill_store
from app.execution.cells.contract import CellSpec


def prepare_dirs(spec: CellSpec) -> None:
    spec.workspace_dir.mkdir(parents=True, exist_ok=True)
    spec.cell_dir.mkdir(parents=True, exist_ok=True)
    # A run that is started again after a provider error finds the folder of the one before it: what that run said
    # must not be mistaken for what this one says.
    for stale in ("result.md", "blocked.md"):
        (spec.cell_dir / stale).unlink(missing_ok=True)
    if spec.package_skill and not spec.skills_bundle:
        package.stage_skill(spec.package_skill)
    if spec.mounts_skills:
        skill_store.stage(spec.project_id, spec.skills, spec.skills_dir)
        if spec.skills_bundle:
            package.write_skill(spec.package_skill, spec.skills_dir)
        # the mountpoint, made as us
        (spec.workspace_dir / skill_store.mount_at(spec.harness).removeprefix("/workspace/")).mkdir(
            parents=True, exist_ok=True
        )
    for mount in spec.mounts:
        mount.source.mkdir(parents=True, exist_ok=True)
        # made here, as us: if Docker had to create the mountpoint it would belong to root
        (spec.workspace_dir / mount.name).mkdir(exist_ok=True)
    if spec.prompt:
        (spec.cell_dir / "prompt.md").write_text(spec.prompt, encoding="utf-8", newline="\n")
    (spec.cell_dir / "input.json").write_text(
        json.dumps(
            {
                "task_id": spec.task_id,
                "title": spec.title,
                "description": spec.description,
                "properties": spec.properties,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )


_UNTRACKED_DIRS = {*skill_store.MOUNTPOINT_DIRS, ".git", "node_modules"}


_MAX_TRACKED = 20_000  # a runaway tree must not make the start or end of a cell slow


_MAX_REPORTED = 100  # per kind, what is kept of a run's changes


def snapshot_workdir(spec: CellSpec) -> dict[str, tuple[int, int]]:
    """Every file in the working folder as {relative path: (size, mtime in ns)}, for telling what a cell changed.
    Blocking (a directory walk): call it from a thread."""
    root = spec.workspace_dir
    skip = _UNTRACKED_DIRS | {m.name for m in spec.mounts}
    out: dict[str, tuple[int, int]] = {}
    for base, dirs, files in os.walk(root):
        top = base == str(root)
        dirs[:] = [d for d in dirs if d not in _UNTRACKED_DIRS and not (top and d in skip)]
        for name in files:
            if len(out) >= _MAX_TRACKED:
                return out
            path = Path(base, name)
            try:
                st = path.lstat()
            except OSError:
                continue
            out[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def changes_between(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> dict:
    """What a cell added, changed and removed, longest lists cut to _MAX_REPORTED (`more` counts what was left out)."""
    added = sorted(p for p in after if p not in before)
    changed = sorted(p for p in after if p in before and after[p] != before[p])
    removed = sorted(p for p in before if p not in after)
    more = sum(max(0, len(x) - _MAX_REPORTED) for x in (added, changed, removed))
    return {
        "added": added[:_MAX_REPORTED],
        "changed": changed[:_MAX_REPORTED],
        "removed": removed[:_MAX_REPORTED],
        "more": more,
    }


def _read_cell_file(spec: CellSpec, name: str) -> str:
    path = spec.cell_dir / name
    return path.read_text(encoding="utf-8", errors="replace")[:100_000] if path.is_file() else ""


def read_result(spec: CellSpec) -> str:
    return _read_cell_file(spec, "result.md")


def read_blocked(spec: CellSpec) -> str:
    return _read_cell_file(spec, "blocked.md")
