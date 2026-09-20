"""Capture actual overlay widgets in each palette, without recording audio."""

from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from cursor_dictation.core.models import AppState
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.theme import COLORS, build_stylesheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    for palette, title in (("warm_white", "Warm White"), ("chamber", "Chamber")):
        sheet = QImage(780, 780, QImage.Format.Format_ARGB32)
        sheet.fill(QColor(COLORS.background))
        painter = QPainter(sheet)
        painter.setPen(QColor(COLORS.foreground))
        painter.setFont(QFont("Segoe UI", 20))
        painter.drawText(42, 54, title)
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(COLORS.muted))
        painter.drawText(42, 82, "Actual UI captures enlarged 3x for pixel inspection")
        overlay = StatusOverlay()
        overlay.set_palette(palette)
        overlay._random.seed(17)
        for index, state in enumerate((AppState.RECORDING, AppState.TRANSCRIBING, AppState.IDLE)):
            overlay.set_state(state)
            overlay._elapsed_timer.stop()
            overlay._activity_timer.stop()
            if state is AppState.RECORDING:
                overlay.set_input_level(0.13)
                overlay._display_recording_time(12)
            elif state is AppState.TRANSCRIBING:
                for _ in range(10):
                    overlay._advance_activity()
            else:
                overlay.show_inserted(word_count=42)
                overlay._finish_completion_animation()
            overlay._dismiss_timer.stop()
            app.processEvents()
            capture = overlay.grab().toImage()
            capture.setDevicePixelRatio(1)
            capture.save(str(args.output / f"{palette}-{index + 1}.png"))
            enlarged = capture.scaled(
                690,
                144,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawImage(42, 110 + index * 160, enlarged)
        overlay.show_error("The recording did not produce any text")
        overlay._dismiss_timer.stop()
        app.processEvents()
        capture = overlay.grab().toImage()
        capture.setDevicePixelRatio(1)
        capture.save(str(args.output / f"{palette}-error.png"))
        enlarged = capture.scaled(
            690,
            144,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.drawImage(42, 590, enlarged)
        overlay.close()
        painter.end()
        sheet.save(str(args.output / f"{palette}-states.png"))


if __name__ == "__main__":
    main()
