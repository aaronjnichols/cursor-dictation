from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from cursor_dictation.core.models import AppState, DeliveryMode
from cursor_dictation.ui.icons import make_app_icon


class TrayIcon(QSystemTrayIcon):
    start_insert_requested = Signal()
    start_copy_requested = Signal()
    cancel_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self) -> None:
        super().__init__(make_app_icon())
        self.setToolTip("Cursor Dictation - Ready")

        menu = QMenu()
        self.start_action = QAction("Start dictation", menu)
        self.copy_action = QAction("Record and copy", menu)
        self.cancel_action = QAction("Cancel dictation", menu)
        self.settings_action = QAction("Settings", menu)
        self.quit_action = QAction("Quit", menu)

        self.start_action.triggered.connect(self.start_insert_requested.emit)
        self.copy_action.triggered.connect(self.start_copy_requested.emit)
        self.cancel_action.triggered.connect(self.cancel_requested.emit)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        self.quit_action.triggered.connect(self.quit_requested.emit)

        menu.addAction(self.start_action)
        menu.addAction(self.copy_action)
        menu.addAction(self.cancel_action)
        menu.addSeparator()
        menu.addAction(self.settings_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.setContextMenu(menu)
        self._state = AppState.IDLE
        self._recording_mode = DeliveryMode.INSERT
        self.set_state(AppState.IDLE)

    def set_recording_mode(self, mode: DeliveryMode) -> None:
        self._recording_mode = mode
        if self._state is AppState.RECORDING:
            self.set_state(self._state)

    def set_state(self, state: AppState) -> None:
        self._state = state
        idle = state is AppState.IDLE
        recording = state is AppState.RECORDING
        insert_recording = recording and self._recording_mode is DeliveryMode.INSERT
        copy_recording = recording and self._recording_mode is DeliveryMode.COPY
        self.start_action.setText("Stop dictation" if insert_recording else "Start dictation")
        self.copy_action.setText("Stop and copy" if copy_recording else "Record and copy")
        self.start_action.setEnabled(idle or insert_recording)
        self.copy_action.setEnabled(idle or copy_recording)
        self.cancel_action.setEnabled(recording)
        label = {
            AppState.RECORDING: "Recording",
            AppState.TRANSCRIBING: "Transcribing locally",
            AppState.DELIVERING: "Delivering text",
            AppState.ERROR: "Error",
            AppState.ERROR_WITH_TRANSCRIPT: "Text ready to copy",
        }.get(state, "Ready")
        self.setToolTip(f"Cursor Dictation - {label}")
