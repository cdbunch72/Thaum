#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# .release/generate_checksums.py
"""Write or verify GNU sha256sum files.

Source (default): SHA256SUMS.txt over runtime Python, scripts/, docker/,
Dockerfile, pyproject.toml, requirements.txt. Text mode (``HASH  PATH``):
CRLF/CR folded to LF before hashing so Windows generate / Linux verify agree.

Omitted from source sums: docs/, tests/, quickstart/, GitHub/release tooling.

Binary (``--binary`` plus explicit files): ``HASH *PATH`` of exact bytes,
for artifacts such as dist/thaum-utils-*.zip. Paths are relative to the
sumfile directory so ``sha256sum -c`` works next to the files.

Each file starts with ``#`` comment lines (version, UTC date, hashed-commit,
what is covered) that GNU ``sha256sum -c`` ignores (coreutils >= 8.31).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

SKIP_DIR_NAMES = frozenset({"__pycache__", ".git"})
SKIP_SUFFIXES = (".pyc", ".pyo", ".pyd")
PACKAGE_DIRS = ("thaum", "alerts", "bots", "connections", "lookup")
TREE_DIRS = PACKAGE_DIRS + ("scripts", "docker")
ROOT_FILES = ("Dockerfile", "pyproject.toml", "requirements.txt")
SUMS_NAME = "SHA256SUMS.txt"
LINE_RE = re.compile(r"^([0-9a-fA-F]{64}) ([ *])(.*)$")
SOURCE_COVERS = (
    "runtime Python (thaum/, alerts/, bots/, connections/, lookup/, "
    "and root *.py); scripts/; docker/; Dockerfile; pyproject.toml; "
    "requirements.txt"
)
SOURCE_OMITS = (
    "docs/, tests/, quickstart/, .github/, .release/, samples, "
    "and other repo metadata"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.endswith(".egg-info")


def iter_source_paths(root: Path) -> list[Path]:
    found: set[Path] = set()
    for name in ROOT_FILES:
        path = root / name
        if not path.is_file():
            raise SystemExit(f"missing required file: {name}")
        found.add(path)
    for py in sorted(root.glob("*.py")):
        if py.is_file():
            found.add(py)
    for dirname in TREE_DIRS:
        base = root / dirname
        if not base.is_dir():
            raise SystemExit(f"missing required directory: {dirname}")
        for path in base.rglob("*"):
            if path.is_dir():
                continue
            if any(_skip_dir(part) for part in path.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            if not path.is_file():
                continue
            found.add(path)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def file_sha256(path: Path, *, binary: bool) -> str:
    data = path.read_bytes()
    if not binary:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "git failed").strip()
        raise SystemExit(f"git rev-parse HEAD failed: {err}")
    sha = result.stdout.strip()
    if not sha:
        raise SystemExit("git rev-parse HEAD returned empty")
    return sha


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as fh:
        version = tomllib.load(fh)["project"]["version"]
    if not isinstance(version, str) or not version.strip():
        raise SystemExit("pyproject.toml [project].version is missing")
    return version.strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_header(
    *,
    label: str,
    version: str,
    date: str,
    hashed_commit: str,
    binary: bool,
    covers: str,
    file_count: int,
) -> str:
    """GNU sha256sum -c ignores '# ...' lines (coreutils >= 8.31)."""
    if binary:
        what = (
            "# This file checksums the exact bytes of the listed artifact(s)",
            "# next to this sumfile. It does not checksum git source or",
            "# SHA256SUMS.txt.",
        )
        mode = "binary (exact file bytes; GNU form HASH *PATH)"
        verify = "cd dist && sha256sum -c SHA256SUMS.zip"
        extra = [
            "# note: checksums the packaged zip, not git blobs.",
            "#   hashed-commit is the same generate-time HEAD as SHA256SUMS.txt.",
        ]
    else:
        what = (
            "# This file checksums committed Thaum source listed below.",
            "# It does not checksum this file, SHA256SUMS.txt.asc, the",
            "# thaum-utils zip, docs/, tests/, quickstart/, .github/,",
            "# .release/, samples, or other repo metadata.",
        )
        mode = (
            "text (CRLF/CR folded to LF before hashing; GNU form HASH  PATH)"
        )
        verify = "sha256sum -c SHA256SUMS.txt"
        extra = [
            f"# omits: {SOURCE_OMITS}",
            "# note: hashed-commit is git rev-parse HEAD when these hashes",
            "#   were generated (the tree whose files were hashed).",
            "#   The signed tag usually points at that commit, or at its",
            "#   child that only adds SHA256SUMS.txt and SHA256SUMS.txt.asc.",
        ]
    lines = [
        f"# Thaum {label}",
        "# GNU sha256sum -c ignores '#' comment lines (coreutils >= 8.31)",
        "#",
        *what,
        "#",
        f"# version: {version}",
        f"# date: {date}",
        f"# hashed-commit: {hashed_commit}",
        f"# files: {file_count}",
        f"# mode: {mode}",
        f"# covers: {covers}",
        *extra,
        f"# verify: {verify}",
        "#",
    ]
    return "\n".join(lines) + "\n"


def gnu_line(digest: str, rel: str, *, binary: bool) -> str:
    marker = "*" if binary else " "
    return f"{digest} {marker}{rel}"


def path_for_sumfile(path: Path, sums_path: Path) -> str:
    path = path.resolve()
    parent = sums_path.parent.resolve()
    try:
        return path.relative_to(parent).as_posix()
    except ValueError:
        return path.name


def format_source_sums(root: Path) -> str:
    lines: list[str] = []
    for path in iter_source_paths(root):
        rel = path.relative_to(root).as_posix()
        if rel in (SUMS_NAME, f"{SUMS_NAME}.asc"):
            continue
        lines.append(gnu_line(file_sha256(path, binary=False), rel, binary=False))
    if not lines:
        raise SystemExit("no files matched checksum coverage")
    return "\n".join(lines) + "\n"


def format_file_sums(paths: list[Path], sums_path: Path, *, binary: bool) -> str:
    lines: list[str] = []
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"not a file: {path}")
        rel = path_for_sumfile(path, sums_path)
        lines.append(gnu_line(file_sha256(path, binary=binary), rel, binary=binary))
    if not lines:
        raise SystemExit("no files to checksum")
    return "\n".join(lines) + "\n"


def parse_sums(text: str) -> list[tuple[str, bool, str]]:
    """Return (digest, binary, path) from GNU sha256sum text or binary lines."""
    rows: list[tuple[str, bool, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        if line.startswith("\\"):
            raise SystemExit(
                f"SHA256SUMS:{lineno}: escaped filenames are not supported"
            )
        match = LINE_RE.match(line)
        if not match:
            raise SystemExit(
                f"SHA256SUMS:{lineno}: expected GNU 'HASH  PATH' or 'HASH *PATH'"
            )
        digest, marker, rel = match.group(1), match.group(2), match.group(3)
        if not rel:
            raise SystemExit(f"SHA256SUMS:{lineno}: empty path")
        rows.append((digest.lower(), marker == "*", rel))
    return rows


def check_sums(root: Path, sums_path: Path, *, source: bool) -> int:
    if not sums_path.is_file():
        raise SystemExit(f"missing {sums_path}")
    listed = parse_sums(sums_path.read_text(encoding="utf-8"))
    ok = True
    seen: set[str] = set()
    for digest, binary, rel in listed:
        seen.add(rel)
        base = sums_path.parent if binary else root
        path = (base / rel)
        if not path.is_file():
            sys.stderr.write(f"MISSING  {rel}\n")
            ok = False
            continue
        actual = file_sha256(path, binary=binary)
        if actual != digest:
            sys.stderr.write(f"FAILED   {rel}\n")
            ok = False
        else:
            sys.stdout.write(f"OK       {rel}\n")
    if source:
        expected = {
            rel: digest
            for digest, _binary, rel in parse_sums(format_source_sums(root))
        }
        for rel in sorted(expected):
            if rel not in seen:
                sys.stderr.write(f"UNLISTED {rel}\n")
                ok = False
    if not ok:
        return 1
    sys.stderr.write(f"{len(listed)} files OK\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify GNU sha256sum files (text source or binary artifacts)."
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path (default: SHA256SUMS.txt in repo root for source)",
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Hash exact bytes and emit HASH *PATH (required for zip artifacts)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify --output against current files instead of rewriting",
    )
    parser.add_argument(
        "--version",
        default="",
        help="Release version for the header (default: pyproject.toml)",
    )
    parser.add_argument(
        "--date",
        default="",
        help="UTC timestamp for the header (default: now, YYYY-MM-DDTHH:MM:SSZ)",
    )
    parser.add_argument(
        "--hashed-commit",
        default="",
        help="git SHA whose files were hashed (default: git rev-parse HEAD)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Explicit files (use with --binary for dist/*.zip)",
    )
    args = parser.parse_args(argv)
    root = repo_root()
    if args.binary and not args.files and not args.check:
        raise SystemExit("--binary requires at least one file")
    if args.files and not args.binary and not args.check:
        raise SystemExit("explicit files require --binary (zip/artifacts)")

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
    else:
        output = root / SUMS_NAME

    if args.check:
        source = output.resolve() == (root / SUMS_NAME).resolve()
        return check_sums(root, output, source=source)

    output.parent.mkdir(parents=True, exist_ok=True)
    version = args.version.strip() or project_version(root)
    date = args.date.strip() or utc_now()
    hashed_commit = args.hashed_commit.strip() or git_head(root)
    if args.files:
        paths = [(root / f if not Path(f).is_absolute() else Path(f)) for f in args.files]
        covers = ", ".join(path_for_sumfile(p, output) for p in paths)
        body = format_file_sums(paths, output, binary=True)
        header = format_header(
            label=output.name,
            version=version,
            date=date,
            hashed_commit=hashed_commit,
            binary=True,
            covers=covers,
            file_count=sum(1 for line in body.splitlines() if line),
        )
        text = header + body
    else:
        body = format_source_sums(root)
        header = format_header(
            label=output.name,
            version=version,
            date=date,
            hashed_commit=hashed_commit,
            binary=False,
            covers=SOURCE_COVERS,
            file_count=sum(1 for line in body.splitlines() if line),
        )
        text = header + body
    output.write_text(text, encoding="utf-8", newline="\n")
    try:
        shown = output.relative_to(root).as_posix()
    except ValueError:
        shown = str(output)
    sys.stdout.write(f"wrote {shown}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # pragma: no cover
        sys.stderr.close()
        raise SystemExit(141)
