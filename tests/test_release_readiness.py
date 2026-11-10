import json
from pathlib import Path

from scripts.release_readiness import build_report


def make_checkout(tmp_path: Path, *, version: str = "0.1.0") -> Path:
    files = {
        "VERSION": f"{version}\n",
        "pyproject.toml": f'[project]\nname = "atlas"\nversion = "{version}"\n',
        "apps/dashboard/package.json": json.dumps(
            {"name": "atlas-dashboard", "version": version}
        ),
        "CHANGELOG.md": "# Changelog\n",
        "LICENSE": "license\n",
        "README.md": "# ATLAS\n",
        "SECURITY.md": "# Security\n",
        "docs/release-checklist.md": "# Release checklist\n",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def fake_git(monkeypatch, *, status: str = ""):
    def run(root: Path, *args: str) -> str:
        if args[0] == "status":
            return status
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(args)

    monkeypatch.setattr("scripts.release_readiness._git", run)


def test_release_readiness_accepts_matching_clean_checkout(tmp_path, monkeypatch):
    root = make_checkout(tmp_path)
    fake_git(monkeypatch)

    report = build_report(root=root, tag="v0.1.0")

    assert report["ready"] is True
    assert all(report["checks"].values())
    assert report["expected_tag"] == "v0.1.0"
    assert report["commit_sha"] == "a" * 40


def test_release_readiness_reports_all_release_blockers(tmp_path, monkeypatch):
    root = make_checkout(tmp_path, version="01.2.3")
    (root / "apps/dashboard/package.json").write_text(
        json.dumps({"name": "atlas-dashboard", "version": "1.2.3"}),
        encoding="utf-8",
    )
    (root / "SECURITY.md").unlink()
    fake_git(monkeypatch, status="?? local-output.txt")

    report = build_report(root=root, tag="v1.2.3")

    assert report["ready"] is False
    assert report["checks"] == {
        "semantic_version": False,
        "version_surfaces_match": False,
        "required_files_present": False,
        "tag_matches_version": False,
        "working_tree_clean": False,
    }
    assert report["missing_files"] == ["SECURITY.md"]
    assert report["dirty_entries"] == ["?? local-output.txt"]


def test_release_readiness_can_ignore_local_changes(tmp_path, monkeypatch):
    root = make_checkout(tmp_path)
    fake_git(monkeypatch, status=" M README.md")

    report = build_report(root=root, require_clean=False)

    assert report["ready"] is True
    assert report["dirty_entries"] == []
