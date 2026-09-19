from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QWidget

from cursor_dictation.core.models import AppState


class StatusOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._active = False
        self._state = AppState.STARTING
        self._elapsed = QElapsedTimer()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("overlayCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        self._waveform_label = QLabel("▁▁▁▁▁")
        self._waveform_label.setObjectName("statusWaveform")
        self._status_label = QLabel("Ready")
        self._elapsed_label = QLabel("")
        self._elapsed_label.setObjectName("muted")
        layout.addWidget(self._waveform_label)
        layout.addWidget(self._status_label)
        layout.addWidget(self._elapsed_label)
        outer.addWidget(card)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss_feedback)

    @property
    def status_text(self) -> str:
        return self._status_label.text()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def waveform_text(self) -> str:
        return self._waveform_label.text()

    def set_input_level(self, level: float) -> None:
        glyphs = "▁▂▃▄▅▆▇█"
        peak = round(max(0.0, min(1.0, level)) * (len(glyphs) - 1))
        indexes = (
            round(peak * 0.5),
            round(peak * 0.75),
            peak,
            round(peak * 0.75),
            round(peak * 0.5),
        )
        self._waveform_label.setText("".join(glyphs[index] for index in indexes))

    def set_state(self, state: AppState) -> None:
        self._state = state
        self._dismiss_timer.stop()
        if state is AppState.RECORDING:
            self._active = True
            self._status_label.setText("Recording...")
            self._elapsed_label.setText("0:00")
            self.set_input_level(0.0)
            self._elapsed.start()
            self._elapsed_timer.start()
            self._show_without_focus()
            return
        self._elapsed_timer.stop()
        self._elapsed_label.clear()
        if state is AppState.TRANSCRIBING:
            self._active = True
            self._status_label.setText("Transcribing locally...")
            self._show_without_focus()
        elif state is AppState.LOADING_MODEL:
            self._active = True
            self._status_label.setText("Loading local model...")
            self._show_without_focus()
        elif state is AppState.DELIVERING:
            self._active = True
            self._status_label.setText("Inserting text...")
            self._show_without_focus()
        elif state in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            self._active = True
            self._status_label.setText("Something went wrong")
            self._show_without_focus()
        else:
            self._active = False
            self._status_label.setText("Ready")
            self.hide()

    def show_busy(self) -> None:
        self._show_feedback("Transcribing...", 1600)

    def show_copied(self) -> None:
        self._show_feedback("Copied", 1600)

    def show_inserted(self) -> None:
        self._show_feedback("Inserted", 1200)

    def show_error(self, message: str) -> None:
        self._show_feedback(message, 3500)

    def _show_feedback(self, message: str, timeout_ms: int) -> None:
        self._elapsed_timer.stop()
        self._elapsed_label.clear()
        self._status_label.setText(message)
        self._active = True
        self._show_without_focus()
        if self._state not in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            self._dismiss_timer.start(timeout_ms)

    def _dismiss_feedback(self) -> None:
        if self._state in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            return
        if self._state is AppState.RECORDING:
            self._active = True
            self._status_label.setText("Recording...")
            self._update_elapsed()
            self._elapsed_timer.start()
            self._show_without_focus()
            return
        if self._state in {
            AppState.TRANSCRIBING,
            AppState.LOADING_MODEL,
            AppState.DELIVERING,
        }:
            self.set_state(self._state)
            return
        self._active = False
        self._status_label.setText("Ready")
        self._elapsed_label.clear()
        self.hide()

    def _show_without_focus(self) -> None:
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = area.center().x() - self.width() // 2
            y = area.bottom() - self.height() - 34
            self.move(x, y)
        self.show()

    def _update_elapsed(self) -> None:
        milliseconds = self._elapsed.elapsed()
        seconds = max(0, milliseconds // 1000)
        self._display_recording_time(seconds)

    def _display_recording_time(self, seconds: int) -> None:
        self._elapsed_label.setText(f"{seconds // 60}:{seconds % 60:02d}")
        if seconds >= 9 * 60:
            self._status_label.setText("Recording... 1 minute left")
        else:
            self._status_label.setText("Recording...")
