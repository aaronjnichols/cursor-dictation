from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundled_root, str):
        return Path(bundled_root)
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)
