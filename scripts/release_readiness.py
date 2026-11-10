"""Validate that a source checkout is ready for a versioned release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
REQUIRED_FILES = (
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "VERSION",
    "docs/release-checklist.md",
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8"
    ).strip()


def build_report(
    *,
    root: Path = ROOT,
    tag: str | None = None,
    require_clean: bool = True,
) -> dict:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dashboard = json.loads(
        (root / "apps/dashboard/package.json").read_text(encoding="utf-8")
    )
    expected_tag = f"v{version}"
    missing_files = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    surfaces = {
        "VERSION": version,
        "pyproject.toml": pyproject["project"]["version"],
        "apps/dashboard/package.json": dashboard["version"],
    }
    dirty_entries = _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()

    checks = {
        "semantic_version": bool(VERSION_PATTERN.fullmatch(version)),
        "version_surfaces_match": len(set(surfaces.values())) == 1,
        "required_files_present": not missing_files,
        "tag_matches_version": tag is None or tag == expected_tag,
        "working_tree_clean": not require_clean or not dirty_entries,
    }
    return {
        "schema_version": "atlas-release-readiness-v1",
        "ready": all(checks.values()),
        "version": version,
        "expected_tag": expected_tag,
        "requested_tag": tag,
        "commit_sha": _git(root, "rev-parse", "HEAD"),
        "checks": checks,
        "version_surfaces": surfaces,
        "missing_files": missing_files,
        "dirty_entries": dirty_entries if require_clean else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify ATLAS version and source-release invariants."
    )
    parser.add_argument("--tag", help="release tag to compare with VERSION")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="skip the clean-working-tree requirement for local diagnostics",
    )
    parser.add_argument("--output", type=Path, help="also write the JSON report")
    args = parser.parse_args()

    report = build_report(tag=args.tag, require_clean=not args.allow_dirty)
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
