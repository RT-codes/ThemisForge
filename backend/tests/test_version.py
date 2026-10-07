"""The version: one source of truth, readable by the app, and a release bundle that holds only what it should."""

import importlib.util
import json
import random
import re
import tomllib
from pathlib import Path

import pytest

from app import version as v

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ----- one version, written in four places that must agree -----


def test_every_file_that_repeats_the_version_agrees_with_the_version_file():
    truth = (ROOT / "VERSION").read_text().strip()
    assert v.SEMVER.match(truth), f"VERSION is not a version: {truth!r}"
    assert tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text())["project"]["version"] == truth
    assert json.loads((ROOT / "frontend" / "package.json").read_text())["version"] == truth
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    assert lock["version"] == truth and lock["packages"][""]["version"] == truth
    uv_lock = (ROOT / "backend" / "uv.lock").read_text()
    assert re.search(rf'name = "backend"\nversion = "{re.escape(truth)}"', uv_lock), (
        "run `uv lock` in backend/"
    )


def test_the_app_reads_the_version_file():
    info = v.build_info()
    assert info.release == (ROOT / "VERSION").read_text().strip()
    assert info.kind == "checkout" and info.version.startswith(
        f"{info.release}+dev"
    )  # a git checkout has no BUILD.json


def test_a_release_bundle_reports_its_build(tmp_path, monkeypatch):
    (tmp_path / "VERSION").write_text("1.2.3\n")
    (tmp_path / "BUILD.json").write_text(
        json.dumps({"version": "1.2.3", "commit": "abc", "built_at": "2026-01-01T00:00:00Z"})
    )
    monkeypatch.setattr(v, "VERSION_FILE", tmp_path / "VERSION")
    monkeypatch.setattr(v, "BUILD_FILE", tmp_path / "BUILD.json")
    v.build_info.cache_clear()
    try:
        info = v.build_info()
        assert (info.version, info.kind, info.commit, info.built_at) == (
            "1.2.3",
            "release",
            "abc",
            "2026-01-01T00:00:00Z",
        )
        (tmp_path / "VERSION").write_text("nonsense")  # a damaged file must not crash the app
        v.build_info.cache_clear()
        assert v.build_info().release == v.UNKNOWN
    finally:
        v.build_info.cache_clear()


def test_versions_are_ordered_the_way_semver_says():
    ordered = [
        "0.9.0",
        "0.10.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "2.0.0",
    ]
    shuffled = random.Random(7).sample(ordered, len(ordered))
    assert sorted(shuffled, key=v.sort_key) == ordered
    assert v.is_newer("1.10.0", "1.9.9") and not v.is_newer("1.0.0-rc.1", "1.0.0")
    assert v.is_newer("v1.0.1", "1.0.0")  # a tag name is accepted
    for bad in ("", "1.0", "1.0.0.0", "latest", "1.0.0-", "x.y.z"):
        with pytest.raises(ValueError):
            v.sort_key(bad)


async def test_the_version_is_public_like_the_health_check(client):
    assert (await client.get("/api/health")).json() == {"status": "ok", "version": v.build_info().version}
    body = (await client.get("/api/version")).json()
    assert body["release"] == (ROOT / "VERSION").read_text().strip() and body["kind"] == "checkout"


# ----- the release bundle -----


def test_the_bundle_never_holds_tests_data_or_secrets():
    build = load_script("build_release")
    for bad in (
        "backend/themisforge.db",
        "backend/.env",
        "backend/backups/x.db",
        "backend/app/__pycache__/a.pyc",
        "backend/.venv/bin/python",
        "a/b.log",
    ):
        assert not build.wanted(Path(bad)), bad
    for good in (
        "backend/app/main.py",
        "backend/.env.example",
        "frontend/dist/index.html",
        "backend/migrations/versions/0001_baseline.py",
    ):
        assert build.wanted(Path(good)), good
    assert not any("tests" in entry for entry in build.INCLUDE)


def test_the_bundle_is_assembled_from_a_built_interface(tmp_path):
    build = load_script("build_release")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        pytest.skip("the web interface is not built")
    import tarfile

    bundle, sums = build.build(tmp_path)
    version = (ROOT / "VERSION").read_text().strip()
    assert bundle.name == f"themisforge-{version}.tar.gz"
    with tarfile.open(bundle) as tar:
        names = tar.getnames()
        top = f"themisforge-{version}"
        assert {
            f"{top}/VERSION",
            f"{top}/BUILD.json",
            f"{top}/backend/uv.lock",
            f"{top}/frontend/dist/index.html",
        } <= set(names)
        assert not [n for n in names if "/tests/" in n or n.endswith((".db", ".env"))]
        assert json.load(tar.extractfile(f"{top}/BUILD.json"))["version"] == version
    digest, name = sums.read_text().split()
    assert name == bundle.name and len(digest) == 64


def test_bump_version_rewrites_each_file(tmp_path, monkeypatch):
    bump = load_script("bump_version")
    for rel, text in {
        "VERSION": "0.1.0\n",
        "backend/pyproject.toml": '[project]\nname = "backend"\nversion = "0.1.0"\n',
        "frontend/package.json": '{\n  "name": "f",\n  "version": "0.1.0"\n}\n',
        "frontend/package-lock.json": '{\n  "name": "f",\n  "version": "0.1.0",\n  "packages": {\n    "": {\n      "version": "0.1.0",\n      "dependencies": {"x": "^1.0.0"}\n    }\n  }\n}\n',
    }.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    monkeypatch.setattr(bump, "ROOT", tmp_path)
    bump.main(["bump", "0.2.0-beta.1"])
    assert (tmp_path / "VERSION").read_text() == "0.2.0-beta.1\n"
    assert 'version = "0.2.0-beta.1"' in (tmp_path / "backend/pyproject.toml").read_text()
    lock = json.loads((tmp_path / "frontend/package-lock.json").read_text())
    assert lock["version"] == lock["packages"][""]["version"] == "0.2.0-beta.1" and lock["packages"][""][
        "dependencies"
    ] == {"x": "^1.0.0"}
    with pytest.raises(SystemExit):
        bump.main(["bump", "1.0"])
