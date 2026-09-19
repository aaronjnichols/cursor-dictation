from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    source = project_root / "assets" / "icons" / "cursor-dictation.svg"
    destination = project_root / "assets" / "icons" / "cursor-dictation.ico"
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"Could not load {source}")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    if not image.save(str(destination), "ICO"):
        raise RuntimeError(f"Could not write {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
