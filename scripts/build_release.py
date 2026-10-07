#!/usr/bin/env python3
"""Builds the release bundle: scripts/build_release.py [--out dist] [--expect-tag v0.2.0]

The bundle is what `themis install` and `themis upgrade` download. It holds the backend source with its lock file (the
dependencies are installed on the user's machine by uv, which picks the right wheels for its system, so one bundle
serves Linux and Windows on any CPU), the prebuilt web interface (so nobody needs Node), and the files an installer
needs. It does NOT hold tests, a virtualenv, a database or a .env.

    dist/themisforge-<version>.tar.gz      the bundle (one top folder, themisforge-<version>/)
    dist/SHA256SUMS                        its checksum, which the installer verifies

Only the standard library, so it runs the same on a laptop and in CI. Build the web interface first
(cd frontend && npm ci && npm run build); this script checks that it is there and fresh enough to be real.
"""

import argparse
import datetime
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

# What goes in, relative to the repository root (a folder brings everything under it that is not excluded below).
INCLUDE = [
    "VERSION",
    "LICENSE",
    "NOTICE",
    "README.md",
    "backend/app",
    "backend/migrations",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/.env.example",
    "frontend/dist",
    "docker/cell-codex",
]
# Names that never go in, wherever they are: caches, local state, and anything that could hold someone's data.
EXCLUDE_NAMES = {"__pycache__", ".venv", ".pytest_cache", ".ruff_cache", "backups", ".env", ".DS_Store"}
EXCLUDE_SUFFIXES = (".pyc", ".db", ".db-shm", ".db-wal", ".db-journal", ".sqlite", ".sqlite3", ".log")


def wanted(path: Path) -> bool:
    """Whether a file under an included folder belongs in the bundle."""
    parts = set(path.parts)
    return not (parts & EXCLUDE_NAMES) and not path.name.endswith(EXCLUDE_SUFFIXES)


def files_to_pack(root: Path = ROOT) -> list[Path]:
    """Every file for the bundle as a path relative to `root`, in a fixed order so the same input gives the same bundle."""
    found: list[Path] = []
    for entry in INCLUDE:
        path = root / entry
        if path.is_file():
            found.append(Path(entry))
        elif path.is_dir():
            found += [
                p.relative_to(root)
                for p in sorted(path.rglob("*"))
                if p.is_file() and wanted(p.relative_to(root))
            ]
        else:
            raise SystemExit(
                f"Missing from the repository: {entry}"
                + (" (build the web interface first)" if "dist" in entry else "")
            )
    return found


def commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5, check=False
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def build(out_dir: Path, built_at: datetime.datetime | None = None) -> tuple[Path, Path]:
    version = (ROOT / "VERSION").read_text().strip()
    if not SEMVER.match(version):
        raise SystemExit(f"VERSION is not a version: {version!r}")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit(
            "The web interface is not built: run (cd frontend && npm ci && npm run build) first."
        )
    built_at = built_at or datetime.datetime.now(datetime.UTC)
    stamp = int(built_at.timestamp())
    top = f"themisforge-{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / f"{top}.tar.gz"
    build_info = (
        json.dumps(
            {"version": version, "commit": commit(), "built_at": built_at.strftime("%Y-%m-%dT%H:%M:%SZ")},
            indent=2,
        )
        + "\n"
    )

    def add_file(tar: tarfile.TarFile, name: str, data: bytes, mode: int = 0o644) -> None:
        info = tarfile.TarInfo(f"{top}/{name}")
        info.size, info.mtime, info.mode = len(data), stamp, mode
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        tar.addfile(info, io.BytesIO(data))

    # gzip with a fixed timestamp (mtime=0), so the same files always give the same bytes
    with (
        bundle.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for rel in files_to_pack():
            data = (ROOT / rel).read_bytes()
            executable = (ROOT / rel).stat().st_mode & 0o111 != 0
            add_file(tar, rel.as_posix(), data, 0o755 if executable else 0o644)
        add_file(tar, "BUILD.json", build_info.encode())

    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    sums = out_dir / "SHA256SUMS"
    sums.write_text(f"{digest}  {bundle.name}\n")
    return bundle, sums


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ThemisForge release bundle.")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "dist", help="where to write the bundle (default: dist/)"
    )
    parser.add_argument(
        "--expect-tag",
        help="fail unless this tag (v0.2.0) matches the VERSION file; CI passes the tag it was started by",
    )
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    if args.expect_tag and args.expect_tag != f"v{version}":
        sys.exit(
            f"The tag {args.expect_tag} does not match VERSION ({version}). Bump the version, commit, and tag again."
        )
    bundle, sums = build(args.out)
    print(f"{bundle} ({bundle.stat().st_size / 1_000_000:.1f} MB)")
    print(sums.read_text().strip())


if __name__ == "__main__":
    main()
