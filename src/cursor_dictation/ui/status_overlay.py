from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QElapsedTimer, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cursor_dictation.core.models import AppState
from cursor_dictation.ui.theme import COLORS

_CHECK_CELLS = frozenset(
    {
        (5, 0),
        (6, 0),
        (5, 1),
        (6, 1),
        (4, 2),
        (5, 2),
        (0, 3),
        (1, 3),
        (3, 3),
        (4, 3),
        (1, 4),
        (2, 4),
        (3, 4),
        (2, 5),
    }
)

_CHECK_SEQUENCE = (
    (0, 3),
    (1, 3),
    (1, 4),
    (2, 4),
    (2, 5),
    (3, 4),
    (3, 3),
    (4, 3),
    (4, 2),
    (5, 2),
    (5, 1),
    (5, 0),
    (6, 1),
    (6, 0),
)


class _TerminalPanel(QWidget):
    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        width = float(self.width() - 1)
        height = float(self.height() - 1)
        cut = 5.0
        shape = QPolygonF(
            (
                QPointF(0.5, 0.5),
                QPointF(width - cut, 0.5),
                QPointF(width, cut),
                QPointF(width, height),
                QPointF(cut, height),
                QPointF(0.5, height - cut),
            )
        )
        painter.setBrush(QColor(COLORS.popover))
        painter.setPen(QPen(QColor(COLORS.border), 1.0))
        painter.drawPolygon(shape)


class _BlockGrid(QWidget):
    def __init__(
        self,
        columns: int,
        rows: int,
        *,
        cell_width: int,
        cell_height: int,
        gap: int,
    ) -> None:
        super().__init__()
        self.setObjectName("overlayVisual")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._columns = columns
        self._rows = rows
        self._cell_width = cell_width
        self._cell_height = cell_height
        self._gap = gap
        self._orange_cells: frozenset[tuple[int, int]] = frozenset()
        self._green_cells: frozenset[tuple[int, int]] = frozenset()
        self.setFixedSize(self.sizeHint())

    @property
    def grid_size(self) -> tuple[int, int]:
        return self._columns, self._rows

    @property
    def orange_cells(self) -> frozenset[tuple[int, int]]:
        return self._orange_cells

    @property
    def green_cells(self) -> frozenset[tuple[int, int]]:
        return self._green_cells

    def set_cells(
        self,
        *,
        orange: frozenset[tuple[int, int]] = frozenset(),
        green: frozenset[tuple[int, int]] = frozenset(),
    ) -> None:
        self._orange_cells = orange
        self._green_cells = green
        self.update()

    def sizeHint(self) -> QSize:
        width = self._columns * self._cell_width + (self._columns - 1) * self._gap
        height = self._rows * self._cell_height + (self._rows - 1) * self._gap
        return QSize(width, height)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        for row in range(self._rows):
            for column in range(self._columns):
                cell = (column, row)
                if cell in self._green_cells:
                    color = COLORS.success
                elif cell in self._orange_cells:
                    color = COLORS.primary
                else:
                    color = COLORS.inactive
                x = column * (self._cell_width + self._gap)
                y = row * (self._cell_height + self._gap)
                painter.fillRect(x, y, self._cell_width, self._cell_height, QColor(color))


def _visual_host(widget: QWidget) -> QWidget:
    host = QWidget()
    host.setObjectName("overlayVisualHost")
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignCenter)
    return host


class StatusOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("statusOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._active = False
        self._state = AppState.STARTING
        self._status_text = "Ready"
        self._visual_mode = "none"
        self._audio_phase = 0
        self._audio_block_heights: tuple[int, ...] = (0,) * 12
        self._activity_phase = 0
        self._check_step = 0
        self._elapsed = QElapsedTimer()

        outer = QHBoxLayout(self)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        outer.setContentsMargins(2, 2, 2, 2)
        panel = _TerminalPanel()
        panel.setObjectName("overlayPanel")
        panel.setFixedSize(226, 44)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 7, 10, 7)
        panel_layout.setSpacing(4)

        main_row = QHBoxLayout()
        main_row.setSpacing(8)
        self._state_code = "[--]"

        self._audio_grid = _BlockGrid(
            12,
            7,
            cell_width=3,
            cell_height=3,
            gap=1,
        )
        self._progress_grid = self._audio_grid
        self._check_grid = self._audio_grid
        self._symbol_label = QLabel("!!")
        self._symbol_label.setObjectName("overlaySymbol")
        self._symbol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._visual_stack = QStackedWidget()
        self._visual_stack.setObjectName("overlayVisualStack")
        self._visual_stack.setFixedSize(47, 30)
        grid_index = self._visual_stack.addWidget(_visual_host(self._audio_grid))
        self._visual_indexes = {
            "audio": grid_index,
            "progress": grid_index,
            "check": grid_index,
            "message": self._visual_stack.addWidget(_visual_host(self._symbol_label)),
        }

        copy = QVBoxLayout()
        copy.setSpacing(1)
        self._status_label = QLabel(self._status_text)
        self._status_label.setObjectName("overlayStatus")
        self._status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._detail_label = QLabel("")
        self._detail_label.setObjectName("overlayDetail")
        self._detail_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        copy.addStretch()
        copy.addWidget(self._status_label)
        copy.addWidget(self._detail_label)
        copy.addStretch()
        main_row.addLayout(copy, 1)
        main_row.addWidget(self._visual_stack)
        panel_layout.addLayout(main_row)

        outer.addWidget(panel)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(100)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(90)
        self._activity_timer.timeout.connect(self._advance_activity)
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(20)
        self._check_timer.timeout.connect(self._advance_completion_animation)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss_feedback)

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def detail_text(self) -> str:
        return self._detail_label.text()

    @property
    def state_code(self) -> str:
        return self._state_code

    @property
    def visual_mode(self) -> str:
        return self._visual_mode

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def waveform_text(self) -> str:
        return "".join("█" if height else "░" for height in self._audio_block_heights)

    @property
    def audio_block_heights(self) -> tuple[int, ...]:
        return self._audio_block_heights

    @property
    def progress_active_cells(self) -> frozenset[tuple[int, int]]:
        return self._progress_grid.orange_cells

    @property
    def completion_grid_size(self) -> tuple[int, int]:
        return self._check_grid.grid_size

    @property
    def completion_green_cells(self) -> frozenset[tuple[int, int]]:
        return self._check_grid.green_cells

    def set_input_level(self, level: float) -> None:
        clamped = max(0.0, min(1.0, level))
        strength = min(1.0, sqrt(clamped) * 2.2)
        profiles = (
            (0.45, 0.62, 0.82, 1.0, 0.76, 0.58, 0.72, 0.92, 0.67, 0.84, 0.60, 0.40),
            (0.52, 0.78, 0.94, 0.70, 0.56, 0.86, 1.0, 0.74, 0.62, 0.88, 0.70, 0.48),
            (0.38, 0.58, 0.76, 0.92, 0.68, 1.0, 0.82, 0.60, 0.78, 0.96, 0.64, 0.44),
        )
        profile = profiles[self._audio_phase % len(profiles)]
        self._audio_phase += 1
        heights = tuple(max(0, min(7, round(strength * 7 * weight))) for weight in profile)
        self._audio_block_heights = heights
        active = frozenset(
            (column, row) for column, height in enumerate(heights) for row in range(7 - height, 7)
        )
        if self._visual_mode in {"audio", "none"}:
            self._audio_grid.set_cells(orange=active)

    def set_state(self, state: AppState) -> None:
        self._state = state
        self._dismiss_timer.stop()
        self._elapsed_timer.stop()
        self._activity_timer.stop()
        self._check_timer.stop()
        if state is AppState.RECORDING:
            self._active = True
            self._set_view(
                code="[REC]",
                status="LISTENING",
                detail="00:00.0",
                visual="audio",
            )
            self.set_input_level(0.0)
            self._elapsed.start()
            self._elapsed_timer.start()
            self._show_without_focus()
            return
        if state is AppState.TRANSCRIBING:
            self._show_activity_state(
                code="[TX]",
                status="TRANSCRIBING",
                detail="LOCAL MODEL",
            )
            return
        if state is AppState.LOADING_MODEL:
            self._show_activity_state(
                code="[LOAD]",
                status="LOADING MODEL",
                detail="LOCAL MODEL",
            )
            return
        if state is AppState.DELIVERING:
            self._show_activity_state(
                code="[OUT]",
                status="INSERTING",
                detail="CURSOR TARGET",
            )
            return
        if state in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            self._active = True
            self._set_view(
                code="[ERR]",
                status="SOMETHING WENT WRONG",
                detail="ACTION REQUIRED",
                visual="message",
            )
            self._show_without_focus()
            return
        self._active = False
        self._status_text = "Ready"
        self._status_label.setText("Ready")
        self.hide()

    def show_busy(self) -> None:
        self._show_activity_feedback("WORKING", "CURRENT TASK ACTIVE", 1600)

    def show_copied(self, *, word_count: int | None = None) -> None:
        self._show_completion_feedback("COPIED", word_count, 1400)

    def show_inserted(self, *, word_count: int | None = None) -> None:
        self._show_completion_feedback("INSERTED", word_count, 1400)

    def show_error(self, message: str) -> None:
        self._elapsed_timer.stop()
        self._activity_timer.stop()
        self._check_timer.stop()
        self._set_view(
            code="[ERR]",
            status=message,
            detail="ACTION REQUIRED",
            visual="message",
        )
        self._active = True
        self._show_without_focus()
        if self._state not in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            self._dismiss_timer.start(3500)

    def _show_activity_state(
        self,
        *,
        code: str,
        status: str,
        detail: str,
    ) -> None:
        self._active = True
        self._activity_phase = 0
        self._set_view(
            code=code,
            status=status,
            detail=detail,
            visual="progress",
        )
        self._advance_activity()
        self._activity_timer.start()
        self._show_without_focus()

    def _show_activity_feedback(self, status: str, detail: str, timeout_ms: int) -> None:
        self._elapsed_timer.stop()
        self._check_timer.stop()
        self._activity_phase = 0
        self._set_view(
            code="[BUSY]",
            status=status,
            detail=detail,
            visual="progress",
        )
        self._advance_activity()
        self._activity_timer.start()
        self._active = True
        self._show_without_focus()
        self._dismiss_timer.start(timeout_ms)

    def _show_completion_feedback(
        self,
        status: str,
        word_count: int | None,
        timeout_ms: int,
    ) -> None:
        self._elapsed_timer.stop()
        self._activity_timer.stop()
        self._check_step = 0
        detail = (
            f"{word_count} {'WORD' if word_count == 1 else 'WORDS'}"
            if word_count is not None
            else "COMPLETED"
        )
        self._set_view(
            code="[OK]",
            status=status,
            detail=detail,
            visual="check",
        )
        self._check_grid.set_cells()
        self._advance_completion_animation()
        self._check_timer.start()
        self._active = True
        self._show_without_focus()
        self._dismiss_timer.start(timeout_ms)

    def _set_view(
        self,
        *,
        code: str,
        status: str,
        detail: str,
        visual: str,
    ) -> None:
        self._status_text = status
        self._visual_mode = visual
        self._state_code = code
        self._status_label.setText(status)
        self._status_label.setToolTip(status)
        self._detail_label.setText(detail)
        self._visual_stack.setCurrentIndex(self._visual_indexes[visual])

    def _advance_activity(self) -> None:
        columns, rows = self._progress_grid.grid_size
        width = 2
        active = frozenset(
            ((self._activity_phase + offset) % columns, row)
            for offset in range(width)
            for row in range(rows)
        )
        self._progress_grid.set_cells(orange=active)
        self._activity_phase = (self._activity_phase + 1) % columns

    def _advance_completion_animation(self) -> None:
        if self._check_step >= len(_CHECK_SEQUENCE):
            self._finish_completion_animation()
            return
        self._check_step += 1
        self._check_grid.set_cells(
            green=frozenset(
                (column + 2, row) for column, row in _CHECK_SEQUENCE[: self._check_step]
            )
        )

    def _finish_completion_animation(self) -> None:
        self._check_timer.stop()
        self._check_step = len(_CHECK_SEQUENCE)
        self._check_grid.set_cells(
            green=frozenset((column + 2, row) for column, row in _CHECK_CELLS)
        )

    def _dismiss_feedback(self) -> None:
        if self._state in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            return
        if self._state is AppState.RECORDING:
            self.set_state(self._state)
            return
        if self._state in {
            AppState.TRANSCRIBING,
            AppState.LOADING_MODEL,
            AppState.DELIVERING,
        }:
            self.set_state(self._state)
            return
        self._elapsed_timer.stop()
        self._activity_timer.stop()
        self._check_timer.stop()
        self._active = False
        self._status_text = "Ready"
        self._status_label.setText("Ready")
        self._detail_label.clear()
        self.hide()

    def _show_without_focus(self) -> None:
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = area.center().x() - self.width() // 2
            y = area.bottom() - self.height() - 24
            self.move(x, y)
        self.show()

    def _update_elapsed(self) -> None:
        milliseconds = max(0, self._elapsed.elapsed())
        seconds = milliseconds // 1000
        tenths = (milliseconds % 1000) // 100
        self._detail_label.setText(f"{seconds // 60:02d}:{seconds % 60:02d}.{tenths}")
        self._update_recording_warning(seconds)

    def _display_recording_time(self, seconds: int) -> None:
        seconds = max(0, seconds)
        self._detail_label.setText(f"{seconds // 60:02d}:{seconds % 60:02d}.0")
        self._update_recording_warning(seconds)

    def _update_recording_warning(self, seconds: int) -> None:
        if seconds >= 9 * 60:
            self._status_text = "1 MINUTE LEFT"
            self._status_label.setText(self._status_text)
        else:
            self._status_text = "LISTENING"
            self._status_label.setText(self._status_text)
