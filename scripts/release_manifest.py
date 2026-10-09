"""Create a machine-readable manifest for an ATLAS source release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def project_version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode("utf-8")
    return [ROOT / name for name in output.split("\0") if name]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(*, generated_at: str | None = None) -> dict:
    files = tracked_files()
    return {
        "schema_version": "atlas-release-manifest-v1",
        "version": project_version(),
        "commit_sha": _git("rev-parse", "HEAD"),
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in files
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_manifest(generated_at=args.generated_at), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
