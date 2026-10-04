"""Build a reproducible source ZIP from an explicit reviewed public allowlist."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

VERSION = "0.2.2"
ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = (
    ".gitattributes",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    "README.md",
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "MANIFEST.in",
    "pyproject.toml",
    "requirements-dev.txt",
    "run_subtitle_search.bat",
    "examples/README.md",
    "examples/sample.srt",
    "src/subdav/__init__.py",
    "src/subdav/__main__.py",
    "src/subdav/app.py",
    "src/subdav/fcpxml.py",
    "src/subdav/library.py",
    "src/subdav/media.py",
    "src/subdav/models.py",
    "src/subdav/pairing.py",
    "src/subdav/srt.py",
    "src/subdav/store.py",
    "src/subdav/style.py",
    "src/subdav/table_sorting.py",
    "src/subdav/title_preview.py",
    "src/subdav/workflow.py",
    "tests/gui_helpers.py",
    "tests/test_app.py",
    "tests/test_distribution.py",
    "tests/test_fcpxml.py",
    "tests/test_media.py",
    "tests/test_pairing.py",
    "tests/test_srt.py",
    "tests/test_store.py",
    "tests/test_table_sorting.py",
    "tests/test_style.py",
    "tests/test_title_preview.py",
    "tests/test_workflow.py",
    "tests/test_security.py",
    "tests/test_release.py",
    "tests/test_privacy.py",
    "tools/make_release.py",
)


@lru_cache(maxsize=1)
def private_markers() -> tuple[bytes, ...]:
    values = {str(Path.home())}
    for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        if os.environ.get(key):
            values.add(os.environ[key])
    result = subprocess.run(
        ["git", "config", "--global", "--get", "user.email"],
        capture_output=True,
        text=True,
        check=False,
    )
    email = result.stdout.strip()
    if email and not email.endswith("@users.noreply.github.com"):
        values.add(email)
    expanded = set()
    for value in values:
        expanded.update((value, value.replace("\\", "/"), value.replace("\\", "\\\\")))
    return tuple(value.casefold().encode("utf-8") for value in expanded if len(value) > 5)


def audit_content(name: str, content: bytes) -> None:
    folded = content.lower()
    if any(marker in folded for marker in private_markers()):
        raise ValueError(f"Potential private local path/email in {name}")
    credential_patterns = (
        rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
        rb"AKIA[A-Z0-9]{16}",
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
    if any(re.search(pattern, content) for pattern in credential_patterns):
        raise ValueError(f"Potential credential in {name}")


def public_paths(root: Path) -> list[tuple[str, Path]]:
    root = root.resolve()
    paths = []
    for name in PUBLIC_FILES:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Public file must be a regular in-repository file: {name}")
        if not path.is_file():
            raise ValueError(f"Required public file is missing: {name}")
        audit_content(name, path.read_bytes())
        paths.append((name, path))
    return paths


def audit_git(root: Path) -> None:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    entries = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, blob, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if mode not in {"100644", "100755"} or stage != "0":
            raise ValueError(f"Non-regular or conflicted staged file: {name}")
        entries.append((name, blob))
    names = {name for name, _ in entries}
    unexpected = names - set(PUBLIC_FILES)
    if unexpected:
        raise ValueError("Unapproved tracked files: " + ", ".join(sorted(unexpected)))
    missing = set(PUBLIC_FILES) - names
    if missing:
        raise ValueError("Public files not staged/tracked: " + ", ".join(sorted(missing)))
    public_paths(root)
    for name, blob in entries:
        staged = subprocess.run(
            ["git", "cat-file", "blob", blob],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
        audit_content(name, staged)
        worktree = (root / name).read_bytes()
        if staged.replace(b"\r\n", b"\n") != worktree.replace(b"\r\n", b"\n"):
            raise ValueError(f"Staged/working content differs for {name}; stage the reviewed file")
    print(f"Privacy audit passed for {len(names)} tracked public files.")


def build_source_zip(root: Path, output: Path) -> Path:
    paths = public_paths(root)
    output = output.resolve()
    if output in {path.resolve() for _, path in paths}:
        raise ValueError("Archive output cannot replace a public source file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in paths:
            member = ZipInfo(f"subdav-{VERSION}/{name}")
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            member.compress_type = ZIP_DEFLATED
            archive.writestr(member, path.read_bytes(), compresslevel=9)
    with ZipFile(output) as archive:
        expected = {f"subdav-{VERSION}/{name}" for name in PUBLIC_FILES}
        if set(archive.namelist()) != expected or archive.testzip() is not None:
            raise ValueError("Release ZIP integrity/allowlist verification failed")
        for name in archive.namelist():
            audit_content(name, archive.read(name))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    print(f"Verified source ZIP: {len(paths)} public files; SHA256 {digest}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-git", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist" / f"subdav-{VERSION}-source.zip"
    )
    args = parser.parse_args()
    if args.audit_git:
        audit_git(ROOT)
    else:
        build_source_zip(ROOT, args.output)


if __name__ == "__main__":
    main()
