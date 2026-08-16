#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# .release/generate_checksums.py
"""Write or verify SHA256SUMS.txt for published Thaum source.

Covered: runtime Python packages and root modules, scripts/, docker/,
Dockerfile, pyproject.toml, requirements.txt.

Omitted: docs/, tests/, quickstart/, GitHub/release tooling, and other
repo metadata. SHA256SUMS.txt itself is never listed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

SKIP_DIR_NAMES = frozenset({"__pycache__", ".git"})
SKIP_SUFFIXES = (".pyc", ".pyo", ".pyd")
PACKAGE_DIRS = ("thaum", "alerts", "bots", "connections", "lookup")
TREE_DIRS = PACKAGE_DIRS + ("scripts", "docker")
ROOT_FILES = ("Dockerfile", "pyproject.toml", "requirements.txt")
SUMS_NAME = "SHA256SUMS.txt"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.endswith(".egg-info")


def iter_checksum_paths(root: Path) -> list[Path]:
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_sums(root: Path) -> str:
    lines: list[str] = []
    for path in iter_checksum_paths(root):
        rel = path.relative_to(root).as_posix()
        if rel in (SUMS_NAME, f"{SUMS_NAME}.asc"):
            continue
        lines.append(f"{file_sha256(path)}  {rel}")
    if not lines:
        raise SystemExit("no files matched checksum coverage")
    return "\n".join(lines) + "\n"


def write_sums(root: Path, output: Path) -> None:
    output.write_text(format_sums(root), encoding="utf-8", newline="\n")


def parse_sums(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        if "  " not in line:
            raise SystemExit(f"SHA256SUMS.txt:{lineno}: expected 'HASH  PATH'")
        digest, rel = line.split("  ", 1)
        if len(digest) != 64:
            raise SystemExit(f"SHA256SUMS.txt:{lineno}: not a SHA-256 hex digest")
        rows.append((digest.lower(), rel))
    return rows


def check_sums(root: Path, sums_path: Path) -> int:
    if not sums_path.is_file():
        raise SystemExit(f"missing {sums_path}")
    listed = parse_sums(sums_path.read_text(encoding="utf-8"))
    expected = {rel: digest for digest, rel in parse_sums(format_sums(root))}
    ok = True
    seen: set[str] = set()
    for digest, rel in listed:
        seen.add(rel)
        path = root / rel
        if not path.is_file():
            sys.stderr.write(f"MISSING  {rel}\n")
            ok = False
            continue
        actual = file_sha256(path)
        if actual != digest:
            sys.stderr.write(f"FAILED   {rel}\n")
            ok = False
        else:
            sys.stdout.write(f"OK       {rel}\n")
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
        description="Generate or verify SHA256SUMS.txt for published Thaum source."
    )
    parser.add_argument(
        "--output",
        default=SUMS_NAME,
        help="Output path (default: SHA256SUMS.txt in repo root)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify --output against current files instead of rewriting",
    )
    args = parser.parse_args(argv)
    root = repo_root()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    if args.check:
        return check_sums(root, output)
    write_sums(root, output)
    sys.stdout.write(f"wrote {output.relative_to(root).as_posix()}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # pragma: no cover
        sys.stderr.close()
        raise SystemExit(141)
