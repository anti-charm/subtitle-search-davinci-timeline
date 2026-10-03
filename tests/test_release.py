"""Exercise the public archive boundary using synthetic private artifacts."""

import importlib.util
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def builder():
    script = ROOT / "tools" / "make_release.py"
    assert script.is_file(), "Release builder is missing"
    spec = importlib.util.spec_from_file_location("make_release", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_zip_excludes_unapproved_local_artifacts(tmp_path):
    release = builder()
    source = tmp_path / "source"
    source.mkdir()
    for name in release.PUBLIC_FILES:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for name in ("private.sqlite3", ".env", "private.srt", "video.mp4", "src/subdav/cache.pyc"):
        (source / name).write_bytes(b"private synthetic artifact")
    archive = release.build_source_zip(source, tmp_path / "public.zip")
    with ZipFile(archive) as z:
        names = z.namelist()
        assert len(names) == len(release.PUBLIC_FILES)
        assert all(name.removeprefix("subdav-0.2.1/") in release.PUBLIC_FILES for name in names)
        assert not any("private" in name or name.endswith(".pyc") for name in names)


def test_privacy_audit_rejects_local_path_and_token(tmp_path):
    release = builder()
    for value in (str(Path.home()), "ghp_" + "x" * 36):
        with pytest.raises(ValueError, match="private|credential"):
            release.audit_content("demo.py", value.encode())


def test_release_zip_is_reproducible(tmp_path):
    release = builder()
    first = release.build_source_zip(ROOT, tmp_path / "first.zip")
    second = release.build_source_zip(ROOT, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()


def test_git_audit_checks_staged_content_even_when_worktree_is_clean(tmp_path):
    release = builder()
    source = tmp_path / "source"
    source.mkdir()
    for name in release.PUBLIC_FILES:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    readme = source / "README.md"
    clean = readme.read_bytes()
    readme.write_text(str(Path.home()), encoding="utf-8")
    subprocess.run(["git", "add", "--all"], cwd=source, check=True, capture_output=True)
    readme.write_bytes(clean)
    with pytest.raises(ValueError, match="private"):
        release.audit_git(source)
