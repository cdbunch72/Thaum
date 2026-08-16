#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# .release/release_meta.py
"""Validate Thaum release pins and emit metadata for cut-release / CI.

Commands::

    python .release/release_meta.py 0.7.0rc2 --format env --notes-out dist/NOTES.md
    python .release/release_meta.py project --format json
    python .release/release_meta.py edge-tag --ref-name main
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

GEMSTONE_PIN_RE = re.compile(r"gemstone_utils==\s*([^#\s;\"']+)")
FINAL_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_pyproject(root: Path) -> dict:
    path = root / "pyproject.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)


def project_version(root: Path) -> str:
    version = load_pyproject(root)["project"]["version"]
    if not isinstance(version, str) or not version.strip():
        raise SystemExit("pyproject.toml [project].version is missing")
    return version.strip()


def gemstone_pin_from_text(text: str, label: str) -> str:
    match = GEMSTONE_PIN_RE.search(text)
    if not match:
        raise SystemExit(f"{label}: gemstone_utils== pin not found")
    return match.group(1)


def gemstone_pins(root: Path) -> tuple[str, str]:
    pyproject = gemstone_pin_from_text(
        (root / "pyproject.toml").read_text(encoding="utf-8"),
        "pyproject.toml",
    )
    requirements = gemstone_pin_from_text(
        (root / "requirements.txt").read_text(encoding="utf-8"),
        "requirements.txt",
    )
    return pyproject, requirements


def is_prerelease(version: str) -> bool:
    return FINAL_VERSION_RE.fullmatch(version) is None


def image_channel(version: str) -> str:
    return "devel" if is_prerelease(version) else "latest"


def extract_release_notes(root: Path, version: str) -> str:
    notes_path = root / "RELEASE_NOTES.md"
    text = notes_path.read_text(encoding="utf-8")
    heading_re = re.compile(rf"^## v{re.escape(version)}(?:\s|$)", re.M)
    match = heading_re.search(text)
    if not match:
        raise SystemExit(f"RELEASE_NOTES.md missing heading ## v{version}")
    start = match.start()
    rest = text[start:]
    next_heading = re.search(r"\n## ", rest)
    section = rest if next_heading is None else rest[: next_heading.start()]
    return section.strip() + "\n"


def validate_version(version: str) -> None:
    if not version or version.startswith(("v", "V")):
        raise SystemExit(
            "bare version required (e.g. 0.7.0rc2), without a leading v"
        )


def release_metadata(root: Path, version: str) -> dict[str, object]:
    validate_version(version)
    pinned = project_version(root)
    if pinned != version:
        raise SystemExit(f"pyproject.toml version {pinned!r} != {version!r}")
    py_pin, req_pin = gemstone_pins(root)
    if py_pin != req_pin:
        raise SystemExit(
            f"gemstone_utils pin mismatch: pyproject {py_pin} vs requirements {req_pin}"
        )
    extract_release_notes(root, version)
    prerelease = is_prerelease(version)
    return {
        "version": version,
        "tag": f"v{version}",
        "prerelease": prerelease,
        "gemstone_utils_ref": py_pin,
        "image_channel": image_channel(version),
    }


def project_metadata(root: Path) -> dict[str, object]:
    py_pin, req_pin = gemstone_pins(root)
    if py_pin != req_pin:
        raise SystemExit(
            f"gemstone_utils pin mismatch: pyproject {py_pin} vs requirements {req_pin}"
        )
    version = project_version(root)
    return {
        "version": version,
        "tag": f"v{version}",
        "prerelease": is_prerelease(version),
        "gemstone_utils_ref": py_pin,
        "image_channel": image_channel(version),
    }


def metadata_env(data: dict[str, object]) -> str:
    prerelease = "1" if data["prerelease"] else "0"
    return "\n".join(
        [
            f"THAUM_RELEASE_VERSION={data['version']}",
            f"THAUM_RELEASE_TAG={data['tag']}",
            f"THAUM_RELEASE_PRERELEASE={prerelease}",
            f"GEMSTONE_UTILS_REF={data['gemstone_utils_ref']}",
            f"THAUM_IMAGE_CHANNEL={data['image_channel']}",
        ]
    ) + "\n"


def edge_tag(ref_name: str) -> str:
    ref = (ref_name or "").strip()
    if ref == "main":
        return "edge"
    suffix = ref.lower().replace("/", "-")
    suffix = re.sub(r"[^a-z0-9._-]+", "-", suffix)
    suffix = re.sub(r"-+", "-", suffix).strip("-")
    if not suffix:
        suffix = hashlib.sha256(ref.encode()).hexdigest()[:12]
    max_suffix = 123
    if len(suffix) > max_suffix:
        suffix = suffix[:max_suffix]
    return f"edge-{suffix}"


def emit(data: dict[str, object], fmt: str) -> None:
    if fmt == "json":
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    sys.stdout.write(metadata_env(data))


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    data = release_metadata(root, args.version)
    if args.notes_out:
        notes_path = Path(args.notes_out)
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(extract_release_notes(root, args.version), encoding="utf-8")
    emit(data, args.format)
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    emit(project_metadata(repo_root()), args.format)
    return 0


def cmd_edge_tag(args: argparse.Namespace) -> int:
    ref = args.ref_name or os.environ.get("REF_NAME", "")
    if not str(ref).strip():
        raise SystemExit("edge-tag requires --ref-name or REF_NAME")
    sys.stdout.write(edge_tag(str(ref)) + "\n")
    return 0


def _add_format_notes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("env", "json"),
        default="env",
        help="stdout format (default: env)",
    )
    parser.add_argument(
        "--notes-out",
        metavar="PATH",
        help="Write the matching RELEASE_NOTES.md section to PATH",
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: release_meta.py <bare-version> [--format env|json] [--notes-out PATH]\n"
            "       release_meta.py validate <bare-version> [...]\n"
            "       release_meta.py project [--format env|json]\n"
            "       release_meta.py edge-tag --ref-name REF\n"
        )
        return 0 if argv and argv[0] in ("-h", "--help") else 2

    command = argv[0]
    rest = argv[1:]
    if command == "project":
        parser = argparse.ArgumentParser(prog="release_meta.py project")
        parser.add_argument(
            "--format",
            choices=("env", "json"),
            default="env",
            help="stdout format (default: env)",
        )
        return cmd_project(parser.parse_args(rest))
    if command == "edge-tag":
        parser = argparse.ArgumentParser(prog="release_meta.py edge-tag")
        parser.add_argument(
            "--ref-name",
            default="",
            help="Git ref name (branch). Also read from REF_NAME.",
        )
        return cmd_edge_tag(parser.parse_args(rest))
    if command == "validate":
        parser = argparse.ArgumentParser(prog="release_meta.py validate")
        parser.add_argument("version", help="Bare version (no leading v)")
        _add_format_notes(parser)
        return cmd_validate(parser.parse_args(rest))

    parser = argparse.ArgumentParser(prog="release_meta.py")
    parser.add_argument("version", help="Bare version (no leading v)")
    _add_format_notes(parser)
    return cmd_validate(parser.parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # pragma: no cover
        sys.stderr.close()
        raise SystemExit(141)
