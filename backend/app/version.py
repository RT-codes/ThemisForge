"""Which version of Themis this is.

One source of truth: the VERSION file at the root of the repository (and of every release bundle), bumped with
scripts/bump_version.py so pyproject.toml and package.json follow. A release bundle also carries BUILD.json (written by
scripts/build_release.py) with the commit it was built from. A git checkout has no BUILD.json, so its version is shown
as "0.1.0+dev.<commit>" and a person reading a bug report can tell the two apart.
"""

import functools
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import BACKEND_DIR

ROOT = BACKEND_DIR.parent
VERSION_FILE = ROOT / "VERSION"
BUILD_FILE = ROOT / "BUILD.json"
UNKNOWN = "0.0.0"

# MAJOR.MINOR.PATCH with an optional pre-release part, such as 1.4.0-beta.2 (https://semver.org)
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


@dataclass(frozen=True)
class BuildInfo:
    version: str  # what to show: "0.1.0" for a release, "0.1.0+dev.abc1234" for a checkout
    release: str  # the number alone, "0.1.0"
    commit: str  # "" when unknown
    built_at: str  # ISO time of the release build, "" for a checkout
    kind: str  # "release" | "checkout"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


@functools.cache
def build_info() -> BuildInfo:
    try:
        release = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        release = UNKNOWN
    if not SEMVER.match(release):
        release = UNKNOWN
    try:
        build = json.loads(BUILD_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        build = None
    if isinstance(build, dict):
        return BuildInfo(
            version=release,
            release=release,
            commit=str(build.get("commit", "")),
            built_at=str(build.get("built_at", "")),
            kind="release",
        )
    commit = _git_commit()
    return BuildInfo(
        version=f"{release}+dev.{commit}" if commit else f"{release}+dev",
        release=release,
        commit=commit,
        built_at="",
        kind="checkout",
    )


def sort_key(version: str) -> tuple:
    """Orders versions the way semver says: 1.0.0-beta.2 < 1.0.0-rc.1 < 1.0.0, and 1.9.0 < 1.10.0.

    Raises ValueError for something that is not a version, so a bad answer from upstream is never compared."""
    m = SEMVER.match(version.strip().removeprefix("v"))
    if not m:
        raise ValueError(f"Not a version: {version!r}")
    major, minor, patch, pre = m.groups()
    if pre is None:
        return (int(major), int(minor), int(patch), 1, ())  # a release sorts after its pre-releases
    parts = tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")
    )  # numbers before words
    return (int(major), int(minor), int(patch), 0, parts)


def is_newer(candidate: str, current: str) -> bool:
    return sort_key(candidate) > sort_key(current)


def read_release_file(path: Path = VERSION_FILE) -> str:
    return path.read_text(encoding="utf-8").strip()
