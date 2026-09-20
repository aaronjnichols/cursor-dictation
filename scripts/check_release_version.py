from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

from cursor_dictation import __version__

_VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Release tag, such as v0.1.0")
    args = parser.parse_args()

    tag_version = args.tag.removeprefix("v")
    if _VERSION_PATTERN.fullmatch(tag_version) is None:
        raise SystemExit(f"Release tag must use vMAJOR.MINOR.PATCH: {args.tag}")

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    versions = {
        "release tag": tag_version,
        "pyproject.toml": project_version,
        "cursor_dictation.__version__": __version__,
    }
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{source}={version}" for source, version in versions.items())
        raise SystemExit(f"Release versions do not match: {details}")

    print(f"Release version verified: {tag_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
