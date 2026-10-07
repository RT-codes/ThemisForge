#!/usr/bin/env python3
"""Sets the version everywhere it is written: scripts/bump_version.py 0.2.0

The VERSION file is the truth (backend/app/version.py reads it); backend/pyproject.toml, frontend/package.json and
frontend/package-lock.json repeat it because their tools want it there, and a test fails when they disagree. Only the
standard library, so it runs anywhere. Afterwards run `uv lock` in backend/ so uv.lock follows.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def replace_first(path: Path, pattern: str, replacement: str, count: int = 1) -> None:
    text = path.read_text()
    new, n = re.subn(pattern, replacement, text, count=count, flags=re.MULTILINE)
    if n == 0:
        sys.exit(f"Could not find the version in {path.relative_to(ROOT)}")
    path.write_text(new)


def main(argv: list[str]) -> None:
    if len(argv) != 2 or not SEMVER.match(argv[1]):
        sys.exit(
            "Usage: scripts/bump_version.py MAJOR.MINOR.PATCH[-prerelease]   (for example 0.2.0 or 1.0.0-beta.1)"
        )
    version = argv[1]
    (ROOT / "VERSION").write_text(version + "\n")
    replace_first(ROOT / "backend" / "pyproject.toml", r'^version = "[^"]*"', f'version = "{version}"')
    replace_first(
        ROOT / "frontend" / "package.json", r'^(\s*)"version": "[^"]*"', rf'\1"version": "{version}"'
    )
    # the lock file names the version twice: at the top and under packages[""]
    replace_first(
        ROOT / "frontend" / "package-lock.json",
        r'^(\s*)"version": "[^"]*"',
        rf'\1"version": "{version}"',
        count=2,
    )
    print(f"Version is now {version}. Next: (cd backend && uv lock), commit, then tag v{version}.")


if __name__ == "__main__":
    main(sys.argv)
