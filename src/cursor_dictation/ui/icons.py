from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from cursor_dictation.ui.theme import COLORS


def make_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(COLORS.raised))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.2, size * 0.2)

    amber_pen = QPen(QColor(COLORS.primary), max(2, size // 16))
    amber_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(amber_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(
        QRectF(size * 0.36, size * 0.17, size * 0.28, size * 0.45),
        size * 0.14,
        size * 0.14,
    )

    foreground_pen = QPen(QColor(COLORS.foreground), max(2, size // 16))
    foreground_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(foreground_pen)
    painter.drawArc(
        QRectF(size * 0.24, size * 0.35, size * 0.52, size * 0.42),
        180 * 16,
        180 * 16,
    )
    painter.drawLine(size // 2, int(size * 0.76), size // 2, int(size * 0.88))
    painter.drawLine(int(size * 0.38), int(size * 0.88), int(size * 0.62), int(size * 0.88))
    painter.end()
    return QIcon(pixmap)
