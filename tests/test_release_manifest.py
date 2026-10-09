import hashlib
import json
import tomllib

from scripts.release_manifest import ROOT, build_manifest, project_version


def test_release_manifest_records_version_commit_and_tracked_files():
    manifest = build_manifest(generated_at="2026-10-09T00:00:00Z")

    assert manifest["schema_version"] == "atlas-release-manifest-v1"
    assert manifest["version"] == project_version() == "0.1.0"
    assert len(manifest["commit_sha"]) == 40
    assert manifest["generated_at"] == "2026-10-09T00:00:00Z"

    version = next(item for item in manifest["files"] if item["path"] == "VERSION")
    content = (ROOT / "VERSION").read_bytes()
    assert version == {
        "path": "VERSION",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def test_release_manifest_paths_are_unique_and_sorted():
    paths = [item["path"] for item in build_manifest()["files"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))


def test_runtime_image_includes_version_file():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY VERSION VERSION" in dockerfile


def test_all_published_version_surfaces_match():
    version = project_version()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dashboard = json.loads(
        (ROOT / "apps/dashboard/package.json").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["version"] == version
    assert dashboard["version"] == version
